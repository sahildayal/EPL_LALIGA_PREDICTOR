"""Regenerate the GitHub Pages dashboard under docs/.

Reads only committed state (season_ledger.json + matchweek_logs/), so it is safe
to run any time and reconstructs the same site from the same history.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.site import build_site  # noqa: E402


def main() -> int:
    out = build_site(Path(__file__).resolve().parents[1])
    pages = sorted(p.name for p in out.glob("*.html"))
    print(f"built {len(pages)} page(s) in {out}")
    for name in pages:
        print(f"  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
