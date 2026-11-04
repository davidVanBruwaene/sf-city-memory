"""Web demo for "Your Block, Unfiltered": phone Wrapped cards at / and the projector room screen at /room.

Run: BLOCK_SOURCE=mock python web.py   (mock = sample data; BLOCK_SOURCE=real calls block.block_facts)
"""
import hashlib
import os
import threading
import time

from flask import Flask, jsonify, request, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.getenv("BLOCK_SOURCE", "mock")  # the one switch: "mock" or "real"
EXAMPLES = ["Mission St / 24th St", "Chestnut St / Fillmore St", "Guerrero St / 20th St"]
CHAT_EXAMPLES = ["How's Inner Sunset?", "Mission & 24th parking tomorrow morning?", "Loudest block in SF?"]
app = Flask(__name__, static_folder=None)
room, room_lock = {}, threading.Lock()
ROOM_INDEX = "block-room"
_es = None
if os.getenv("ELASTIC_ENDPOINT") and os.getenv("ELASTIC_API_KEY"):  # serverless: persist the room in ES so instances share it
    from elasticsearch import Elasticsearch
    _es = Elasticsearch(os.environ["ELASTIC_ENDPOINT"], api_key=os.environ["ELASTIC_API_KEY"])

MOCK = {
    "mission st": dict(lat=37.7524, lon=-122.4184, nickname="The Sidewalk Bazaar of the Mission", weirdness=9.2, facts=[
        dict(title="Sidewalk-sale violations", ratio=64.0, count=212, period="2 yrs", dataset="311 (vw6y-z8j6)",
             sentence="Your block gets 64x more sidewalk-sale complaints than the SF average.", rank=1),
        dict(title="Tow-away requests", ratio=14.5, count=88, period="2 yrs", dataset="311 (vw6y-z8j6)",
             sentence="14.5x more tow-away requests than the city.", rank=None),
        dict(title="Ornamental pear trees", ratio=9.1, count=31, period="all", dataset="Street trees (tkzw-k3nq)",
             sentence="31 ornamental pears: 9.1x the city's share.", rank=None)],
        sweeping=dict(schedule="Thu 6-8am (west side)", officer_usually_by="07:05", spread_min=5, weeks_seen=8, weeks_total=8)),
    "chestnut st": dict(lat=37.8004, lon=-122.4363, nickname="The Last Call of the Marina", weirdness=7.4, facts=[
        dict(title="Loud-music complaints", ratio=22.3, count=147, period="2 yrs", dataset="311 (vw6y-z8j6)",
             sentence="22.3x more noise complaints than the SF average.", rank=2),
        dict(title="Shoplifting reports", ratio=11.2, count=64, period="2 yrs", dataset="Police (wg3w-h783)",
             sentence="11.2x the city's rate of shoplifting reports.", rank=None),
        dict(title="London plane trees", ratio=8.4, count=40, period="all", dataset="Street trees (tkzw-k3nq)",
             sentence="40 London planes: 8.4x the city's share.", rank=None)],
        sweeping=None),
}
NICKS = ["The Cone Garden of {}", "Tow Zone Royale: {}", "{}: Home of the Mystery Mattress", "The Graffiti Gallery of {}",
         "Pigeon Parliament at {}"]
TITLES = ["Abandoned-vehicle reports", "Illegal-dumping reports", "Graffiti reports", "Noise complaints", "Tow-away requests"]


def mock_block(street, cross):
    key = street.lower().strip()
    if key in MOCK:
        b = dict(MOCK[key])
    else:  # deterministic fake so different addresses look different
        h = int(hashlib.md5(f"{street}/{cross}".encode()).hexdigest(), 16)
        facts = [dict(title=TITLES[(h >> (4 * i)) % 5], ratio=round(8 + (h >> (8 * i)) % 560 / 10, 1),
                      count=15 + (h >> (6 * i)) % 200, period="2 yrs", dataset="311 (vw6y-z8j6)", rank=None) for i in range(3)]
        for f in facts:
            f["sentence"] = f"{f['ratio']}x more {f['title'].lower()} than the SF average."
        b = dict(lat=37.74 + (h % 700) / 10000, lon=-122.47 + (h >> 12) % 700 / 10000,
                 nickname=NICKS[h % 5].format(street), weirdness=round(5 + (h >> 20) % 50 / 10, 1), facts=facts,
                 sweeping=dict(schedule="Tue 8-10am", officer_usually_by="08:23", spread_min=5, weeks_seen=7, weeks_total=8)
                 if h % 3 else None)
    b["address"] = f"{street} & {cross}, San Francisco" if cross else f"{street}, San Francisco"
    return b


WOW = [("Mission St", "24th St"), ("Chestnut St", "Fillmore St"), ("Market St", "6th St"), ("Bryant St", "24th St"),
       ("Stockton St", "Clay St")]
_full = {}  # (street, cross) lowercased -> finished block with the Mistral nickname; the 5 wow blocks are filled at startup


def _key(street, cross):
    return street.lower(), cross.lower()


def get_block(street, cross, fast=False):
    if SOURCE == "real":
        import block
        return block.block_facts(street, cross, fast=fast)
    return mock_block(street, cross)


def _prewarm():
    for st, cr in WOW:
        try:
            b = get_block(st, cr)
            if b and not b.get("error"):
                _full[_key(st, cr)] = b
        except Exception:
            pass


threading.Thread(target=_prewarm, daemon=True).start()


@app.get("/api/block")
def api_block():
    street = request.args.get("street", "").strip()
    cross = request.args.get("cross", "").strip()
    if not street:
        return jsonify(error="not_found", examples=EXAMPLES), 400
    fast = request.args.get("fast") == "1"
    try:
        b = _full.get(_key(street, cross))
        if b is None:
            b = get_block(street, cross, fast=fast)
            if not fast and b and not b.get("error"):
                _full[_key(street, cross)] = b
            elif fast and b and not b.get("error"):
                b = dict(b, pending=True)
    except Exception as e:  # keep the demo alive on any backend failure
        return jsonify(error="not_found", detail=str(e), examples=EXAMPLES), 502
    if not b or b.get("error"):
        return jsonify((b or {"error": "not_found"}) | {"examples": EXAMPLES}), 404
    top = b["facts"][0] if b.get("facts") else {}
    with room_lock:
        room[b["address"]] = dict(lat=b["lat"], lon=b["lon"], nickname=b["nickname"], weirdness=b["weirdness"],
                                  top_fact=f"{top.get('title', '')} {top.get('ratio', '')}x".strip(), ts=time.time())
        if _es:
            try:
                _es.index(index=ROOM_INDEX, id=b["address"], document=room[b["address"]], refresh=True)
            except Exception:
                pass
    return jsonify(b)


@app.get("/api/nickname")
def api_nickname():
    """Second step of the fast flow: the Mistral nickname and sentences for a block the numbers card already showed."""
    street = request.args.get("street", "").strip()
    cross = request.args.get("cross", "").strip()
    try:
        b = _full.get(_key(street, cross))
        if b is None:
            b = get_block(street, cross)
            if b and not b.get("error"):
                _full[_key(street, cross)] = b
        return jsonify(nickname=b["nickname"], sentences=[f["sentence"] for f in b["facts"]])
    except Exception:
        return jsonify(error="unavailable"), 502


@app.post("/api/chat")
def api_chat():
    history = (request.get_json(silent=True) or {}).get("messages") or []
    if not history or history[-1].get("role") != "user":
        return jsonify(error="Ask me about an SF neighborhood or block.", examples=CHAT_EXAMPLES), 400
    try:
        import area
        out = area.chat(history)
    except Exception:  # never break the page: answer with a friendly line
        out = {"error": "The AI guide is having trouble answering right now. Please try again in a moment."}
    return jsonify(out | {"examples": CHAT_EXAMPLES}), 200


@app.get("/api/room")
def api_room():
    with room_lock:
        if _es:
            try:
                hits = _es.search(index=ROOM_INDEX, size=200, sort="ts:asc")["hits"]["hits"]
                return _room_json([h["_source"] for h in hits])
            except Exception:
                pass
        blocks = sorted(room.values(), key=lambda x: x["ts"])
    return _room_json(blocks)


def _room_json(blocks):
    return jsonify(blocks=blocks, top5=sorted(blocks, key=lambda x: -x["weirdness"])[:5])


MEMORY_FIELDS = ["kind", "title", "body", "owner", "observed_at", "source_quote", "url", "neighborhood", "when", "access", "location"]


@app.get("/api/memory")
def api_memory():
    """City-memory items with a location inside bbox=west,south,east,north (public/community only, plus ?user='s own)."""
    global _es
    try:
        w, s, e, n = (float(x) for x in request.args.get("bbox", "").split(","))
    except ValueError:
        return jsonify(error="bad_bbox", items=[]), 400
    if _es is None:
        if not (os.getenv("ELASTIC_ENDPOINT") and os.getenv("ELASTIC_API_KEY")):
            return jsonify(items=[], note="no elastic configured")
        from elasticsearch import Elasticsearch
        _es = Elasticsearch(os.environ["ELASTIC_ENDPOINT"], api_key=os.environ["ELASTIC_API_KEY"])
    user = request.args.get("user", "")
    vis = [{"terms": {"visibility": ["public", "community"]}}] + ([{"term": {"owner": user}}] if user else [])
    q = {"bool": {"filter": [{"geo_bounding_box": {"location": {"top_left": {"lat": n, "lon": w}, "bottom_right": {"lat": s, "lon": e}}}},
                             {"bool": {"should": vis, "minimum_should_match": 1}}],
                  "must_not": [{"term": {"status": "superseded"}}]}}
    try:
        r = _es.search(index="city-memory", query=q, size=min(int(request.args.get("limit", 600)), 1000), source_includes=MEMORY_FIELDS)
    except Exception as ex:
        return jsonify(error="search_failed", detail=str(ex), items=[]), 502
    return jsonify(items=[h["_source"] | {"id": h["_id"]} for h in r["hits"]["hits"]])


SWEEP_FIELDS = ["corridor", "limits", "blockside", "weekday", "fromhour", "tohour", "weeks", "location", "cnn"]


def _client():
    global _es
    if _es is None and os.getenv("ELASTIC_ENDPOINT") and os.getenv("ELASTIC_API_KEY"):
        from elasticsearch import Elasticsearch
        _es = Elasticsearch(os.environ["ELASTIC_ENDPOINT"], api_key=os.environ["ELASTIC_API_KEY"])
    return _es


def _sweep_time(t):
    """t = 'HH:MM' (today, SF time) or 'YYYY-MM-DDTHH:MM'; default now."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("America/Los_Angeles")
    now = datetime.now(tz)
    if not t:
        return now
    if "T" in t:
        return datetime.fromisoformat(t).replace(tzinfo=tz)
    h, m = (int(x) for x in t.split(":"))
    return now.replace(hour=h, minute=m, second=0, microsecond=0)


@app.get("/api/sweep")
def api_sweep():
    """Street-cleaning blocks inside bbox=west,south,east,north, each with status at time t: now (cleaning), soon (<=2h), safe."""
    try:
        w, s, e, n = (float(x) for x in request.args.get("bbox", "").split(","))
        at = _sweep_time(request.args.get("t", ""))
    except ValueError:
        return jsonify(error="bad_request", items=[]), 400
    es = _client()
    if es is None:
        return jsonify(items=[], note="no elastic configured")
    day, wk, mins = at.strftime("%A"), (at.day - 1) // 7 + 1, at.hour * 60 + at.minute
    try:
        r = es.search(index="sf-street-sweeping", size=1500, source_includes=SWEEP_FIELDS, query={"bool": {"filter": [
            {"geo_bounding_box": {"location": {"top_left": {"lat": n, "lon": w}, "bottom_right": {"lat": s, "lon": e}}}},
            {"terms": {"weekday": [day, day[:3], day[:4]]}}, {"term": {"weeks": wk}}]}})
    except Exception as ex:
        return jsonify(error="search_failed", detail=str(ex), items=[]), 502
    items = []
    for h in r["hits"]["hits"]:
        b = h["_source"]
        a, z = b["fromhour"] * 60, b["tohour"] * 60
        status = "now" if a <= mins < z else "soon" if 0 < a - mins <= 120 else "safe"
        items.append({"id": h["_id"], "status": status, "lat": b["location"]["lat"], "lon": b["location"]["lon"], "street": b["corridor"],
                      "limits": b.get("limits"), "side": b.get("blockside"), "weekday": day, "from": b["fromhour"], "to": b["tohour"]})
    return jsonify(items=items, t=at.strftime("%a %H:%M"))


@app.get("/api/sweep/officer")
def api_sweep_officer():
    """Usual officer arrival for the block nearest lat,lon on this street. null when the ticket data isn't there or the pattern is thin."""
    try:
        street, day = request.args["street"], request.args["weekday"]
        loc = {"lat": float(request.args["lat"]), "lon": float(request.args["lon"])}
        from block import name_words
        from sweep_officer import es, officer_timing
        near = es.search(index="sf-sweep-tickets", size=1, sort=[{"_geo_distance": {"location": loc, "order": "asc"}}],
                         query={"wildcard": {"block_key": f"* {name_words(street)}*"}})["hits"]["hits"]
        return jsonify(officer=officer_timing(near[0]["_source"]["block_key"], day) if near else None)
    except Exception:
        return jsonify(officer=None)


@app.get("/sweep-layer.js")
def sweep_layer_js():
    return send_from_directory(os.path.join(HERE, "web"), "sweep-layer.js")


@app.get("/memory-map")
def memory_map_page():
    return send_from_directory(os.path.join(HERE, "web"), "memory-map.html")


@app.get("/memory-layer.js")
def memory_layer_js():
    return send_from_directory(os.path.join(HERE, "web"), "memory-layer.js")


@app.get("/")
def home():
    return send_from_directory(os.path.join(HERE, "web"), "memory-map.html")


@app.get("/card")
def phone():
    return send_from_directory(os.path.join(HERE, "web"), "index.html")


@app.get("/chat.js")
def chat_js():
    return send_from_directory(os.path.join(HERE, "web"), "chat.js")


@app.get("/room")
def room_page():
    return send_from_directory(os.path.join(HERE, "web"), "room.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
