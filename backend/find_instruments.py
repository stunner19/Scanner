"""
find_instruments.py — Diagnose exact instrument_type values and find correct symbols.
Run: python find_instruments.py
"""

import io
import requests
import pandas as pd
from universe import get_universe, get_universe_names

print("Downloading Upstox instrument master...")
url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.csv.gz"
resp = requests.get(url, timeout=30)
df = pd.read_csv(io.BytesIO(resp.content), compression="gzip")

print(f"\nTotal rows: {len(df)}")
print(f"Columns: {df.columns.tolist()}")
print(f"\nAll instrument_type values and counts:")
print(df["instrument_type"].value_counts().to_string())

print(f"\nSample rows for each instrument_type:")
for itype in df["instrument_type"].unique():
    sample = df[df["instrument_type"] == itype]["tradingsymbol"].head(5).tolist()
    print(f"  {itype}: {sample}")

# Try finding RELIANCE regardless of type
print(f"\n--- RELIANCE in ALL types ---")
print(
    df[df["tradingsymbol"] == "RELIANCE"][
        ["tradingsymbol", "instrument_type", "instrument_key"]
    ].to_string()
)

print(f"\n--- WIPRO in ALL types ---")
print(
    df[df["tradingsymbol"] == "WIPRO"][
        ["tradingsymbol", "instrument_type", "instrument_key"]
    ].to_string()
)

print(f"\n--- TCS in ALL types ---")
print(
    df[df["tradingsymbol"] == "TCS"][
        ["tradingsymbol", "instrument_type", "instrument_key"]
    ].to_string()
)
