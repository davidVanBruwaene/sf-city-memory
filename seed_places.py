"""Seed the shared city memory with open SF coffee shops from DataSF Registered Business Locations (g8m3-pdis)."""
import hashlib

import requests
from elasticsearch import helpers

import citymem
from citymem import Fact, INDEX, es
from datetime import datetime

URL = "https://data.sf.gov/resource/g8m3-pdis.json"
NAMES = ("coffee", "cafe", "café", "espresso", "roasters")
WHERE = ("city='San Francisco' AND dba_end_date IS NULL AND location_end_date IS NULL AND location IS NOT NULL AND ("
         + " OR ".join(f"upper(dba_name) like '%{n.upper()}%'" for n in NAMES) + ")")


def fetch():
    rows, offset = [], 0
    while True:
        page = requests.get(URL, params={"$where": WHERE, "$order": "uniqueid", "$limit": 1000, "$offset": offset}, timeout=60)
        page.raise_for_status()
        rows += page.json()
        if len(page.json()) < 1000:
            return rows
        offset += 1000


def docs(rows):
    seen, now = set(), datetime.now().astimezone().isoformat()
    for r in rows:
        name, addr = r["dba_name"].strip(), r["full_business_address"].strip()
        key = (name.lower(), addr.lower())
        if key in seen:
            continue
        seen.add(key)
        hood = r.get("neighborhoods_analysis_boundaries")
        body = f"{name} is a coffee shop / cafe at {addr}, San Francisco, CA {r.get('business_zip', '')}".strip()
        body += f" ({hood})." if hood else "."
        fact = Fact(kind="place", title=name, body=body, access="unknown", visibility="public", when=None,
                    neighborhood=hood, url=None)
        lon, lat = r["location"]["coordinates"]
        doc = fact.model_dump() | {"body_semantic": body, "owner": "datasf", "visibility": "public",
                                   "source_quote": f"DataSF g8m3-pdis {r['uniqueid']}", "status": "reported",
                                   "observed_at": now, "location": {"lat": lat, "lon": lon}}
        # Id from name + address so re-running the seed overwrites instead of duplicating.
        yield {"_index": INDEX, "_id": "place-" + hashlib.sha1("|".join(key).encode()).hexdigest()[:20], "_source": doc}


if __name__ == "__main__":
    items = list(docs(fetch()))
    ok, errs = helpers.bulk(es, items, chunk_size=100, request_timeout=120, raise_on_error=False)
    es.indices.refresh(index=INDEX)
    print(f"loaded {ok} coffee places ({len(errs)} errors)")
    r = es.search(index=INDEX, query={"bool": {"filter": [{"term": {"owner": "datasf"}}, {"match_phrase": {"title": "Reveille Coffee"}}]}}, source_excludes=["body_semantic"])
    print("Reveille found:", [(h["_source"]["title"], h["_source"]["body"]) for h in r["hits"]["hits"]])
