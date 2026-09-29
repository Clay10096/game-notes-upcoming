#!/usr/bin/env python3
"""Check that the standalone static directory can be published as-is."""
from __future__ import annotations

import json
from pathlib import Path

from common import ROOT, SourceError
from exchange import validate_rates
from scrape_upcoming import validate_snapshot


def main():
    site = ROOT / "site"
    for relative in ("index.html", "styles.css", "favicon.svg", "common.js",
                     "upcoming.js", "upcoming-logic.js", "_headers"):
        path = site / relative
        if not path.is_file() or not path.stat().st_size:
            raise SourceError(f"Missing publish file: {relative}")
    html = (site / "index.html").read_text(encoding="utf-8")
    if "游戏发售笔记" not in html or "./upcoming.js" not in html:
        raise SourceError("Standalone homepage is incomplete")
    counts = {}
    for platform, store in (("ns2", "nintendo"), ("ps5", "playstation")):
        for region in ("hk", "jp", "us"):
            stem = f"upcoming-{platform}-{region}"
            snapshot = validate_snapshot(json.loads((site / "data" / f"{stem}.json").read_text()))
            if snapshot["store"] != store or snapshot["region"] != region.upper():
                raise SourceError(f"Incorrect snapshot identity: {stem}")
            counts[stem] = snapshot["gameCount"]
            status = json.loads((site / "data" / f"{stem}.status.json").read_text())
            if status.get("status") not in ("success", "failed"):
                raise SourceError(f"Invalid source status: {stem}")
    validate_rates(json.loads((site / "data/fx.json").read_text()))
    print("Publish directory: site/ (no build step)")
    for stem, count in counts.items():
        print(f"{stem}: {count} games")


if __name__ == "__main__":
    main()
