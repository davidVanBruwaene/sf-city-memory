"""Load SF's street-cleaning schedule (DataSF yhqp-riqs, ~38k blocks) into Elasticsearch."""
import requests
from elasticsearch import helpers

from sfhack import es

INDEX = "sf-street-sweeping"
URL = "https://data.sf.gov/resource/yhqp-riqs.json"
MAPPINGS = {"properties": {
    "corridor": {"type": "text", "fields": {"raw": {"type": "keyword"}}},
    "limits": {"type": "text"}, "blockside": {"type": "keyword"}, "cnnrightleft": {"type": "keyword"},
    "cnn": {"type": "keyword"}, "fullname": {"type": "keyword"}, "weekday": {"type": "keyword"},
    "fromhour": {"type": "integer"}, "tohour": {"type": "integer"}, "weeks": {"type": "integer"},
    "holidays": {"type": "boolean"}, "location": {"type": "geo_point"},
}}


def docs(rows):
    for r in rows:
        coords = (r.get("line") or {}).get("coordinates") or []
        mid = coords[len(coords) // 2] if coords else None
        yield {"_index": INDEX, "_source": {
            "corridor": r.get("corridor"), "limits": r.get("limits"), "blockside": r.get("blockside"),
            "cnnrightleft": r.get("cnnrightleft"), "cnn": r.get("cnn"), "fullname": r.get("fullname"),
            "weekday": r.get("weekday"), "fromhour": int(r.get("fromhour") or 0), "tohour": int(r.get("tohour") or 0),
            "weeks": [i for i in range(1, 6) if r.get(f"week{i}") == "1"], "holidays": r.get("holidays") == "1",
            "location": {"lon": mid[0], "lat": mid[1]} if mid else None,
        }}


if __name__ == "__main__":
    rows = requests.get(URL, params={"$limit": 60000}, timeout=180).json()
    print(f"fetched {len(rows)} rows")
    es.indices.delete(index=INDEX, ignore_unavailable=True)
    es.indices.create(index=INDEX, mappings=MAPPINGS)
    ok, errors = helpers.bulk(es, docs(rows), chunk_size=2000, raise_on_error=False)
    es.indices.refresh(index=INDEX)
    print(f"indexed {ok}, errors {len(errors)}, count {es.count(index=INDEX)['count']}")
