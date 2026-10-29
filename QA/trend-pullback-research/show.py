import json, sys
rows = [json.loads(l) for f in sys.argv[1:] for l in open(f)]
key = lambda r: (r["TR"][2] or -9)
for r in sorted(rows, key=key, reverse=True)[:int(__import__("os").environ.get("TOP", 15))]:
    f = lambda p: f"n={p[0]} w={p[1]} e={p[2]} tot={p[3]} pf={p[4]} dd={p[5]}"
    print(f"{r['name'][:48]:48s} | TR {f(r['TR'])} | VA {f(r['VA'])} | HO {f(r['HO'])} | {r['yp']}")
