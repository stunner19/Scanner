"""
refresh_universe_fallback.py — Re-fetch NSE index constituent CSVs and update
the bundled fallback snapshots in universe/fallback/.

Why this exists: NSE frequently blocks/rate-limits requests from cloud
datacenter IPs (Render included), so the live scanner can't always reach it.
When that happens, universe/india_stocks.py falls back to these bundled,
git-tracked CSVs instead of returning an empty universe. This script keeps
those snapshots from going stale — it's meant to run on a schedule (see
.github/workflows/refresh-universe-fallback.yml), from a runner whose IP
NSE isn't blocking.

Run:
  cd backend
  python refresh_universe_fallback.py

Exits non-zero if every index failed to fetch (so CI can flag it), but a
partial failure (some indices still reachable) still updates what it can
and exits 0.
"""

import sys
import logging

from universe.india_stocks import _CSV_FILES, _fallback_path, fetch_raw_csv, _parse_constituents

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


def main() -> int:
    ok, failed = 0, []

    for index_name in _CSV_FILES:
        text = fetch_raw_csv(index_name)
        if not text:
            log.warning(f"{index_name}: fetch failed — leaving existing snapshot untouched")
            failed.append(index_name)
            continue

        symbols = _parse_constituents(text, index_name)
        if not symbols:
            log.warning(f"{index_name}: fetched but parsed 0 symbols — leaving existing snapshot untouched")
            failed.append(index_name)
            continue

        path = _fallback_path(index_name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        log.info(f"{index_name}: updated ({len(symbols)} symbols) -> {path}")
        ok += 1

    log.info(f"Done — {ok}/{len(_CSV_FILES)} indices updated" + (f", {len(failed)} failed: {failed}" if failed else ""))
    return 1 if ok == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
