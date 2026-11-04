"""Ask about an SF neighborhood or block in chat: Mistral calls tools that compute numbers from DataSF and Elastic,
answers only from those numbers with their datasets, and returns map places for the web map to fly to."""
import contextlib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import requests

import block
import citymem
from block import BY_CATEGORY, INDEX, VIOLENT, city, es, per_dataset

SENSITIVE = re.compile(r"missing|found person|mental|welfare|death|overdose|drug|narcotic|warrant|prostitut", re.I)

MODEL = "mistral-large-4"
NHOOD_RADIUS_M, NHOOD_MIN_RATIO = 600, 1.5
EXAMPLES = ["How's Inner Sunset?", "Mission & 24th parking tomorrow morning?", "Loudest block in SF?"]
# Well-known blocks the rankings compare; "loudest" counts distinct addresses reporting noise, so one
# neighbour filing hundreds of reports does not make a block loud.
CANDIDATES = {"Market St & 6th St": (37.7810, -122.4100), "Chestnut St & Fillmore St": (37.8007, -122.4361),
              "Van Ness Ave & O'Farrell St": (37.7848, -122.4210), "Valencia St & 16th St": (37.7650, -122.4220),
              "Polk St & Broadway": (37.7958, -122.4214), "Columbus Ave & Broadway": (37.7979, -122.4066),
              "Folsom St & 11th St": (37.7718, -122.4136), "Mission St & 24th St": (37.7524, -122.4184),
              "Haight St & Ashbury St": (37.7701, -122.4469), "Irving St & 9th Ave": (37.7641, -122.4663),
              "Clement St & 6th Ave": (37.7831, -122.4642), "Castro St & 18th St": (37.7609, -122.4350)}
TOPICS = {"noise": "service_name='Noise'", "graffiti": "service_name like 'Graffiti%'",
          "dumping": "service_name='Street and Sidewalk Cleaning'", "parking": "service_name='Parking Enforcement'",
          "encampments": "service_name='Encampments'"}
SYSTEM = (
    "You are the San Francisco guide of 'Your Block, Unfiltered'. Answer questions about SF neighborhoods and blocks "
    "by calling the tools, then reply in 3-6 short, friendly sentences in the user's language. Use only numbers the "
    "tools returned, never invent or round one into a new number, and name the dataset after each fact like "
    "(311 vw6y-z8j6). For a neighborhood give at least three of its facts with their ratios. For parking, give the street-cleaning times for "
    "the day asked about (today is {today}, Pacific time) and say none applies if so, then add the block's unusual facts. If a place is not found, say so "
    "kindly and suggest one of: " + "; ".join(EXAMPLES) + ". Never blame people.")
TOOLS = [
    {"type": "function", "function": {"name": "block_facts", "description": (
        "What is unusual on one SF block compared with the whole city (311, police incidents, street trees), "
        "plus a nickname. Use for a corner like 'Mission & 24th'."), "parameters": {"type": "object", "properties": {
            "street": {"type": "string", "description": "e.g. 'Mission St'"},
            "cross": {"type": "string", "description": "cross street, e.g. '24th St'"}}, "required": ["street", "cross"]}}},
    {"type": "function", "function": {"name": "neighborhood_facts", "description": (
        "What stands out in an SF neighborhood (e.g. 'Inner Sunset', 'Mission', 'Marina') compared with the city: "
        f"311 reports and police incidents within {NHOOD_RADIUS_M} m of its center in the past year."),
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "street_cleaning", "description": (
        "Street-cleaning schedule of a block and its next two cleanings: when the user must move their car."),
        "parameters": {"type": "object", "properties": {"street": {"type": "string"}, "cross": {"type": "string"}},
                       "required": ["street"]}}},
    {"type": "function", "function": {"name": "rank_blocks", "description": (
        "Rank well-known SF blocks by a 311 topic over the past year, e.g. the loudest block in SF. Topics: "
        + ", ".join(TOPICS) + "."), "parameters": {"type": "object", "properties": {
            "topic": {"type": "string", "enum": list(TOPICS)}}, "required": ["topic"]}}},
    {"type": "function", "function": {"name": "ask_city", "description": (
        "Search the shared SF community memory (events, places to work, communities, tips residents added)."),
        "parameters": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}}},
]
_nhoods = {}


def soql(dataset, **params):
    r = requests.get(f"https://data.sf.gov/resource/{dataset}.json", params={f"${k}": v for k, v in params.items()},
                     timeout=30)
    r.raise_for_status()
    return r.json()


def nhoods():
    # Center of each SF Analysis Neighborhood: the mean of its outline's points is close enough for a 600 m circle.
    if not _nhoods:
        for row in soql("j2bu-swwd", select="nhood, the_geom", limit=100):
            pts = [p for poly in row["the_geom"]["coordinates"] for p in poly[0]]
            _nhoods[row["nhood"]] = (sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts))
    return _nhoods


def find_nhood(name):
    key = re.sub(r"[^a-z]", "", name.lower())
    for n, c in nhoods().items():
        parts = [re.sub(r"[^a-z]", "", p.lower()) for p in [n, *n.split("/")]]
        if key and any(key == p or (len(key) > 3 and key in p) for p in parts):
            return n, c
    return None, None


def neighborhood_facts(name):
    n, c = find_nhood(name)
    if not n:
        return {"error": "not_found", "known": sorted(nhoods())}
    lat, lon = c
    # Same ratio as block.py, over the same Elastic index, in a wider circle.
    here = per_dataset(es.search(index=INDEX, size=0, aggs=BY_CATEGORY, query={
        "geo_distance": {"distance": f"{NHOOD_RADIUS_M}m", "location": {"lat": lat, "lon": lon}}}))
    base, facts, totals = city(), [], {}
    for ds, label in [("311", "311 (vw6y-z8j6)"), ("police", "SFPD incidents (wg3w-h783)"), ("trees", "Street trees (tkzw-k3nq)")]:
        cats, total = here.get(ds, ({}, 0))
        everywhere, city_total = base.get(ds, ({}, 0))
        totals[f"{label} within {NHOOD_RADIUS_M} m"] = total
        for cat, k in cats.items():
            if k >= 15 and everywhere.get(cat) and not VIOLENT.search(cat) and not SENSITIVE.search(cat):
                ratio = round((k / total) / (everywhere[cat] / city_total), 1)
                if ratio >= NHOOD_MIN_RATIO:
                    name = cat.split("::")[-1].strip() if ds == "trees" else cat.replace("_", " ").strip().capitalize()
                    title = f"{name} trees" if ds == "trees" else block.TITLES.get(name, name)
                    facts.append(dict(title=title, ratio=ratio, count=k, period="all" if ds == "trees" else "1 yr",
                                      dataset=label))
    facts = sorted(facts, key=lambda f: -f["ratio"])[:5]
    return dict(neighborhood=n, lat=round(lat, 5), lon=round(lon, 5), radius_m=NHOOD_RADIUS_M, totals=totals,
                facts=facts, note="ratio = times the city's share of that report type")


def street_cleaning(street, cross=None):
    import city_mcp  # imported late: it starts the MCP server object, which only this tool needs
    # A parking question is about a block, so the block's own facts and map pin come along.
    with ThreadPoolExecutor(1) as ex:
        facts = ex.submit(block.block_facts, street, cross or "")
        out = {"schedule": city_mcp.street_cleaning(street, cross), "dataset": "Street sweeping schedule (yhqp-riqs)"}
        try:
            b = facts.result()
            if not b.get("error"):
                out["block"] = b
        except Exception:
            pass
    return out


def rank_blocks(topic):
    where = TOPICS.get(topic, TOPICS["noise"])
    since = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%dT00:00:00")

    def one(item):
        name, (lat, lon) = item
        r = soql("vw6y-z8j6", select="count(distinct address) AS a",
                 where=f"within_circle(point, {lat}, {lon}, 200) AND requested_datetime > '{since}' AND {where}")[0]
        return dict(block=name, lat=lat, lon=lon, addresses_reporting=int(r["a"]))

    with ThreadPoolExecutor(12) as ex:
        rows = sorted(ex.map(one, CANDIDATES.items()), key=lambda x: -x["addresses_reporting"])
    return dict(topic=topic, ranked_by="distinct addresses with a report within 200 m, past year",
                compared=f"{len(rows)} well-known blocks", dataset="311 (vw6y-z8j6)", ranking=rows[:5],
                note="the first entry is the answer")


def ask_city(question):
    with contextlib.redirect_stdout(sys.stderr):
        hits = citymem.retrieve("guest", question)
        if not hits:
            return {"answer": "Nothing in the city memory matches that yet."}
        return {"brief": citymem.answer("guest", question, hits), "dataset": "SF city memory (Elastic)"}


def run_tool(name, args):
    try:
        if name == "block_facts":
            out = block.block_facts(args.get("street", ""), args.get("cross", ""))
        elif name == "neighborhood_facts":
            out = neighborhood_facts(args.get("name", ""))
        elif name == "street_cleaning":
            out = street_cleaning(args.get("street", ""), args.get("cross"))
        elif name == "rank_blocks":
            out = rank_blocks(args.get("topic", "noise"))
        elif name == "ask_city":
            out = ask_city(args.get("question", ""))
        else:
            out = {"error": f"unknown tool {name}"}
    except Exception as e:
        out = {"error": f"{type(e).__name__}: {e}"[:300]}
    return out


def text_of(c):
    return c if isinstance(c, str) else "".join(getattr(x, "text", "") for x in (c or []) if getattr(x, "type", "") == "text")


def chat(history):
    """history: [{role: user|assistant, content}]. Returns {reply, places, sources, block, neighborhood} or {error}."""
    from block import mistral
    if mistral is None:
        return {"error": "The AI guide is offline right now (no Mistral key). Try the block search instead."}
    today = datetime.now().strftime("%A %B %d %Y")
    msgs = [{"role": "system", "content": SYSTEM.format(today=today)}]
    msgs += [{"role": m["role"], "content": str(m["content"])[:2000]} for m in history[-12:]
             if m.get("role") in ("user", "assistant") and m.get("content")]
    places, sources, card, hood = [], [], None, None
    for _ in range(5):
        r = None
        for attempt in range(4):
            try:
                r = mistral.chat.complete(model=MODEL, reasoning_effort="low", messages=msgs, tools=TOOLS,
                                          tool_choice="auto")
                break
            except Exception as e:
                if getattr(e, "status_code", None) != 429 or attempt == 3:
                    return {"error": "The AI guide is having trouble answering right now. Please try again in a moment."}
                time.sleep(2 * (attempt + 1))
        m = r.choices[0].message
        if not m.tool_calls:
            return dict(reply=text_of(m.content).strip(), places=places, sources=sorted(set(sources)), block=card,
                        neighborhood=hood)
        msgs.append({"role": "assistant", "content": text_of(m.content), "tool_calls": [
            {"id": t.id, "type": "function", "function": {"name": t.function.name, "arguments": t.function.arguments}}
            for t in m.tool_calls]})
        for t in m.tool_calls:
            a = t.function.arguments
            args = json.loads(a) if isinstance(a, str) else (a or {})
            out = run_tool(t.function.name, args)
            if isinstance(out, dict) and not out.get("error"):
                if t.function.name == "block_facts":
                    card = out
                    places.append(dict(lat=out["lat"], lon=out["lon"], label=out["address"].removesuffix(", San Francisco")))
                    sources += [f["dataset"] for f in out["facts"]]
                elif t.function.name == "neighborhood_facts":
                    hood = out
                    places.append(dict(lat=out["lat"], lon=out["lon"], label=out["neighborhood"], radius=NHOOD_RADIUS_M))
                    sources += [f["dataset"] for f in out["facts"]] or ["311 (vw6y-z8j6)"]
                elif t.function.name == "rank_blocks":
                    top = out["ranking"][0]
                    places.append(dict(lat=top["lat"], lon=top["lon"], label=top["block"]))
                    sources.append(out["dataset"])
                elif t.function.name == "street_cleaning" and out.get("block"):
                    card = out["block"]
                    places.append(dict(lat=card["lat"], lon=card["lon"], label=card["address"].removesuffix(", San Francisco")))
                    sources += [out["dataset"]] + [f["dataset"] for f in card["facts"]]
                elif out.get("dataset"):
                    sources.append(out["dataset"])
            msgs.append({"role": "tool", "name": t.function.name, "tool_call_id": t.id,
                         "content": json.dumps(out, default=str)[:6000]})
    return {"error": "The AI guide got lost in the data. Try asking about one place, e.g. " + EXAMPLES[0]}


if __name__ == "__main__":
    print(json.dumps(chat([{"role": "user", "content": " ".join(sys.argv[1:]) or EXAMPLES[0]}]), indent=1, default=str))
