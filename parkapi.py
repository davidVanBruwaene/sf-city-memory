""""Can I park here?" GET /api/park?lat=&lon=&t= -> a big YES / MOVE BY / NO for the block side nearest the tap.

The sentence is a template (no Mistral): fast, and it says exactly what the schedule says.
"""
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from flask import Blueprint, jsonify, request, send_from_directory

try:
    from city_mcp import next_sweeps
except Exception:  # city_mcp needs the mcp + mistral packages; keep the API up without them
    def next_sweeps(weekday, weeks, start_h, end_h, now, n=2):
        days = {"Mon": 0, "Tues": 1, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
        out, day = [], now.date()
        for _ in range(70):
            if day.weekday() == days.get(weekday, -1) and (day.day - 1) // 7 + 1 in weeks:
                midnight = datetime(day.year, day.month, day.day, tzinfo=SF)
                if midnight + timedelta(hours=end_h) > now:
                    out.append((midnight + timedelta(hours=start_h), midnight + timedelta(hours=end_h)))
                    if len(out) == n:
                        break
            day += timedelta(days=1)
        return out

SF = ZoneInfo("America/Los_Angeles")
HERE = os.path.dirname(os.path.abspath(__file__))
NEAR_M = 60  # farther than this from any posted block = no street cleaning here
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DIRS = {"North": (1, 0), "South": (-1, 0), "East": (0, 1), "West": (0, -1)}
bp = Blueprint("park", __name__)


def _es():
    from sweep_officer import es
    return es


def parse_t(t):
    """'' = now; 'YYYY-MM-DDTHH:MM'; 'HH:MM' today; 'Wed 06:30' = the next Wednesday (today if it is one)."""
    now = datetime.now(SF).replace(second=0, microsecond=0)
    t = (t or "").strip()
    if not t:
        return now
    if re.match(r"\d{4}-\d{2}-\d{2}T", t):
        return datetime.fromisoformat(t).replace(tzinfo=SF)
    day, _, hm = t.rpartition(" ")
    h, m = (int(x) for x in hm.split(":"))
    at = now.replace(hour=h, minute=m)
    if day:
        at += timedelta(days=(WEEKDAYS.index(day[:3].lower()) - now.weekday()) % 7)
    return at


def _when(d, at):
    days = (d.date() - at.date()).days
    day = "today" if days == 0 else "tomorrow" if days == 1 else f"{d:%a}"
    return f"{d:%-I:%M %p} {day}" if days < 2 else f"{day} {d:%-I:%M %p}"


def _side_score(side, dlat, dlon):
    return sum(DIRS[k][0] * dlat + DIRS[k][1] * dlon for k in DIRS if k in (side or ""))


def _officer(corridor, loc, weekday):
    try:
        from block import name_words
        from sweep_officer import officer_timing
        near = _es().search(index="sf-sweep-tickets", size=1, sort=[{"_geo_distance": {"location": loc, "order": "asc"}}],
                            query={"wildcard": {"block_key": f"* {name_words(corridor)}*"}})["hits"]["hits"]
        return officer_timing(near[0]["_source"]["block_key"], weekday) if near else None
    except Exception:
        return None


def _lines(cnns):
    """Block-side polylines from DataSF for the map highlight; [] if it is slow or down."""
    try:
        where = " OR ".join(f"cnn='{c}'" for c in cnns)
        rows = requests.get("https://data.sf.gov/resource/yhqp-riqs.json",
                            params={"$select": "cnn,blockside,line", "$where": where, "$limit": 50}, timeout=3).json()
        seen, out = set(), []
        for r in rows:
            k = (r.get("cnn"), r.get("blockside"))
            if k not in seen and r.get("line"):
                seen.add(k)
                out.append({"side": r.get("blockside"), "coords": [[y, x] for x, y in r["line"]["coordinates"]]})
        return out
    except Exception:
        return []


def verdict(lat, lon, at):
    es = _es()
    loc = {"lat": lat, "lon": lon}
    first = es.search(index="sf-street-sweeping", size=1, sort=[{"_geo_distance": {"location": loc, "order": "asc", "unit": "m"}}],
                      query={"geo_distance": {"distance": f"{NEAR_M}m", "location": loc}})["hits"]["hits"]
    if not first:
        return {"status": "none", "headline": "No posted street cleaning nearby", "detail": "Still check the signs for meters, permits and red curbs."}
    b = first[0]["_source"]
    rows = [h["_source"] for h in es.search(index="sf-street-sweeping", size=40, query={"bool": {"filter": [
        {"term": {"corridor.raw": b["corridor"]}}, {"geo_distance": {"distance": "40m", "location": b["location"]}}]}})["hits"]["hits"]]
    sides = {}
    for r in rows:
        if r["weekday"] == "Holiday":
            continue
        s = sides.setdefault(r.get("blockside") or "Both", {"side": r.get("blockside") or "Both", "sweeps": [], "cnn": r["cnn"],
                                                            "lat": r["location"]["lat"], "lon": r["location"]["lon"]})
        s["sweeps"] += next_sweeps(r["weekday"], r["weeks"], r["fromhour"], r["tohour"], at, n=2)
    for s in sides.values():
        s["sweeps"] = sorted(set(s["sweeps"]))
        a, z = s["sweeps"][0] if s["sweeps"] else (None, None)
        s["status"] = "none" if a is None else "now" if a <= at < z else "soon" if a - at <= timedelta(hours=24) else "yes"
        s["until"] = z if s["status"] == "now" else a
    dlat, dlon = lat - b["location"]["lat"], (lon - b["location"]["lon"]) * 0.79  # cos(37.8°)
    mine = max(sides.values(), key=lambda s: _side_score(s["side"], dlat, dlon))
    if mine["status"] == "now":
        head = f"No: street cleaning now (until {mine['until']:%-I:%M %p})"
    elif mine["status"] == "soon":
        head = f"Move by {_when(mine['until'], at)}"
    elif mine["status"] == "yes":
        head = f"Yes, until {mine['until']:%a %-I:%M %p}"
    else:
        head = "Yes, no cleaning in the next 10 weeks"
    out = {"status": mine["status"], "headline": head, "street": b["corridor"], "limits": b.get("limits"), "side": mine["side"],
           "t": at.strftime("%a %b %-d %-I:%M %p"),
           "next": [f"{a:%a %b %-d} {a:%-I:%M}-{z:%-I:%M %p}" for a, z in mine["sweeps"][:2]], "sides": [], "officer": None, "other": None}
    if mine["sweeps"]:
        nxt = mine["sweeps"][0][0]
        off = _officer(b["corridor"], b["location"], nxt.strftime("%A"))
        if off:
            out["officer"] = off | {"line": f"🚓 Officer usually by {off['officer_usually_by']} ({off['weeks_seen']} of {off['weeks_total']} weeks)"}
    rank = {"now": 0, "soon": 1, "yes": 2, "none": 3}
    for s in sides.values():
        out["sides"].append({"side": s["side"], "status": s["status"]})
        if s is not mine and (rank[s["status"]] > rank[mine["status"]] or (s["status"] == mine["status"] == "yes" and s["until"] > mine["until"])):
            out["other"] = f"{s['side']} side is safe until {s['until']:%a %-I:%M %p}" if s["until"] else f"{s['side']} side has no cleaning soon"
    lines = _lines({s["cnn"] for s in sides.values()})
    for ln in lines:
        ln["status"] = sides.get(ln["side"], {}).get("status", "none")
    out["lines"] = lines
    return out


@bp.get("/api/park")
def api_park():
    try:
        lat, lon = float(request.args["lat"]), float(request.args["lon"])
        at = parse_t(request.args.get("t", ""))
    except (KeyError, ValueError):
        return jsonify(error="bad_request", hint="lat, lon and optional t ('Wed 06:30' or 'YYYY-MM-DDTHH:MM')"), 400
    try:
        return jsonify(verdict(lat, lon, at))
    except Exception as ex:
        return jsonify(error="lookup_failed", detail=str(ex)), 502


@bp.get("/park.js")
def park_js():
    return send_from_directory(os.path.join(HERE, "web"), "park.js")
