"""Your Block, Unfiltered: what is unusually common on one SF block compared with the whole city, for web.py's real mode."""
import math
import os
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv
from elasticsearch import Elasticsearch

load_dotenv(Path(__file__).with_name(".env"))
es = Elasticsearch(os.environ["ELASTIC_ENDPOINT"], api_key=os.environ["ELASTIC_API_KEY"])
SUFFIXES = {"st", "street", "ave", "av", "avenue", "blvd", "boulevard", "rd", "road", "dr", "drive", "way", "pl",
            "place", "ct", "court", "ter", "terrace", "ln", "lane", "aly", "alley", "hwy", "highway"}
RADIUS_M, DAYS = 200, 365
_city = {}


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
            out.append(make(cat, n, round((n / total) / (everywhere[cat] / city_total), 1)))
    return out


def fact_311(cat, n, ratio):
    title = cat.replace("_", " ").strip().capitalize()
    return dict(title=f"{title} reports", ratio=ratio, count=n, period="1 yr", dataset="311 (vw6y-z8j6)", rank=None,
                sentence=f"{ratio}x the city's share of {title.lower()} reports: {n} within {RADIUS_M} m in the past year.")


def fact_tree(cat, n, ratio):
    name = cat.split("::")[-1].strip()
    return dict(title=f"{name} trees", ratio=ratio, count=n, period="all", dataset="Street trees (tkzw-k3nq)", rank=None,
                sentence=f"{n} {name} trees on this block: {ratio}x the city's share.")


def block_facts(street, cross):
    must = [name_match("corridor", street)] + ([name_match("limits", cross)] if cross else [])
    hits = es.search(index="sf-street-sweeping", size=1, query={"bool": {"must": must}})["hits"]["hits"]
    if not hits:
        return {"error": "not_found"}
    b = hits[0]["_source"]
    lat, lon = b["location"]["lat"], b["location"]["lon"]
    since = (datetime.now() - timedelta(days=DAYS)).strftime("%Y-%m-%dT00:00:00")
    key = "service_subtype"
    facts = unusual(soql("vw6y-z8j6", select=f"{key}, count(*) AS n", group=key, limit=5000,
                         where=f"within_circle(point, {lat}, {lon}, {RADIUS_M}) AND requested_datetime > '{since}'"),
                    city("311", "vw6y-z8j6", key, f"requested_datetime > '{since}'"), key, 15, fact_311)
    # Trees carry the street-cleaning block's centerline id (cnn), so these are the block's own trees.
    facts += unusual(soql("tkzw-k3nq", select="species, count(*) AS n", where=f"cnn='{b['cnn']}'", group="species"),
                     city("trees", "tkzw-k3nq", "species", "species IS NOT NULL"), "species", 3, fact_tree)
    facts = sorted(facts, key=lambda f: -f["ratio"])[:3]
    top = facts[0]["ratio"] if facts else 1.0
    return dict(
        address=f"{street} & {cross}, San Francisco" if cross else f"{street}, San Francisco", lat=lat, lon=lon,
        nickname=f"The {facts[0]['title'].removesuffix(' reports').removesuffix(' trees')} Capital of {b['corridor']}" if facts
        else f"Remarkably Normal {b['corridor']}",
        # The card needs officer arrival times from parking-citation data, which is not loaded yet.
        weirdness=round(min(9.9, 3 + 1.5 * math.log2(max(1.0, top))), 1), facts=facts, sweeping=None)
