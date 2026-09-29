#!/usr/bin/env python3
"""Save ECB reference rates for CNY estimates in the upcoming-games site."""
import argparse
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from common import Client, ROOT, SourceError, atomic_json

ECB_XML = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
ECB_PAGE = "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html"
NAMESPACE = "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"
CURRENCIES = ("USD", "JPY", "HKD")


def quote_date(value, today=None):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise SourceError("Invalid exchange rate date")
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise SourceError("Invalid exchange rate date") from exc
    if result > (today or datetime.now(timezone.utc).date()):
        raise SourceError("Future exchange rate date")
    return result


def parse_rates(raw, today=None):
    # Only the official small daily document is expected; never expand entities.
    if len(raw) > 100_000 or "<!DOCTYPE" in raw.upper() or "<!ENTITY" in raw.upper():
        raise SourceError("Unexpected exchange rate XML")
    try:
        tree = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise SourceError("Expected ECB exchange rate XML") from exc
    days = tree.findall(f".//{{{NAMESPACE}}}Cube[@time]")
    if len(days) != 1:
        raise SourceError("Expected one daily exchange rate quote")
    quoted = quote_date(days[0].get("time"), today)
    rates = {}
    for row in days[0].findall(f"{{{NAMESPACE}}}Cube"):
        currency = row.get("currency")
        if currency not in (*CURRENCIES, "CNY"):
            continue
        try:
            rate = Decimal(row.get("rate", ""))
        except InvalidOperation as exc:
            raise SourceError("Invalid ECB currency rate") from exc
        if currency in rates or not rate.is_finite() or rate <= 0:
            raise SourceError("Invalid or duplicate ECB currency rate")
        rates[currency] = rate
    if set(rates) != {*CURRENCIES, "CNY"}:
        raise SourceError("Missing ECB currency rate")
    return quoted.isoformat(), {currency: float(rates["CNY"] / rates[currency]) for currency in CURRENCIES}


def validate_rates(snapshot, today=None):
    if not isinstance(snapshot, dict) or snapshot.get("schemaVersion") != 1 or snapshot.get("status") != "success" or snapshot.get("targetCurrency") != "CNY":
        raise SourceError("Invalid exchange rate metadata")
    quote_date(snapshot.get("quoteDate"), today)
    try:
        updated = datetime.fromisoformat(snapshot["updatedAt"])
        if updated.tzinfo is None:
            raise ValueError("Missing time zone")
    except (KeyError, TypeError, ValueError) as exc:
        raise SourceError("Invalid exchange rate completion time") from exc
    rates = snapshot.get("rates")
    if not isinstance(rates, dict) or set(rates) != set(CURRENCIES) or any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0
        for value in rates.values()
    ):
        raise SourceError("Invalid CNY conversion rates")
    return snapshot


def refresh(directory, client=None):
    directory = Path(directory)
    client = client or Client()
    path = directory / "fx.json"
    previous = None
    if path.exists():
        try:
            previous = validate_rates(json.loads(path.read_text()))
        except (SourceError, ValueError):
            pass
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        quoted, rates = parse_rates(client.request(ECB_XML, headers={"Accept": "application/xml"}))
        if previous and quoted < previous["quoteDate"]:
            raise SourceError("Exchange rate date moved backwards")
        snapshot = {"schemaVersion": 1, "status": "success", "targetCurrency": "CNY",
                    "quoteDate": quoted, "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "rates": rates, "source": {"name": "European Central Bank", "url": ECB_PAGE, "feed": ECB_XML}}
        validate_rates(snapshot)
        atomic_json(path, snapshot)
        atomic_json(directory / "fx.status.json", {"status": "success", "attemptedAt": started,
                    "completedAt": snapshot["updatedAt"], "lastSuccessAt": snapshot["updatedAt"], "error": None})
        return snapshot
    except Exception as exc:
        atomic_json(directory / "fx.status.json", {"status": "failed", "attemptedAt": started,
                    "completedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "lastSuccessAt": previous["updatedAt"] if previous else None,
                    "error": f"{type(exc).__name__}: {exc}"[:500]})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "site/data")
    args = parser.parse_args()
    try:
        snapshot = refresh(args.output)
        print(f'ECB reference rates: {snapshot["quoteDate"]}; CNY per currency: {snapshot["rates"]}')
    except Exception as exc:
        print(f"FAILED exchange rates: {exc}. Previous rates were preserved.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
