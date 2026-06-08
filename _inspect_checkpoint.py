"""Quick script to inspect checkpoint data."""
import json

c = json.load(open("output/dynamic_checkpoint.json", encoding="utf-8"))
print(f"Last batch: {c['last_batch_completed']}")
print(f"Species classified: {len(c['assignments'])}")
print(f"Groups created: {len(c['groups'])}")
print(f"Tokens used: {c['total_tokens']}")
print()
for gid, g in sorted(c["groups"].items()):
    n = len(g.get("species", []))
    print(f"  {gid}: {g['group_name']} | {g.get('habitat','?')}, {g.get('trophic_level','?')}, {g.get('size_class','?')} | {n} spp")
    for sp in g.get("species", [])[:5]:
        print(f"      - {sp}")
    if n > 5:
        print(f"      ... (+{n-5} more)")
