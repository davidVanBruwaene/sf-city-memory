"""Shared clients for the hack: loads .env and exposes `es` and `mistral`. Run directly to check both."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from mistralai.client import Mistral

load_dotenv(Path(__file__).with_name(".env"))

ELASTIC_ENDPOINT = os.getenv("ELASTIC_ENDPOINT", "")
ELASTIC_API_KEY = os.getenv("ELASTIC_API_KEY", "")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
TOKEN_511 = os.getenv("TOKEN_511", "")

es = Elasticsearch(ELASTIC_ENDPOINT, api_key=ELASTIC_API_KEY) if ELASTIC_ENDPOINT and ELASTIC_API_KEY else None
mistral = Mistral(api_key=MISTRAL_API_KEY) if MISTRAL_API_KEY else None


def check():
    ok = True
    if es is None:
        print("elastic: NOT SET - fill ELASTIC_ENDPOINT and ELASTIC_API_KEY in .env")
        ok = False
    else:
        try:
            v = es.info()["version"]
            print(f"elastic: ok, {v.get('build_flavor', '?')} {v['number']} at {ELASTIC_ENDPOINT}")
        except Exception as e:
            print(f"elastic: FAILED {type(e).__name__}: {e}")
            ok = False
    if mistral is None:
        print("mistral: NOT SET - fill MISTRAL_API_KEY in .env")
        ok = False
    else:
        try:
            r = mistral.chat.complete(
                model="mistral-small-latest",
                messages=[{"role": "user", "content": "Reply with the single word: ready"}],
                max_tokens=5,
            )
            print(f"mistral: ok, mistral-small-latest replied {r.choices[0].message.content!r}")
        except Exception as e:
            print(f"mistral: FAILED {type(e).__name__}: {e}")
            ok = False
    return ok


if __name__ == "__main__":
    sys.exit(0 if check() else 1)
