"""Shared HTTP, currency, URL and atomic-file helpers for this site only."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import gzip
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ZONES = {"hk": "Asia/Hong_Kong", "jp": "Asia/Tokyo", "us": "America/Los_Angeles"}
CURRENCIES = {"hk": "HKD", "jp": "JPY", "us": "USD"}


class SourceError(RuntimeError):
    pass


class Client:
    def __init__(self, delay=0.25):
        self.delay = delay
        self.request_count = 0

    def request(self, url, body=None, headers=None):
        request_headers = {"User-Agent": "Mozilla/5.0 (compatible; GameNotesUpcoming/1.0)",
                           "Accept-Encoding": "gzip", "Accept": "application/json,text/html;q=0.9"}
        request_headers.update(headers or {})
        data = json.dumps(body).encode() if body is not None else None
        if data is not None:
            request_headers["Content-Type"] = "application/json"
        for attempt in range(3):
            time.sleep(self.delay if attempt == 0 else 2 ** attempt)
            self.request_count += 1
            try:
                req = urllib.request.Request(url, data=data, headers=request_headers)
                with urllib.request.urlopen(req, timeout=45) as response:
                    if response.status != 200:
                        raise SourceError(f"HTTP {response.status}")
                    raw = response.read(32_000_001)
                    if len(raw) > 32_000_000:
                        raise SourceError("Response exceeds size limit")
                    if response.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    return raw.decode("utf-8")
            except urllib.error.HTTPError as exc:
                if exc.code not in (408, 429, 500, 502, 503, 504):
                    raise SourceError(f"HTTP {exc.code}: {urllib.parse.urlsplit(url).hostname}") from exc
                if attempt == 2:
                    raise SourceError(f"HTTP {exc.code} after retries") from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt == 2:
                    raise SourceError(f"Request failed: {type(exc).__name__}") from exc
        raise SourceError("Request failed")

    def json(self, url, body=None, headers=None):
        try:
            return json.loads(self.request(url, body, headers))
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise SourceError("Expected JSON; official source changed or refused the request") from exc


def query_url(url, params):
    return url + "?" + urllib.parse.urlencode(params, doseq=True)


def amount(value):
    if isinstance(value, bool) or value is None:
        raise SourceError("Missing price")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise SourceError("Invalid price") from exc
    if not number.is_finite() or number < 0:
        raise SourceError("Invalid price")
    return float(number.quantize(Decimal("0.01")))


def iso(value, zone):
    if not value:
        return None
    try:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceError("Invalid official timestamp") from exc
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=ZoneInfo(zone))
    return timestamp.astimezone(ZoneInfo(zone)).isoformat(timespec="seconds")


def official_url(url, image=False):
    if not url:
        return None
    parsed = urllib.parse.urlsplit(url)
    hosts = ("nintendo.com", "nintendo.com.hk", "nintendo.co.jp", "nintendo.net")
    if parsed.scheme != "https" or parsed.username or parsed.password or not any(
            parsed.hostname == host or (parsed.hostname or "").endswith("." + host) for host in hosts):
        raise SourceError("Unexpected non-official Nintendo URL")
    return url


def playstation_url(url, image=False):
    if not url:
        return None
    parsed = urllib.parse.urlsplit(url)
    expected = "image.api.playstation.com" if image else "store.playstation.com"
    if parsed.scheme != "https" or parsed.hostname != expected or parsed.username or parsed.password:
        raise SourceError("Unexpected non-official PlayStation URL")
    return url


def atomic_json(destination, value):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    handle_id, temporary = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(handle_id, "w", encoding="utf-8") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
