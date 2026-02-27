"""
check_symbols.py — Diagnostic script to find correct Upstox symbol names.

Run this once to see how Upstox names your stocks:
  cd backend
  python check_symbols.py

This will print the exact tradingsymbol for each stock in your universe.
"""

import io
import requests
import pandas as pd
from universe import get_universe, get_universe_names

print("Downloading Upstox NSE instrument master...")
url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.csv.gz"
resp = requests.get(url, timeout=30)
df = pd.read_csv(
    io.BytesIO(resp.content),
    compression="gzip",
    usecols=["tradingsymbol", "instrument_key", "instrument_type", "name"],
)
eq = df[df["instrument_type"] == "EQ"]

print(f"Loaded {len(eq)} NSE EQ instruments\n")

# Check every symbol in every universe
all_symbols = set()
for name in get_universe_names():
    for t in get_universe(name):
        all_symbols.add(t.replace(".NS", "").replace(".BO", ""))

print(f"{'Symbol':<20} {'Status':<10} {'Upstox Key'}")
print("-" * 70)

missing = []
for sym in sorted(all_symbols):
    match = eq[eq["tradingsymbol"] == sym]
    if not match.empty:
        key = match.iloc[0]["instrument_key"]
        print(f"{sym:<20} {'✓ FOUND':<10} {key}")
    else:
        # Try case-insensitive search
        close = eq[eq["tradingsymbol"].str.upper() == sym.upper()]
        if not close.empty:
            actual = close.iloc[0]["tradingsymbol"]
            key = close.iloc[0]["instrument_key"]
            print(f"{sym:<20} {'~ CASE':<10} actual='{actual}' key={key}")
            missing.append((sym, actual))
        else:
            # Try partial match
            partial = eq[
                eq["tradingsymbol"].str.contains(f"^{sym}", case=False, na=False)
            ]
            if not partial.empty:
                suggestions = partial["tradingsymbol"].tolist()[:3]
                print(f"{sym:<20} {'? PARTIAL':<10} suggestions: {suggestions}")
            else:
                print(f"{sym:<20} {'✗ MISSING':<10} not found in Upstox master")
            missing.append((sym, None))

print(f"\n{len(missing)} symbols need attention:")
for sym, actual in missing:
    if actual:
        print(f"  {sym} → rename to '{actual}' in india_stocks.py")
    else:
        print(f"  {sym} → not available on Upstox")
