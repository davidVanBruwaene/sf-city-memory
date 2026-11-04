"""Load the last 10 weeks of street-cleaning tickets (DataSF ab4h-6ztd, 'STR CLEAN') into Elasticsearch."""
import hashlib
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv
from elasticsearch import Elasticsearch, helpers

load_dotenv(Path(__file__).with_name(".env"))
es = Elasticsearch(os.environ["ELASTIC_ENDPOINT"], api_key=os.environ["ELASTIC_API_KEY"])

INDEX = "sf-sweep-tickets"
URL = "https://data.sf.gov/resource/ab4h-6ztd.json"
WEEKS = 10
MAPPINGS = {"properties": {
    "block_key": {"type": "keyword"}, "weekday": {"type": "keyword"}, "issued_ts": {"type": "date"},
    "minute_of_day": {"type": "integer"}, "location": {"type": "geo_point"},
}}


def block_key(address):
    """'918 GUERRERO ST' -> '900 GUERRERO ST'; None when the address has no street number."""
    m = re.match(r"\s*(\d+)\s+(.+?)\s*$", address or "")
    return f"{int(m[1]) // 100 * 100} {m[2].upper()}" if m else None


def docs(rows):
    for r in rows:
        key, ts = block_key(r.get("citation_location")), r.get("citation_issued_datetime")
        if not key or not ts:
            continue
        t = datetime.fromisoformat(ts)  # local SF time
        lat, lon = r.get("latitude"), r.get("longitude")
        yield {"_index": INDEX, "_id": hashlib.md5(r["citation_number"].encode()).hexdigest(), "_source": {
            "block_key": key, "weekday": t.strftime("%A"), "issued_ts": ts, "minute_of_day": t.hour * 60 + t.minute,
            "location": {"lat": float(lat), "lon": float(lon)} if lat and lon else None}}


if __name__ == "__main__":
    since = (datetime.now() - timedelta(weeks=WEEKS)).strftime("%Y-%m-%dT00:00:00")
    rows, offset = [], 0
    while True:
        page = requests.get(URL, params={"$where": f"violation_desc='STR CLEAN' AND citation_issued_datetime>='{since}'",
                                         "$order": "citation_number", "$limit": 50000, "$offset": offset}, timeout=180).json()
        rows += page
        if len(page) < 50000:
            break
        offset += 50000
    print(f"fetched {len(rows)} tickets since {since[:10]}")
    es.indices.delete(index=INDEX, ignore_unavailable=True)
    es.indices.create(index=INDEX, mappings=MAPPINGS)
    ok, errors = helpers.bulk(es, docs(rows), chunk_size=2000, raise_on_error=False)
    es.indices.refresh(index=INDEX)
    print(f"indexed {ok}, errors {len(errors)}, count {es.count(index=INDEX)['count']}")
