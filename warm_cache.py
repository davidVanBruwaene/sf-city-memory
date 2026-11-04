"""Pre-compute the demo blocks into the Elastic block-cache so the stage cards open in ~1s. Run: python warm_cache.py"""
import time

import block

DEMO = [("Mission St", "24th St"), ("Chestnut St", "Fillmore St"), ("Market St", "Powell St"), ("Bryant St", "24th St"),
        ("Stockton St", "Clay St"), ("Guerrero St", "19th St"), ("Guerrero St", "20th St")]

for st, cr in DEMO:
    t = time.time()
    out = block.block_facts(st, cr, fresh=True)
    print(f"{st} / {cr}: {'ERR ' + out['error'] if out.get('error') else out['nickname']} ({time.time() - t:.1f}s)")
