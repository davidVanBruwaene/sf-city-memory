# SF City Memory

*People come and go. The city remembers.*

SF City Memory is an MCP server that makes a chatbot know San Francisco. It tells you when to move your car for street cleaning and what is worth going to this week. It also lets people add what they know, so the next person's chatbot knows it too. It was built at the Elastic x Mistral SF Hack Night ("Make SF Better"), whose challenge was to build something that makes life in SF better for someone who lives here.

- Code: https://github.com/davidVanBruwaene/sf-city-memory
- State as of 3 November 2026.

## What a user can ask their chatbot

| user says | what happens |
|---|---|
| "I'm staying on Sutter St near Gough. Tell me about my block." | Street trees on the block, recent 311 reports nearby and the street-cleaning schedule |
| "I'm parked on Sutter St near Gough. Do I need to move my car this week?" | The next street cleaning for each side of that block |
| "I'm in SF until Friday for AI and startup stuff. What's worth going to this week?" | A short brief from the city memory, citing its entries |
| "Add this to the city memory: ..." | Stored for everyone. A report about something already known updates that entry instead of duplicating it |
| "Remember just for me: my garbage goes out Thursday morning." | A private note that only this user's chatbot can see |

## How it fits together

```
Chat client (Claude Desktop, Claude Code, Mistral Vibe, or any MCP client)
  -> sf-city MCP server (Python, stdio): city_mcp.py
       -> Elasticsearch Serverless 9.7
            sf-street-sweeping: 37,878 block sides from DataSF
            city-memory: shared knowledge, embedded by mistral-embed
       -> Mistral API: mistral-large-4 extracts, matches, merges and writes briefs
       -> DataSF API, live: street trees and 311 reports for about_block
```

- **The chat client** holds the conversation.
- **Elastic** holds the city's knowledge.
- **Mistral** maintains that knowledge and writes the brief the client receives.

Elastic calls `mistral-embed` itself through an inference endpoint, so the server has no embedding code.

## Tools

| tool | input | returns |
|---|---|---|
| `street_cleaning` | `street`, optional `cross_street` | Up to 12 matching block sides, each with its schedule and the next two cleanings from now (Pacific time) |
| `about_block` | `street`, `cross_street` | The block's street trees and the 311 reports within 120 m in the last 30 days (both live from DataSF), plus its street cleaning |
| `ask_city` | `question` | A brief written by `mistral-large-4` that cites entries as [n], followed by the entries with who reported each one and when |
| `remember` | `note`, `share` (default true) | What was stored, and which earlier report it replaced, if any. `share=false` keeps the note private |

The server acts as one user, set by the `CITY_USER` environment variable (default `guest`). There is no authentication beyond that.

## Street cleaning

- **Source.** DataSF dataset `yhqp-riqs` (Street Sweeping Schedule), https://data.sf.gov/resource/yhqp-riqs.json. `ingest_sweeping.py` loads it into the `sf-street-sweeping` index.
- **Documents.** Each document is one side of one block: the street (`corridor`), the cross streets it runs between (`limits`), the block side, weekday, start and end hour, weeks of the month (1-5), a holidays flag, and a `geo_point` at the block's midpoint.
- **Week rule.** Week N means the Nth such weekday of the month, as on SF street signs ("Tue 1st & 3rd"). The tool computes the next two dates from that rule, looking up to 10 weeks ahead.
- **Matching.** Suffix words (St, Street, Ave, Blvd and so on) are dropped first, because the data writes "St" where people write "Street". Every remaining word of the street must match `corridor`, and every remaining word of the cross street must match `limits`, so a cross street filters to the blocks that touch it.
- **Not handled yet.**
  - Holiday exceptions: the flag is stored but not applied.
  - Lookup by location: no tool finds a block from coordinates or an address. `about_block` uses the stored point only to centre its 311 search on a block found by name.
- **Garbage pickup.** DataSF has no garbage-collection dataset, so garbage days go in as private notes.

## About a block

`about_block` finds the block in `sf-street-sweeping` from the street and cross street, then queries DataSF live:

- **Street trees** (`tkzw-k3nq`), counted by species. They are matched on the block's centerline id (`cnn`), which the tree inventory shares with the street-cleaning data. A count of 0 can also mean the inventory files that block's trees under another segment.
- **311 reports** (`vw6y-z8j6`) within 120 m of the block's midpoint in the last 30 days, counted by service.

## City memory

**Entry fields:**
- `kind`: event, place, community, person or tip
- `title`, `body`
- `access`: free, paid, approval or unknown
- `visibility`: public, community or personal
- `when`, `neighborhood`, `url`
- `owner`, `source_quote`
- `status`: reported or superseded
- `supersedes`, `observed_at`
- `first_owner`, `first_observed_at`: the original reporter, kept when updates merge into the entry

**Retrieval.**
- Hybrid search fuses two queries with the RRF retriever: keyword search (BM25 over title, boosted, and body) and semantic search over `body_semantic`. If RRF fails, it uses semantic search alone.
- A filter drops superseded entries. It keeps public and community entries, plus the asking user's own entries, including their private ones.

**Adding.** `mistral-large-4` extracts facts from the note as structured output. It is told never to invent, and to leave access unknown unless the note states it.

**Updating:**
1. For each new fact, Elastic finds the 3 nearest entries.
2. Only entries of the same kind and the same sharing class stay candidates. A private note can only replace the same owner's private notes, so it can never hide a shared entry.
3. `mistral-large-4` picks the candidate that is the very same thing, or none when unsure.
4. On a match, Mistral merges the old entry and the new report field by field (title, body, when, neighborhood, url), keeping every older detail the report does not change. The merged entry keeps the first reporter in `first_owner` and `first_observed_at`, points to the old one with `supersedes`, and the old one is marked superseded. Nothing is deleted.

**Answering.** `mistral-large-4` writes the brief from the retrieved entries only. For each entry it cites, it gives the access as recorded (never inferred from the body), who first reported it, who updated it and how long ago. It flags entries older than 60 days and says when an entry replaced an older report.

## Where Elastic and Mistral are used

**Elastic**
- A `semantic_text` field backed by the inference endpoint `mistral-embeddings` (service mistral, model mistral-embed)
- Hybrid retrieval with the RRF retriever
- Permission filtering in the query: visibility, owner, superseded
- 37,878 street-cleaning documents, each with a location
- Block lookup for `about_block`, whose stored location centres the 311 search
- Terms aggregations for memory stats (`python citymem.py stats`)

**Mistral**
- `mistral-embed` embeds every memory entry, called through Elastic.
- `mistral-large-4`, with `reasoning_effort="low"`:
  - structured extraction
  - same-entry judgement
  - merging updates
  - cited briefs

## What is in the memory now

| event | when | where |
|---|---|---|
| Elastic x Mistral SF Hack Night | Tue 3 Nov 2026, 5-8:30 PM | 33 New Montgomery St |
| Elastic{ON} SF 2026 | Wed 4 Nov 2026 | not recorded |
| Design Chat with Ian Silber (former Head of Product Design, OpenAI) | Wed 4 Nov, about 4:30-6 PM (time estimated from a calendar view) | 380 Brannan St |
| Omarchy SF | Wed 4 Nov, 5:30-8:30 PM | Cloudflare, 101 Townsend St |
| GTM Series #03: Stevie Case (former CRO, Vanta) | Thu 5 Nov, 6-8:30 PM | 363 Clementina St |
| Founders GTM Coffee Meetup | Fri 6 Nov, 2-4 PM | Réveille Coffee, 200 Columbus Ave |

The organisers reported the first two entries and David the other four. Access is recorded as unknown for all six.

## Running it

1. Create the environment: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in `ELASTIC_ENDPOINT`, `ELASTIC_API_KEY` and `MISTRAL_API_KEY`. `python sfhack.py` checks both connections.
3. `python citymem.py setup` creates the inference endpoint and the `city-memory` index.
4. `python ingest_sweeping.py` loads the street-cleaning data.
5. Seed the memory:
   - `python citymem.py say organisers @seed/tonight.md --yes`
   - `python seed_week.py`
6. Connect a client. `<repo>` is the path to the clone.
   - **Claude Desktop.** Add this under `mcpServers` in `~/Library/Application Support/Claude/claude_desktop_config.json`:
     `"sf-city": {"command": "<repo>/.venv/bin/python", "args": ["<repo>/city_mcp.py"], "env": {"CITY_USER": "<name>"}}`
     - Claude Desktop rewrites that file from memory while it runs, so add the entry with the app closed. This route has not yet been seen working.
     - `connect_claude.py` does this for you: it quits Claude, adds the entry and reopens Claude. Double-clicking `Connect sf-city to Claude.command` runs it.
     - It sets `CITY_USER` to `david`; edit `ENTRY` in that script for another user.
   - **Claude Code** (the route seen working): `claude mcp add --transport stdio --scope local sf-city --env CITY_USER=<name> -- <repo>/.venv/bin/python <repo>/city_mcp.py`, run from the repo folder. Start a new session afterwards; a running session keeps the server code it started with.
   - **Mistral Vibe:** `vibe mcp add sf-city --transport stdio --command <repo>/.venv/bin/python --arg <repo>/city_mcp.py --env CITY_USER=<name>`
     - Registering works. A full Vibe chat through the server has not been verified.

## Constraints and known limits

- **Mistral free tier.** These models work:
  - `mistral-large-4`
  - `ministral-8b-latest`
  - `ministral-14b-2512`
  - `mistral-embed`

  These are refused:
  - `mistral-small` and `mistral-medium` (HTTP 429, code 1300)
  - `mistral-large-2512` (HTTP 403)

  The server retries 429 responses with backoff.
- **Reasoning model.** `mistral-large-4` replies contain thinking chunks, and `reasoning_effort="low"` is its minimum.
- **Mistral calls per tool.**
  - `ask_city`: one call.
  - `remember`: one extraction call, plus up to two per fact (match and merge), so it is the slowest tool.
- **Identity.** It is an environment variable, not authentication.
- **Relevance.** Retrieval always returns the top 8 entries, and Mistral's brief decides which are relevant.

## Files

| file | what it is |
|---|---|
| `city_mcp.py` | The MCP server, with 4 tools |
| `citymem.py` | The city memory (mappings, retrieval, extraction, matching, merging, answering) and a CLI: `setup`, `chat`, `say`, `show`, `stats`, `reset` |
| `ingest_sweeping.py` | Loads DataSF street cleaning into Elastic |
| `seed_week.py`, `seed/tonight.md` | Seed entries |
| `sfhack.py` | Shared Elastic and Mistral clients, `.env` loading and a connection check |
| `connect_claude.py`, `Connect sf-city to Claude.command` | Connect the server to Claude Desktop |
| `PITCH.md` | Demo prompts and the two-minute pitch |
| `demo.py` | An earlier scripted terminal demo of the memory |
| Notebooks and guides | The organisers' starter material: BART, Muni, 311 and other DataSF examples |
