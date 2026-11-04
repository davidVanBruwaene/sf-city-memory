"""Your Block, Unfiltered: what is unusually common on one SF block compared with the whole city, for web.py's real mode."""
import json
import math
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv
from elasticsearch import Elasticsearch

load_dotenv(Path(__file__).with_name(".env"))
es = Elasticsearch(os.environ["ELASTIC_ENDPOINT"], api_key=os.environ["ELASTIC_API_KEY"])
SUFFIXES = {"st", "street", "ave", "av", "avenue", "blvd", "boulevard", "rd", "road", "dr", "drive", "way", "pl",
            "place", "ct", "court", "ter", "terrace", "ln", "lane", "aly", "alley", "hwy", "highway"}
RADIUS_M, DAYS, MIN_RATIO = 200, 365, 8
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


def soql(dataset, **params):
    r = requests.get(f"https://data.sf.gov/resource/{dataset}.json", params={f"${k}": v for k, v in params.items()},
                     timeout=60)
    r.raise_for_status()
    return r.json()


def name_match(field, name):
    # Require every word but the suffix: the data writes "St" where people write "Street".
    words = [w for w in name.replace(".", " ").split() if w.lower() not in SUFFIXES] or name.split()
    return {"match": {field: {"query": " ".join(words), "operator": "and"}}}


def counts(rows, key):
    c = {r[key]: int(r["n"]) for r in rows if r.get(key)}
    return c, sum(c.values())


def city(name, dataset, key, where):
    # The citywide baseline is the same for every block, so fetch it once per process.
    if name not in _city:
        _city[name] = counts(soql(dataset, select=f"{key}, count(*) AS n", where=where, group=key, limit=50000), key)
    return _city[name]


def unusual(rows, baseline, key, min_count, make):
    here, total = counts(rows, key)
    everywhere, city_total = baseline
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
    return dict(title=cat, ratio=ratio, count=n, period="2 yr", dataset="SFPD incidents (wg3w-h783)", rank=None,
                sentence=f"{ratio}x the city's share of '{cat}' incident reports: {n} within {RADIUS_M} m in two years.")


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


def block_facts(street, cross):
    must = [name_match("corridor", street)] + ([name_match("limits", cross)] if cross else [])
    hits = es.search(index="sf-street-sweeping", size=1, query={"bool": {"must": must}})["hits"]["hits"]
    if not hits:
        return {"error": "not_found"}
    b = hits[0]["_source"]
    lat, lon = b["location"]["lat"], b["location"]["lon"]
    near = f"within_circle(point, {lat}, {lon}, {RADIUS_M})"
    since = (datetime.now() - timedelta(days=DAYS)).strftime("%Y-%m-%dT00:00:00")
    since2 = (datetime.now() - timedelta(days=2 * DAYS)).strftime("%Y-%m-%dT00:00:00")
    key = "service_subtype"
    facts = unusual(soql("vw6y-z8j6", select=f"{key}, count(*) AS n", group=key, limit=5000,
                         where=f"{near} AND requested_datetime > '{since}'"),
                    city("311", "vw6y-z8j6", key, f"requested_datetime > '{since}'"), key, 15, fact_311)
    key = "incident_description"
    facts += unusual(soql("wg3w-h783", select=f"{key}, count(*) AS n", group=key, limit=5000,
                          where=f"{near} AND report_datetime > '{since2}'"),
                     city("police", "wg3w-h783", key, f"report_datetime > '{since2}'"), key, 15, fact_police)
    # Trees carry the street-cleaning block's centerline id (cnn), so these are the block's own trees.
    facts += unusual(soql("tkzw-k3nq", select="species, count(*) AS n", where=f"cnn='{b['cnn']}'", group="species"),
                     city("trees", "tkzw-k3nq", "species", "species IS NOT NULL"), "species", 10, fact_tree)
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
    return dict(
        address=f"{street} & {cross}, San Francisco" if cross else f"{street}, San Francisco", lat=lat, lon=lon,
        nickname=nickname,
        # The card needs officer arrival times from parking-citation data, which is not loaded yet.
        weirdness=weirdness, facts=facts, sweeping=None)
