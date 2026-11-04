"""Scripted demo of the city memory: press Enter to run each step, so the pitch never waits on typing."""
import json
import sys

import citymem

# Edit these lines to match the seeded data; each turn may both answer and contribute.
STEPS = [
    ("What the city remembers", "stats", None),
    ("A visiting founder asks", "david", "I'm in SF until Thursday working on agent governance, on a tight budget. "
                                         "Where can I work for free near other agent builders, and what's worth going to?"),
    ("A local mentions an update in passing", "maya", "REPLACE: a real update to one seeded entry, plus one new tip"),
    ("The visitor asks again", "david", "What should I do on Thursday?"),
    ("Behind the scenes", "explain", None),
    ("Every entry, including personal and replaced ones", "show", None),
]


def explain():
    print("Elasticsearch index mapping (body_semantic is embedded by Mistral through an Elastic inference endpoint):")
    print(json.dumps(citymem.MAPPINGS["properties"]["body_semantic"]))
    ep = citymem.es.inference.get(inference_id=citymem.EMBED_ID)["endpoints"][0]
    print(f"\nInference endpoint {ep['inference_id']}: service={ep['service']}, model={ep['service_settings'].get('model')}")
    print("\nRetrieval: RRF hybrid of BM25 (title, body) + semantic (body_semantic), filtered by visibility:")
    print(json.dumps(citymem.visible_to("david")))
    print(f"\nMistral: {citymem.MODEL} extracts question + facts (structured output), judges whether a new report "
          "updates an old one and merges them, and writes the cited answer; mistral-embed embeds every entry.")


def main():
    if citymem.es is None or citymem.mistral is None:
        sys.exit("fill .env first, then check it with: python sfhack.py")
    for title, who, text in STEPS:
        input(f"\n=== {title} [Enter] ")
        if who in ("stats", "show"):
            getattr(citymem, who)()
        elif who == "explain":
            explain()
        else:
            print(f"{who}> {text}")
            citymem.turn(who, text)


if __name__ == "__main__":
    main()
