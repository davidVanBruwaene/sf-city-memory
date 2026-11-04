"""Write to the shared city memory from the web: chat turns that add or update entries, bulk uploads (CSV or notes),
and answers that cite who reported what. Reuses citymem's extraction, matching, merging and answering.

Run `python memweb.py backfill` to geocode entries that have an address in their body but no location yet.
"""
import contextlib
import csv
import io
import re
import sys
import unicodedata

import requests
from flask import Blueprint, jsonify, request

import citymem
from citymem import INDEX, Fact, Turn, es

bp = Blueprint("memweb", __name__)
SF = (37.70, 37.84, -122.52, -122.35)  # south, north, west, east
ADDRESS = re.compile(r"\b(\d{1,5})\s+((?:[A-Z0-9][\w'.-]*\s?){1,3}?)(?:\s*(?:St|Street|Ave|Avenue|Blvd|Way|Pl|Rd|Dr|Ln)\b\.?)?(?=[,.;)]|\s+(?:is|in|on|for|near|has|San)\b|$)")
FIELDS = ["kind", "title", "body", "owner", "observed_at", "source_quote", "url", "neighborhood", "when", "access",
          "visibility", "location", "first_owner", "first_observed_at", "supersedes"]
COLS = {"title": ("name", "title", "dba_name", "place", "business", "shop", "event"),
        "address": ("address", "addr", "location", "street", "full_business_address"),
        "notes": ("notes", "note", "description", "desc", "why", "comment", "comments", "tip", "body"),
        "neighborhood": ("neighborhood", "hood", "area", "district"),
        "url": ("url", "link", "website", "web"),
        "when": ("when", "date", "time", "hours")}


def in_sf(lat, lon):
    return SF[0] <= lat <= SF[1] and SF[2] <= lon <= SF[3]


def find_address(text):
    m = ADDRESS.search(text or "")
    return f"{m.group(1)} {m.group(2).strip()}" if m else None


def geocode(address=None, name=None):
    """Address or place name -> {lat, lon, geo_source}. Tries the seeded DataSF places in city-memory, then DataSF
    Registered Business Locations (g8m3-pdis), then OpenStreetMap Nominatim."""
    if name:
        name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    if name:  # a seeded place with the same name (and street number, when we have one) is the cheapest match
        must = [{"match": {"title": {"query": name, "operator": "and"}}}]
        if address:
            must.append({"match_phrase": {"body": address.split()[0]}})
        r = es.search(index=INDEX, size=1, source_includes=["location", "title"], query={"bool": {
            "must": must, "filter": [{"exists": {"field": "location"}}], "must_not": [{"term": {"status": "superseded"}}]}})
        if r["hits"]["hits"]:
            loc = r["hits"]["hits"][0]["_source"]["location"]
            return {"lat": loc["lat"], "lon": loc["lon"], "geo_source": "city-memory (DataSF g8m3-pdis)"}
    if not address:
        return None
    street = re.sub(r"[^A-Z0-9 ]", "", address.upper())
    try:
        rows = requests.get("https://data.sf.gov/resource/g8m3-pdis.json", timeout=15, params={
            "$where": f"city='San Francisco' AND location IS NOT NULL AND upper(full_business_address) like '{street}%'",
            "$select": "location", "$limit": 1}).json()
        if rows and isinstance(rows, list):
            lon, lat = rows[0]["location"]["coordinates"]
            if in_sf(lat, lon):
                return {"lat": lat, "lon": lon, "geo_source": "DataSF g8m3-pdis"}
    except Exception:
        pass
    try:
        rows = requests.get("https://nominatim.openstreetmap.org/search", timeout=15,
                            headers={"User-Agent": "sf-city-memory-hackathon/1.0"},
                            params={"q": f"{address}, San Francisco, CA", "format": "json", "limit": 1}).json()
        if rows:
            lat, lon = float(rows[0]["lat"]), float(rows[0]["lon"])
            if in_sf(lat, lon):
                return {"lat": lat, "lon": lon, "geo_source": "OpenStreetMap Nominatim"}
    except Exception:
        pass
    return None


def locate(fact):
    g = geocode(find_address(fact.body) or find_address(fact.title), fact.title if fact.kind == "place" else None)
    return ({"lat": g["lat"], "lon": g["lon"]}, g["geo_source"]) if g else (None, None)


def item(doc_id, doc):
    return {k: doc.get(k) for k in FIELDS if doc.get(k) is not None} | {"id": doc_id}


def save(user, facts, quote, match=True):
    out = []
    for fact in facts:
        loc, geo = locate(fact)
        with contextlib.redirect_stdout(sys.stderr):
            doc_id, doc, old = citymem.store(user, fact, quote, match=match, location=loc)
        prev = old["_source"] if old else None
        out.append(item(doc_id, doc) | {"geo_source": geo, "replaced": prev and {
            "title": prev["title"], "body": prev["body"], "owner": prev["owner"], "observed_at": prev["observed_at"]}})
    return out


EVENTS = re.compile(r"\b(events?|this week|tonight|today|tomorrow|weekend|meetups?|happening|going to|attend)\b", re.I)


def recall(user, question):
    """citymem.retrieve, plus the events themselves for "what's on" questions: 900+ seeded cafes otherwise crowd them out."""
    hits = citymem.retrieve(user, question, size=6)
    if EVENTS.search(question):
        r = es.search(index=INDEX, size=6, source_excludes=["body_semantic"], query={"bool": {
            "must": {"semantic": {"field": "body_semantic", "query": question}},
            "filter": [citymem.visible_to(user), {"term": {"kind": "event"}}]}})
        seen = {h["_id"] for h in r["hits"]["hits"]}
        hits = r["hits"]["hits"] + [h for h in hits if h["_id"] not in seen][:3]
    return hits


def sources(hits):
    return [item(h["_id"], h["_source"]) | {"n": i} for i, h in enumerate(hits, 1)]


def user_of(body):
    u = re.sub(r"[^\w .@-]", "", str(body.get("user") or "")).strip()[:40]
    return u or "web-guest"


@bp.post("/api/memory/turn")
def turn():
    """One chat message: returns the facts it reports (to confirm before saving) and an answer to its question."""
    b = request.get_json(silent=True) or {}
    text, user = str(b.get("text") or "").strip()[:4000], user_of(b)
    if not text:
        return jsonify(error="Say something about SF, or ask a question."), 400
    try:
        t = citymem.chat("parse", citymem.MODEL, response_format=Turn, messages=[
            {"role": "system", "content": citymem.EXTRACT}, {"role": "user", "content": text}]).choices[0].message.parsed
        out = {"facts": [f.model_dump() for f in t.facts], "question": t.question}
        if t.question:
            hits = recall(user, t.question)
            out |= {"reply": citymem.answer(user, t.question, hits), "sources": sources(hits)}
        return jsonify(out)
    except Exception as e:
        return jsonify(error="The city memory is busy right now. Try again in a moment.", detail=str(e)), 502


@bp.post("/api/memory/save")
def save_facts():
    """Save the facts the user confirmed: share = 'shared' keeps their visibility, 'personal' makes them private."""
    b = request.get_json(silent=True) or {}
    user, quote = user_of(b), str(b.get("quote") or "")[:4000]
    try:
        facts = [Fact(**f) for f in (b.get("facts") or [])][:10]
    except Exception as e:
        return jsonify(error="bad facts", detail=str(e)), 400
    for f in facts:
        if b.get("share") == "personal":
            f.visibility = "personal"
        elif f.visibility == "personal":
            f.visibility = "community"
    try:
        return jsonify(items=save(user, facts, quote))
    except Exception as e:
        return jsonify(error="Could not save to the city memory. Try again in a moment.", detail=str(e)), 502


def csv_facts(text):
    rows = list(csv.DictReader(io.StringIO(text.strip())))
    if not rows:
        return []
    header = {c: (c or "").strip().lower() for c in rows[0]}
    pick = {k: next((c for c, low in header.items() if low in names), None) for k, names in COLS.items()}
    if not pick["title"]:
        return []
    facts = []
    for r in rows:
        get = lambda k: (r.get(pick[k]) or "").strip() if pick[k] else ""
        title = get("title")
        if not title:
            continue
        addr, notes = get("address"), get("notes")
        kind = "event" if pick["when"] and get("when") and "date" in (pick["when"] or "").lower() else "place"
        body = f"{title}" + (f" at {addr}, San Francisco" if addr else "") + "." + (f" {notes.rstrip('.')}." if notes else "")
        extra = [f"{c}: {v}" for c, v in r.items() if c and v and c not in pick.values()]
        body += (" " + "; ".join(extra) + ".") if extra else ""
        facts.append(Fact(kind=kind, title=title, body=body, access="unknown", visibility="community",
                          when=get("when") or None, neighborhood=get("neighborhood") or None, url=get("url") or None))
    return facts


@bp.post("/api/memory/upload")
def upload():
    """Bulk add: a CSV (one row = one entry, columns like name, address, notes) or free-form notes that Mistral splits
    into facts. Each entry is geocoded and merged into an existing entry about the same thing."""
    b = request.get_json(silent=True) or {}
    user, text = user_of(b), str(b.get("text") or "")[:60000]
    name = str(b.get("filename") or "pasted text")[:80]
    if not text.strip():
        return jsonify(error="Empty upload."), 400
    try:
        first = text.strip().splitlines()[0]
        facts = csv_facts(text) if ("," in first or name.lower().endswith(".csv")) else []
        if not facts:
            facts = citymem.chat("parse", citymem.MODEL, response_format=Turn, messages=[
                {"role": "system", "content": citymem.EXTRACT}, {"role": "user", "content": text[:12000]}],
            ).choices[0].message.parsed.facts
        facts = facts[:40]
        if b.get("share") == "personal":
            for f in facts:
                f.visibility = "personal"
        items = save(user, facts, f"Uploaded by {user}: {name}", match=len(facts) <= 15)
        return jsonify(items=items, count=len(items), located=sum(1 for i in items if i.get("location")))
    except Exception as e:
        return jsonify(error="Could not read that upload. Try a CSV with a name and address column.", detail=str(e)), 502


def backfill():
    q = {"bool": {"must_not": [{"exists": {"field": "location"}}, {"term": {"status": "superseded"}}]}}
    for h in es.search(index=INDEX, size=200, query=q, source_excludes=["body_semantic"])["hits"]["hits"]:
        s = h["_source"]
        addr = find_address(s["body"])
        g = geocode(addr, s["title"] if s["kind"] == "place" else None)
        print(f"{s['title'][:40]:<40} {addr or '-':<25} {g}")
        if g:
            es.update(index=INDEX, id=h["_id"], doc={"location": {"lat": g["lat"], "lon": g["lon"]}}, refresh=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["backfill"]:
        backfill()
    else:
        sys.exit("usage: python memweb.py backfill")
