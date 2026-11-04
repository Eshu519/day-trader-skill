import json
with open(r'C:\Users\Eshwar\Projects\day-trader-skill\trader\watchlist.json', 'r') as f:
    d = json.load(f)
hits = d.get('hits', [])
print(f'Total hits: {len(hits)}')
# Sort by volume
hits_sorted = sorted(hits, key=lambda h: h.get('volume', 0), reverse=True)
for h in hits_sorted[:15]:
    vol = h.get('volume', 0)
    print(f"{h['symbol']:20s}  {h['price']:>10.2f}  RSI {h['rsi']:>5.1f}  Vol {vol:>12,}  {h['setups']}")