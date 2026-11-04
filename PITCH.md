# SF City Memory: pitch and demo

**People come and go. The city remembers.**

## Setup (once)

1. In Terminal.app (not the terminal inside Claude), run `.venv/bin/python connect_claude.py` from this folder.
   It quits Claude, adds `sf-city` to `claude_desktop_config.json` and reopens Claude. Claude rewrites that file
   from memory while it runs, so an edit made with Claude open is lost.
2. New chat, then + and Connectors: `sf-city` should be listed, with `street_cleaning`, `ask_city` and `remember`.
   Click "Always allow" the first time each tool runs.

## Type these into Claude

1. `I'm parked on Sutter St near Gough. Do I need to move my car this week?`
   Expect the north side Thu Nov 5, 7-9 AM, and the south side (Gough-Octavia) Tue Nov 17, 8-10 AM, because it is the 1st and 3rd Tuesdays only.
2. `I'm in SF until Friday for AI and startup stuff. What's worth going to this week?`
   Expect Mistral's brief, with citations, covering the hack night, Elastic{ON}, the Design Chat, Omarchy, the GTM Series and the Founders coffee.
3. `Add this to the city memory: tonight's hack night is officially "Make SF Better: A Hack Night with Mistral AI". Pitches are 2 minutes at 7:30, finalists at 8, prizes at 8:30, judged on novelty, use of Elastic and use of Mistral.`
   Say yes if Claude asks to share it. Expect "replacing the earlier report 'Elastic x Mistral SF Hack Night'".
4. `What time are prizes tonight, and how are we judged?`
   The answer now comes from the merged entry, marked as replacing an older report.
5. Optional, for private memory: `Remember just for me: my garbage goes out Thursday morning.` Then, in a new chat, ask `What do I need to do Thursday?`

## Two minutes

- **0:00 Problem.** Your chatbot knows everything except your block: when to move your car, what's on this week, what a neighbour said yesterday.
- **0:20 What it is.** An MCP server any assistant can plug into. Claude is the front end tonight; the city lives in Elastic and Mistral keeps it.
- **0:35 Demo.** Prompts 1 to 4.
- **1:35 Under the hood.**
  - **Elastic:** 37,878 street-cleaning block sides from DataSF. A city-memory index whose `semantic_text` field is embedded by `mistral-embed` through an Elastic inference endpoint. Hybrid BM25 plus semantic retrieval fused with RRF, and a visibility filter so private notes stay private.
  - **Mistral (`mistral-large-4`):** turns what people say into structured entries, decides whether a report updates an existing entry and merges it, and writes the cited brief that Claude receives.
- **1:50 Close.** Garbage pickup isn't open data, so the memory holds it: tell it once and it remembers.
