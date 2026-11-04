"""Your Block, Unfiltered: what is unusually common on one SF block compared with the whole city, for web.py's real mode."""
import json
import math
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

load_dotenv(Path(__file__).with_name(".env"))
es = Elasticsearch(os.environ["ELASTIC_ENDPOINT"], api_key=os.environ["ELASTIC_API_KEY"])
SUFFIXES = {"st", "street", "ave", "av", "avenue", "blvd", "boulevard", "rd", "road", "dr", "drive", "way", "pl",
            "place", "ct", "court", "ter", "terrace", "ln", "lane", "aly", "alley", "hwy", "highway"}
RADIUS_M, MIN_RATIO = 200, 8
MODEL = "mistral-large-4"
# Police descriptions about guns and violence stay out of a block's story: they stigmatise, and a shop-lifting joke is fine.
VIOLENT = re.compile(r"gun|firearm|weapon|shoot|stab|assault|batter|homicide|murder|manslaughter|rape|robbery|kidnap|"
                     r"arson|threat|domestic|molest|sex|abuse|trafficking|child|suicide|death|brandish", re.I)
# Plain names for the labels the city data uses; the key is the label with its first letter capitalised.
TITLES = {"Entertainment reports": "Nightlife noise reports", "Permit Violation, Sidewalk Sales": "Sidewalk sales without a permit",
          "Peddling Without A License": "Unlicensed peddling"}
_city = {}
try:
    from sfhack import mistral
except Exception:  # no key, or an SDK without the new import path: the template sentences carry on
    mistral = None


INDEX = "sf-block-signals"
# One query answers all three datasets: per dataset, the count of each category (inside the radius, or citywide).
BY_CATEGORY = {"by_dataset": {"terms": {"field": "dataset", "size": 10},
                              "aggs": {"c": {"terms": {"field": "category", "size": 5000}}}}}


def name_match(field, name):
    # Require every word but the suffix: the data writes "St" where people write "Street".
    words = [w for w in name.replace(".", " ").split() if w.lower() not in SUFFIXES] or name.split()
    return {"match": {field: {"query": " ".join(words), "operator": "and"}}}


def name_words(name):
    return " ".join(w for w in name.replace(".", " ").split() if w.lower() not in SUFFIXES).upper() or name.upper()


def per_dataset(resp):
    out = {}
    for d in resp["aggregations"]["by_dataset"]["buckets"]:
        c = {x["key"]: x["doc_count"] for x in d["c"]["buckets"]}
        out[d["key"]] = (c, d["doc_count"])
    return out


def city():
    # The citywide baseline is the same for every block, so fetch it once per process.
    if not _city:
        _city.update(per_dataset(es.search(index=INDEX, size=0, aggs=BY_CATEGORY)))
    return _city


def unusual(here_all, baseline, dataset, min_count, make):
    here, total = here_all.get(dataset, ({}, 0))
    everywhere, city_total = baseline.get(dataset, ({}, 0))
    out = []
    for cat, n in here.items():
        if n >= min_count and everywhere.get(cat):
            ratio = round((n / total) / (everywhere[cat] / city_total), 1)
            fact = make(cat, n, ratio) if ratio >= MIN_RATIO else None
            if fact:
                out.append(fact)
    return out


def fact_311(cat, n, ratio):
    title = cat.replace("_", " ").strip().capitalize()
    return dict(title=f"{title} reports", ratio=ratio, count=n, period="1 yr", dataset="311 (vw6y-z8j6)", rank=None,
                sentence=f"{ratio}x the city's share of {title.lower()} reports: {n} within {RADIUS_M} m in the past year.")


def fact_police(cat, n, ratio):
    if VIOLENT.search(cat):
        return None
    return dict(title=cat, ratio=ratio, count=n, period="1 yr", dataset="SFPD incidents (wg3w-h783)", rank=None,
                sentence=f"{ratio}x the city's share of '{cat}' incident reports: {n} within {RADIUS_M} m in the past year.")


def fact_tree(cat, n, ratio):
    name = cat.split("::")[-1].strip()
    return dict(title=f"{name} trees", ratio=ratio, count=n, period="all", dataset="Street trees (tkzw-k3nq)", rank=None,
                sentence=f"{n} {name} trees on this block: {ratio}x the city's share.")


def say(facts, nickname_hint):
    """Mistral writes the nickname and one sentence per fact from computed numbers only; None means use the templates."""
    if mistral is None or not facts:
        return None
    data = [{"title": f["title"], "ratio": f["ratio"], "count": f["count"], "period": f["period"]} for f in facts]
    allowed = {str(x) for f in data for x in (f["ratio"], round(f["ratio"]), f["count"])} | {"1", "2", "200"}
    prompt = ("Write a playful but kind blurb for one San Francisco block. Facts (ratio = times the SF average share, "
              f"measured within {RADIUS_M} m of the block): {json.dumps(data)}. Return JSON "
              '{"nickname": "<one fun line, no digits, like The Siren Capital of SF>", "sentences": ["<one sentence per fact, '
              'same order>"]}. Use only numbers given above, never invent one, and never blame people.')
    for attempt in range(3):
        try:
            r = mistral.chat.complete(model=MODEL, reasoning_effort="low", response_format={"type": "json_object"},
                                      messages=[{"role": "user", "content": prompt}])
            c = r.choices[0].message.content
            out = json.loads(c if isinstance(c, str) else "".join(getattr(x, "text", "") for x in c if getattr(x, "type", "") == "text"))
            nick, sents = out["nickname"].strip(), [str(x).strip() for x in out["sentences"]]
            nums = lambda t: set(re.findall(r"\d+(?:\.\d+)?", t))
            if len(sents) == len(facts) and nick and not nums(nick) and all(nums(t) <= allowed for t in sents):
                return nick, sents
            return None  # numbers that were not computed: fall back to the templates
        except Exception as e:
            if getattr(e, "status_code", None) != 429 or attempt == 2:
                return None
            time.sleep(1.5 * (attempt + 1))


TICKETS_INDEX = "sf-sweep-tickets"


def sweeping_info(b):
    """The block's cleaning schedule plus, when the ticket data shows a steady pattern, when the officer usually arrives."""
    from sweep_officer import officer_timing
    day, a, z = b["weekday"], b["fromhour"] % 12 or 12, b["tohour"] % 12 or 12
    out = dict(schedule=f"{day[:3]} {a}-{z}{'am' if b['tohour'] < 12 else 'pm'}")
    near = es.search(index=TICKETS_INDEX, size=1, sort=[{"_geo_distance": {"location": b["location"], "order": "asc"}}],
                     query={"wildcard": {"block_key": f"* {name_words(b['corridor'])}*"}})["hits"]["hits"]
    try:
        timing = officer_timing(near[0]["_source"]["block_key"], day) if near else None
    except Exception as e:
        print(f"officer_timing failed: {e}", file=sys.stderr)
        timing = None
    return {**out, **timing} if timing else out


def block_facts(street, cross):
    must = [name_match("corridor", street)] + ([name_match("limits", cross)] if cross else [])
    hits = es.search(index="sf-street-sweeping", size=1, query={"bool": {"must": must}})["hits"]["hits"]
    if not hits:
        return {"error": "not_found"}
    b = hits[0]["_source"]
    lat, lon = b["location"]["lat"], b["location"]["lon"]
    here = per_dataset(es.search(index=INDEX, size=0, aggs=BY_CATEGORY, query={
        "geo_distance": {"distance": f"{RADIUS_M}m", "location": {"lat": lat, "lon": lon}}}))
    base = city()
    facts = unusual(here, base, "311", 15, fact_311)
    facts += unusual(here, base, "police", 15, fact_police)
    facts += unusual(here, base, "trees", 10, fact_tree)
    facts = sorted(facts, key=lambda f: -f["ratio"])[:3]
    for f in facts:
        f["title"] = TITLES.get(f["title"], f["title"])
    weirdness = round(min(9.9, sum(math.log(f["ratio"]) for f in facts)), 1)
    nickname = f"Remarkably Normal {b['corridor']}"
    written = say(facts, nickname)
    if written:
        nickname = written[0]
        for f, text in zip(facts, written[1]):
            f["sentence"] = text
    elif facts:
        nickname = f"The {facts[0]['title'].removesuffix(' reports').removesuffix(' trees')} Capital of {b['corridor']}"
        for f in facts:
            f["sentence"] = f"{f['title']}: {f['ratio']:.0f}x the SF average ({f['count']} reports)"
    try:
        sweeping = sweeping_info(b)
    except Exception as e:
        print(f"sweeping_info failed: {e}", file=sys.stderr)
        sweeping = None
    return dict(
        address=f"{street} & {cross}, San Francisco" if cross else f"{street}, San Francisco", lat=lat, lon=lon,
        nickname=nickname,
        weirdness=weirdness, facts=facts, sweeping=sweeping)
