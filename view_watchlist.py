import json
f = open(r'C:\Users\Eshwar\Projects\day-trader-skill\trader\watchlist.json')
d = json.load(f)
print('Mode:', d.get('mode'))
print('Date:', d.get('date'))
print('Hits:', len(d.get('hits', [])))
for h in d.get('hits', [])[:20]:
    print(f"{h['symbol']:20s}  {h['price']:>10.2f}  RSI {h['rsi']:>5.1f}  {h['setups']}")