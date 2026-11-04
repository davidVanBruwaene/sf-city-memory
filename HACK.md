# Hack workspace

Clone of the organisers' repo, kept as the `upstream` remote: `git pull upstream main` picks up anything they push during the night.

## Setup (once)

1. Elastic: [sign up for Cloud Serverless](https://ela.st/sign-up), create a project, then Connection details: copy the endpoint and create an API key.
2. Mistral: [redeem the event credits](https://admin.mistral.ai/subscription/upgrade/redeem?redeem_code=MISTRAL%3C3SF) (code `MISTRAL<3SF`), then create an API key.
3. Paste the values into `.env` (gitignored).
4. `.venv/bin/python sfhack.py` prints ok or FAILED for each service.

## Use

- Notebooks: `.venv/bin/jupyter lab`. In a notebook, replace the 🔑 credentials cell with `from sfhack import es, mistral, ELASTIC_ENDPOINT, ELASTIC_API_KEY, MISTRAL_API_KEY` so no key is saved into the `.ipynb`.
- Scripts: `from sfhack import es, mistral`.

## City memory skeleton (optional)

`citymem.py`: Mistral parses each chat turn into a question plus proposed facts. You approve each fact (or keep it personal), it is stored in Elasticsearch with its owner, quote and timestamp, and a newer report about the same thing replaces the older one. Questions go through hybrid search (BM25 + `semantic_text` on Mistral embeddings via an Elastic inference endpoint), filtered so personal entries reach only their owner, then a cited Mistral answer with access type and report age.

```
.venv/bin/python citymem.py setup                            # inference endpoint + index
.venv/bin/python citymem.py say cofounder @notes.md --yes    # seed from your cofounder's notes
.venv/bin/python citymem.py chat david                       # ask and tell in the same breath
.venv/bin/python citymem.py show | stats | reset
```

## Timeline

Build 5:30 to 7:30 PM. 2-minute pitch at 7:30: who it helps, what it does, and show both the Elastic part (queries, mappings) and the Mistral part. Finalists give 3 minutes at 8:00.
Judged on novelty, use of Elastic, use of Mistral. UI is not judged.
