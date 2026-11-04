"""When does the street-cleaning ticket officer usually reach a block? From the first ticket of each week (sf-sweep-tickets)."""
import os
import statistics
from pathlib import Path

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

load_dotenv(Path(__file__).with_name(".env"))
es = Elasticsearch(os.environ["ELASTIC_ENDPOINT"], api_key=os.environ["ELASTIC_API_KEY"])
INDEX = "sf-sweep-tickets"
WEEKS_TOTAL = 10  # the window ingest_tickets.py loads
MIN_WEEKS, MAX_SPREAD_MIN = 4, 10
DAYS = {d[:3].lower(): d for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")}


def officer_timing(block_key, weekday):
    """{"officer_usually_by": "07:05", ...} or None when the pattern is too thin or too scattered to promise."""
    day = DAYS.get(weekday[:3].lower())
    if not day:
        return None
    resp = es.search(index=INDEX, size=0, query={"bool": {"filter": [
        {"term": {"block_key": block_key.upper()}}, {"term": {"weekday": day}}]}}, aggs={
        "weeks": {"date_histogram": {"field": "issued_ts", "calendar_interval": "week", "min_doc_count": 1},
                  "aggs": {"first": {"min": {"field": "minute_of_day"}}}}})
    firsts = [int(b["first"]["value"]) for b in resp["aggregations"]["weeks"]["buckets"]]
    if len(firsts) < MIN_WEEKS:
        return None
    spread = max(firsts) - min(firsts)
    if spread > MAX_SPREAD_MIN:
        return None
    m = round(statistics.median(firsts))
    return {"officer_usually_by": f"{m // 60:02d}:{m % 60:02d}", "spread_min": spread,
            "weeks_seen": len(firsts), "weeks_total": WEEKS_TOTAL}


if __name__ == "__main__":
    import sys
    key, day = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("900 GUERRERO ST", "Thursday")
    print(key, day, officer_timing(key, day))
