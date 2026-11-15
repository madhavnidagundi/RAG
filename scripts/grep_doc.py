"""Print parsed-text passages matching a regex (helper for writing gold passages)."""
import json, re, sys
doc, pat = sys.argv[1], sys.argv[2]
width = int(sys.argv[3]) if len(sys.argv) > 3 else 400
t = json.load(open(f"corpus/parsed/{doc}.json", encoding="utf-8"))["text"]
for m in list(re.finditer(pat, t, re.I))[:6]:
    print(f"--- @{m.start()}: ...{t[max(0,m.start()-80):m.start()+width]}...\n")
