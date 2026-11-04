"""City memory: each chat turn can both answer from and add to a shared, permission-aware store of local knowledge."""
import sys
import time
from datetime import datetime
from typing import Literal

from elasticsearch import ApiError, NotFoundError
from pydantic import BaseModel

from sfhack import MISTRAL_API_KEY, es, mistral

INDEX = "city-memory"
EMBED_ID = "mistral-embeddings"
MODEL = "mistral-large-4"
USAGE = "usage: python citymem.py setup | chat <user> | say <user> <text|@file> [--yes] | show | stats | reset"

EXTRACT = (
    "You maintain the shared memory of San Francisco's AI and startup community. From the user's message extract "
    "(1) the question they are asking, if any, and (2) every concrete, reusable piece of local knowledge they report: "
    "events, places to work, communities, people open to meeting, tips. Each fact's body must make sense without the "
    "conversation: keep who, what, where, when, how to get in, and why it is worth it or who recommended it. "
    "visibility: 'personal' for the user's own plans and private contacts, 'community' for insider knowledge, "
    "'public' for things already publicly listed. access is 'unknown' unless the message says free, paid or "
    "approval-required. Never invent facts; return an empty list when there are none."
)
ANSWER = (
    "Answer using only the numbered memory entries and cite them like [2]. For each recommendation say whether access "
    "is free, paid or approval-required, who reported it and how long ago (today is {today}). Flag only entries older "
    "than 60 days as possibly stale, and say when an entry replaced an older report. Keep it short and conversational. "
    "If nothing is relevant, say so."
)
MAPPINGS = {"properties": {
    "kind": {"type": "keyword"}, "title": {"type": "text"}, "body": {"type": "text"},
    "body_semantic": {"type": "semantic_text", "inference_id": EMBED_ID},
    "access": {"type": "keyword"}, "visibility": {"type": "keyword"}, "when": {"type": "keyword"},
    "neighborhood": {"type": "keyword"}, "url": {"type": "keyword"}, "owner": {"type": "keyword"},
    "source_quote": {"type": "text"}, "status": {"type": "keyword"}, "supersedes": {"type": "keyword"},
    "observed_at": {"type": "date"},
}}


class Fact(BaseModel):
    kind: Literal["event", "place", "community", "person", "tip"]
    title: str
    body: str
    access: Literal["free", "paid", "approval", "unknown"]
    visibility: Literal["public", "community", "personal"]
    when: str | None
    neighborhood: str | None
    url: str | None


class Turn(BaseModel):
    question: str | None
    facts: list[Fact]


class Match(BaseModel):
    same_as: int | None


def setup():
    try:
        es.inference.get(inference_id=EMBED_ID)
        print(f"inference endpoint {EMBED_ID}: exists")
    except NotFoundError:
        es.inference.put(task_type="text_embedding", inference_id=EMBED_ID, inference_config={
            "service": "mistral", "service_settings": {"api_key": MISTRAL_API_KEY, "model": "mistral-embed"}})
        print(f"inference endpoint {EMBED_ID}: created")
    if es.indices.exists(index=INDEX):
        print(f"index {INDEX}: exists")
    else:
        es.indices.create(index=INDEX, mappings=MAPPINGS)
        print(f"index {INDEX}: created")


def visible_to(user):
    # Public and community entries for everyone, personal ones only for their owner; replaced reports are hidden.
    return {"bool": {
        "must_not": [{"term": {"status": "superseded"}}],
        "should": [{"terms": {"visibility": ["public", "community"]}}, {"term": {"owner": user}}],
        "minimum_should_match": 1,
    }}


def retrieve(user, query, size=8):
    lexical = {"bool": {"must": {"multi_match": {"query": query, "fields": ["title^2", "body"]}}, "filter": visible_to(user)}}
    semantic = {"bool": {"must": {"semantic": {"field": "body_semantic", "query": query}}, "filter": visible_to(user)}}
    try:
        r = es.search(index=INDEX, size=size, source_excludes=["body_semantic"], retriever={"rrf": {"retrievers": [
            {"standard": {"query": lexical}}, {"standard": {"query": semantic}}]}})
    except ApiError as e:
        print(f"(hybrid search failed, using semantic only: {e.message})")
        r = es.search(index=INDEX, size=size, source_excludes=["body_semantic"], query=semantic)
    return r["hits"]["hits"]


def chat(method, model, **kw):
    # Free tier allows about one request per second per model; mistral-large-4 always reasons, "low" is its floor.
    if model == MODEL:
        kw["reasoning_effort"] = "low"
    for attempt in range(4):
        try:
            return getattr(mistral.chat, method)(model=model, **kw)
        except Exception as e:
            if getattr(e, "status_code", None) != 429 or attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))


def text_of(content):
    return content if isinstance(content, str) else "".join(getattr(c, "text", "") for c in content if getattr(c, "type", "") == "text")


def find_same(user, fact):
    # A personal note may only replace the owner's personal notes, so it can never hide a shared entry from others.
    shared = ("public", "community")
    candidates = [h for h in retrieve(user, fact.body, size=3)
                  if (h["_source"]["visibility"] in shared) == (fact.visibility in shared) and h["_source"]["kind"] == fact.kind]
    if not candidates:
        return None
    listing = "\n".join(f"{i}. {h['_source']['title']}: {h['_source']['body']}" for i, h in enumerate(candidates, 1))
    m = chat("parse", MODEL, response_format=Match, messages=[
        {"role": "system", "content": "Return the number of the existing entry that describes the very same event, "
                                      "place, community, person or tip as the new report (an update or correction of it), "
                                      "or null. Different things that merely mention each other are not the same. "
                                      "When unsure, return null."},
        {"role": "user", "content": f"Existing:\n{listing}\n\nNew report: {fact.title}: {fact.body}"},
    ]).choices[0].message.parsed
    return candidates[m.same_as - 1] if m.same_as and 1 <= m.same_as <= len(candidates) else None


def remember(user, fact, quote, match=True):
    doc = fact.model_dump() | {"body_semantic": fact.body, "owner": user, "source_quote": quote,
                               "status": "reported", "observed_at": datetime.now().astimezone().isoformat()}
    old = find_same(user, fact) if match else None
    if old:
        prev = old["_source"]
        r = chat("complete", MODEL, messages=[
            {"role": "system", "content": "Rewrite the older entry with the newer report applied. Keep every detail the "
                                          "newer report does not change. Reply with the rewritten entry only."},
            {"role": "user", "content": f"Older: {prev['body']}\nNewer: {fact.body}"},
        ])
        doc["body"] = doc["body_semantic"] = text_of(r.choices[0].message.content).strip() or fact.body
        doc["access"] = prev["access"] if doc["access"] == "unknown" else doc["access"]
        doc |= {k: doc[k] or prev.get(k) for k in ("when", "neighborhood", "url")}
        doc["supersedes"] = old["_id"]
    es.index(index=INDEX, document=doc, refresh=True)
    if old:
        es.update(index=INDEX, id=old["_id"], doc={"status": "superseded"}, refresh=True)
        print(f"  replaces '{old['_source']['title']}' reported by {old['_source']['owner']}")
    return old["_source"]["title"] if old else None


def consent(fact):
    a = input(f"  share as {fact.visibility}? [y]es / [p]ersonal only / [n]o: ").strip().lower()
    if a == "p":
        fact.visibility = "personal"
    return a in ("y", "p")


def format_entries(hits):
    return "\n".join(
        f"[{i}] {s['kind']} | {s['title']} | {s['body']} | access={s['access']} | when={s.get('when')} "
        f"| reported by {s['owner']} on {s['observed_at'][:10]}" + (" | replaces an older report" if s.get("supersedes") else "")
        for i, s in enumerate((h["_source"] for h in hits), 1))


def answer(user, question, hits):
    if not hits:
        return "Nothing in the city memory matches that yet."
    entries = format_entries(hits)
    r = chat("complete", MODEL, messages=[
        {"role": "system", "content": ANSWER.format(today=datetime.now().date())},
        {"role": "user", "content": f"Memory:\n{entries}\n\nQuestion from {user}: {question}"},
    ])
    return text_of(r.choices[0].message.content)


def turn(user, text, assume_yes=False):
    t = chat("parse", MODEL, response_format=Turn, messages=[
        {"role": "system", "content": EXTRACT}, {"role": "user", "content": text},
    ]).choices[0].message.parsed
    for fact in t.facts:
        print(f"+ [{fact.kind}/{fact.access}/{fact.visibility}] {fact.title}: {fact.body}")
        if assume_yes or consent(fact):
            remember(user, fact, text)
    if t.question:
        print(answer(user, t.question, retrieve(user, t.question)))


def show():
    r = es.search(index=INDEX, size=100, sort=[{"observed_at": "desc"}], source_excludes=["body_semantic", "source_quote"])
    print("admin view: every entry, including personal and replaced ones")
    for s in (h["_source"] for h in r["hits"]["hits"]):
        print(f"{s['observed_at'][:16]} {s['status']:<10} {s['visibility']:<9} {s['owner']:<10} [{s['kind']}/{s['access']}] {s['title']}")


def stats():
    r = es.search(index=INDEX, size=0, aggs={k: {"terms": {"field": k}} for k in ("kind", "access", "visibility", "owner", "status")})
    for k, agg in r["aggregations"].items():
        print(f"{k}: " + ", ".join(f"{b['key']}={b['doc_count']}" for b in agg["buckets"]))


def reset():
    es.indices.delete(index=INDEX, ignore_unavailable=True)
    print(f"index {INDEX}: deleted, run setup to recreate")


def main(argv):
    if es is None or mistral is None:
        sys.exit("fill .env first, then check it with: python sfhack.py")
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    simple = {"setup": setup, "show": show, "stats": stats, "reset": reset}
    if cmd in simple and not args:
        simple[cmd]()
    elif cmd == "chat" and len(args) == 1:
        while True:
            try:
                text = input(f"{args[0]}> ").strip()
            except EOFError:
                break
            if text:
                turn(args[0], text)
    elif cmd == "say" and len(args) in (2, 3):
        text = open(args[1][1:]).read() if args[1].startswith("@") else args[1]
        turn(args[0], text, assume_yes="--yes" in args[2:])
    else:
        sys.exit(USAGE)


if __name__ == "__main__":
    main(sys.argv[1:])
