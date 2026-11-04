"""Plant this week's public SF tech events, read off David's calendar on 2026-11-03, into the city memory."""
import citymem
from citymem import Fact

QUOTE = "Public events on David's calendar for the week of 2 November 2026"
EVENTS = [
    Fact(kind="event", title="Design Chat with Ian Silber",
         body="Design chat with Ian Silber, former Head of Product Design at OpenAI, at 380 Brannan St, San Francisco.",
         access="unknown", visibility="public", when="Wednesday 4 November 2026, about 4:30-6 PM",
         neighborhood="SoMa", url=None),
    Fact(kind="event", title="Omarchy SF",
         body="Omarchy SF meetup, hosted at Cloudflare's office, 101 Townsend St, San Francisco.",
         access="unknown", visibility="public", when="Wednesday 4 November 2026, 5:30-8:30 PM",
         neighborhood="SoMa", url=None),
    Fact(kind="event", title="GTM Series #03: Stevie Case (x-CRO Vanta)",
         body="Third session of a go-to-market talk series, with Stevie Case, former CRO of Vanta, "
              "at 363 Clementina St, San Francisco.",
         access="unknown", visibility="public", when="Thursday 5 November 2026, 6-8:30 PM",
         neighborhood="SoMa", url=None),
    Fact(kind="event", title="Founders GTM Coffee Meetup",
         body="Coffee meetup for founders about go-to-market, at Réveille Coffee, 200 Columbus Ave, San Francisco.",
         access="unknown", visibility="public", when="Friday 6 November 2026, 2-4 PM",
         neighborhood="North Beach", url=None),
]

if __name__ == "__main__":
    for f in EVENTS:
        citymem.remember("david", f, QUOTE, match=False)
        print(f"planted: {f.title} ({f.when})")
