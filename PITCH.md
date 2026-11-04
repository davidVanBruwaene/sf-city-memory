# SF City Memory: pitch and demo

**People come and go. The city remembers.**

## Setup

1. `sf-city` is registered with Claude Code for this folder:
   `claude mcp add --transport stdio --scope local sf-city --env CITY_USER=david -- <repo>/.venv/bin/python <repo>/city_mcp.py`
2. Start a **new** Code session in this folder. A running session keeps the server code it started with.
3. Allow each `sf-city` tool the first time Claude uses it.

Claude Desktop chat: `connect_claude.py` adds the server while Claude is closed, because Claude rewrites its config from memory while it runs. This route has not yet been seen working.

## Demo flow: type these

1. `I'm staying on Sutter St near Gough. Tell me about my block.`
   `about_block` reports 32 street trees (Brisbane Box, Banyan Fig, Southern Magnolia) and 36 reports to 311 within 120 m in the last 30 days, mostly street and sidewalk cleaning. It also gives the street-cleaning schedule.
2. `Do I need to move my car this week?`
   The north side is cleaned Thu Nov 5, 7-9 AM. The south side is cleaned only on the 1st and 3rd Tuesdays, next on Tue Nov 17, 8-10 AM.
3. `I'm in SF until Friday for AI and startup stuff. What's worth going to this week?`
   `ask_city` returns Mistral's brief, with citations, covering the hack night, Elastic{ON}, the Design Chat, Omarchy, the GTM Series and the Founders coffee.
4. `Add this to the city memory: tonight's hack night is officially "Make SF Better: A Hack Night with Mistral AI". Pitches are 2 minutes at 7:30, finalists at 8, prizes at 8:30, judged on novelty, use of Elastic and use of Mistral.`
   Approve `remember`. It should say it replaced the earlier hack night report.
5. `What time are prizes tonight, and how are we judged?`
   The answer comes from the merged entry: it keeps the 5:00 PM start and credits the organisers as first reporter and you as the updater.

## Two minutes

- **0:00 Problem.** Your chatbot knows everything except your block: when to move your car, what the street is like, what's on this week, what a neighbour said yesterday.
- **0:20 What it is.** An MCP server any assistant can plug into. Claude is the front end tonight; the city lives in Elastic and Mistral keeps it.
- **0:35 Demo.** Prompts 1 to 5.
- **1:35 Under the hood.**
  - **Elastic:** 37,878 street-cleaning block sides from DataSF, each with a location, which also places a block for live street-tree and 311 lookups. A city-memory index whose `semantic_text` field is embedded by `mistral-embed` through an Elastic inference endpoint. Hybrid BM25 plus semantic retrieval fused with RRF, and a visibility filter so private notes stay private.
  - **Mistral (`mistral-large-4`):** turns what people say into structured entries, decides whether a report updates an existing entry and merges it, and writes the cited brief that Claude receives.
- **1:50 Close.** Garbage pickup isn't open data, so the memory holds it: tell it once and it remembers.
