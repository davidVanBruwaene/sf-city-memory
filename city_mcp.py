"""SF city MCP server: street cleaning (when to move your car), the shared city memory, and remembering what people say."""
import contextlib
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from mcp.server.mcpserver import MCPServer

import citymem
from sfhack import es

SF = ZoneInfo("America/Los_Angeles")
DAYS = {"Mon": 0, "Tues": 1, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
SUFFIXES = {"st", "street", "ave", "av", "avenue", "blvd", "boulevard", "rd", "road", "dr", "drive", "way", "pl",
            "place", "ct", "court", "ter", "terrace", "ln", "lane", "aly", "alley", "hwy", "highway"}
USER = os.getenv("CITY_USER", "guest")
server = MCPServer(name="sf-city", instructions=(
    "Local knowledge of San Francisco for residents and visitors: street-cleaning schedules (when to move your car) "
    "and a shared community memory of events, places to work, communities and tips that people contribute. "
    "Say who reported a memory entry and when. Ask before sharing anything the user tells you."))


def next_sweeps(weekday, weeks, start_h, end_h, now, n=2):
    # Week N is the Nth such weekday of the month, as printed on SF street-cleaning signs.
    out, day = [], now.date()
    for _ in range(70):
        if day.weekday() == DAYS.get(weekday, -1) and (day.day - 1) // 7 + 1 in weeks:
            midnight = datetime(day.year, day.month, day.day, tzinfo=SF)
            if midnight + timedelta(hours=end_h) > now:
                out.append((midnight + timedelta(hours=start_h), midnight + timedelta(hours=end_h)))
                if len(out) == n:
                    break
        day += timedelta(days=1)
    return out


def name_match(field, name):
    # Require every word but the suffix: the data writes "St" where people and models write "Street".
    words = [w for w in name.replace(".", " ").split() if w.lower() not in SUFFIXES] or name.split()
    return {"match": {field: {"query": " ".join(words), "operator": "and"}}}


@server.tool()
def street_cleaning(street: str, cross_street: str | None = None) -> str:
    """When is street cleaning on a San Francisco block, i.e. when must the user move their car. Give the street
    (e.g. 'Sutter St') and, if known, a nearby cross street to narrow it to the block. Returns each block side with
    its schedule and the next two cleanings from now (Pacific time)."""
    must = [name_match("corridor", street)]
    if cross_street:
        must.append(name_match("limits", cross_street))
    r = es.search(index="sf-street-sweeping", size=12, query={"bool": {"must": must}})
    now = datetime.now(SF)
    lines = [f"Now: {now:%a %b %d %-I:%M %p}"]
    for s in (h["_source"] for h in r["hits"]["hits"]):
        nxt = next_sweeps(s["weekday"], s["weeks"], s["fromhour"], s["tohour"], now)
        when = "; ".join(f"{a:%a %b %d} {a:%-I %p}-{b:%-I %p}" for a, b in nxt) or "none in the next 10 weeks"
        side = f", {s['blockside']} side" if s.get("blockside") else ""
        lines.append(f"{s['corridor']} ({s['limits']}){side}: {s['fullname']}, "
                     f"{s['fromhour']}:00-{s['tohour']}:00. Next: {when}")
    near = f" near {cross_street}" if cross_street else ""
    return "\n".join(lines) if len(lines) > 1 else f"No street-cleaning schedule found for {street}{near}."


def soql(dataset, params):
    r = requests.get(f"https://data.sf.gov/resource/{dataset}.json", params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def counted(rows, key):
    total = sum(int(x["n"]) for x in rows)
    top = ", ".join(f"{(x.get(key) or 'unspecified').split('::')[-1].strip()} {x['n']}" for x in rows[:5])
    return total, top


@server.tool()
def about_block(street: str, cross_street: str) -> str:
    """Tell the user about a San Francisco block they live or are staying on: its street trees, what people reported
    to 311 nearby in the last 30 days (both live from DataSF) and its street-cleaning schedule. Give the street and a
    cross street at one end of the block."""
    r = es.search(index="sf-street-sweeping", size=1, query={"bool": {"must": [
        name_match("corridor", street), name_match("limits", cross_street)]}})
    if not r["hits"]["hits"]:
        return f"No block found for {street} near {cross_street}."
    b = r["hits"]["hits"][0]["_source"]
    lat, lon = b["location"]["lat"], b["location"]["lon"]
    out = [f"Block: {b['corridor']} between {b['limits']} (around {lat:.5f}, {lon:.5f})"]
    try:
        # Trees carry the same centerline id (cnn) as the street-cleaning block, so this is the exact block.
        total, top = counted(soql("tkzw-k3nq", {"$select": "species, count(*) AS n", "$where": f"cnn='{b['cnn']}'",
                                                "$group": "species", "$order": "n DESC"}), "species")
        out.append(f"Street trees on this block: {total}" + (f" ({top})" if total else ""))
    except Exception as e:
        out.append(f"Street trees: unavailable ({type(e).__name__})")
    try:
        since = (datetime.now(SF) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
        total, top = counted(soql("vw6y-z8j6", {
            "$select": "service_name, count(*) AS n", "$group": "service_name", "$order": "n DESC",
            "$where": f"within_circle(point, {lat}, {lon}, 120) AND requested_datetime > '{since}'"}), "service_name")
        out.append(f"311 reports within 120 m in the last 30 days: {total}" + (f" ({top})" if total else ""))
    except Exception as e:
        out.append(f"311 reports: unavailable ({type(e).__name__})")
    out.append("Street cleaning:\n" + street_cleaning(street, cross_street))
    return "\n".join(out)


@server.tool()
def ask_city(question: str) -> str:
    """Ask the San Francisco city memory: events, places to work, communities, people and tips that residents and
    visitors have contributed, plus the user's own private notes (where they parked, their garbage day). Mistral writes
    a short cited brief from the entries Elastic finds; the entries follow so you can check it."""
    with contextlib.redirect_stdout(sys.stderr):
        hits = citymem.retrieve(USER, question)
        if not hits:
            return "Nothing in the city memory matches that yet."
        brief = citymem.answer(USER, question, hits)
    return (f"Brief by Mistral ({citymem.MODEL}) from {len(hits)} entries Elastic found:\n{brief}\n\n"
            f"Entries:\n{citymem.format_entries(hits)}")


@server.tool()
def ask_area(question: str) -> str:
    """Ask about a San Francisco neighborhood or block in plain words ("How's Inner Sunset?", "loudest block in SF?"):
    Mistral answers from numbers computed on DataSF and names each dataset."""
    import area
    out = area.chat([{"role": "user", "content": question}])
    return out.get("reply") or out.get("error", "No answer.")


@server.tool()
def remember(note: str, share: bool = True) -> str:
    """Add what the user told you about San Francisco (an event, a place, a community, a tip, a change to something
    already known) to the shared city memory. Call only after the user agreed to share it; share=False keeps it
    private to them, e.g. where they parked or their garbage day. Mistral extracts the facts and decides whether each
    updates an existing entry, then merges it."""
    with contextlib.redirect_stdout(sys.stderr):
        t = citymem.chat("parse", citymem.MODEL, response_format=citymem.Turn, messages=[
            {"role": "system", "content": citymem.EXTRACT}, {"role": "user", "content": note},
        ]).choices[0].message.parsed
        out = []
        for fact in t.facts:
            if not share:
                fact.visibility = "personal"
            replaced = citymem.remember(USER, fact, note)
            out.append(f"stored [{fact.kind}/{fact.access}/{fact.visibility}] {fact.title}"
                       + (f", replacing the earlier report '{replaced}'" if replaced else ""))
    return "\n".join(out) or "Nothing concrete to remember in that."


if __name__ == "__main__":
    server.run("stdio")
