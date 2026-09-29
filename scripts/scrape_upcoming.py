#!/usr/bin/env python3
"""Official Nintendo Switch 2 / PlayStation 5 coming-soon snapshots.

Each source owns its JSON and status. A failed scan only replaces the status;
the last validated game list remains available to the static site.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from lxml import html

from common import (ROOT, CURRENCIES, ZONES, Client, SourceError, amount, atomic_json, iso,
                    official_url, playstation_url, query_url)
from ps_store import (PS_API, PS_LOCALES, PS_PATHS, PS_PREFIXES, PS_QUERY_HASH,
                       PS_TYPES, ps_artwork, ps_price)

HK_LIST = "https://www.nintendo.com/hk/games/switch2/lineup"
HK_API = "https://www.nintendo.com/hk/api/games/switch2"
HK_PRICE = "https://api.ec.nintendo.com/v1/price"
JP_LIST = "https://www.nintendo.com/jp/games/switch2/index.html"
JP_API = "https://search.nintendo.jp/nintendo_soft/search.json"
US_LIST = "https://www.nintendo.com/us/store/games/coming-soon/"
PS_CATEGORIES = {
    "hk": "3bf499d7-7acf-4931-97dd-2667494ee2c9",
    "jp": "0c9f6f09-d84c-433e-9acd-d7e222eef034",
    "us": "82ced94c-ed3f-4d81-9b50-4d4cf1da170b",
}
EDITION_WORDS = re.compile(
    r"(?:\s*[-–—:：]\s*)?(?:デジタル|數位|数字|Digital\s+)?(?:デラックス|豪華|Deluxe|Ultimate|Gold|Premium|Special|Collector'?s)"
    r"(?:\s*(?:版|エディション|Edition|版本))?(?:\s*\([^)]*\))?$",
    re.I,
)
EXCLUDE_WORDS = re.compile(r"体験版|試玩版|试玩版|デモ版|\bDemo\b|Upgrade\s*(?:Pack|Pass)|アップグレード|升級包|升级包", re.I)


def release(raw, now):
    """Preserve the official text; only a complete day is actionable."""
    text = str(raw or "").strip()
    if not text or text in ("未定", "發售日待定", "発売日未定", "TBD", "TBA"):
        return None, "tbd", text or None
    match = re.fullmatch(r"(20\d\d)[./年-](\d{1,2})[./月-](\d{1,2})(?:日)?", text)
    if match:
        try:
            day = date(*map(int, match.groups())).isoformat()
            return day, "day", text
        except ValueError as exc:
            raise SourceError("Invalid official release day") from exc
    if re.fullmatch(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)", text):
        return text[:10], "day", text
    if re.fullmatch(r"20\d\d(?:年)?", text):
        return None, "year", text
    if re.search(r"20\d\d|今春|今夏|今秋|今冬|来春|来夏|来秋|来冬|春|夏|秋|冬|初頭|年内", text):
        return None, "season", text
    return None, "tbd", text


def still_upcoming(game, now):
    if game.get("releaseAt"):
        return datetime.fromisoformat(game["releaseAt"].replace("Z", "+00:00")) > now
    if game.get("datePrecision") == "day":
        # A date-only listing is not an instant in UTC. Use store local day.
        return game["releaseDate"] > now.astimezone(ZoneInfo(ZONES[game["region"]])).date().isoformat()
    return True


def image_url(url, store):
    if not url:
        return None
    if store == "playstation":
        return playstation_url(url, True)
    if urlsplit(url).hostname == "images.ctfassets.net" and url.startswith("https://"):
        return url
    return official_url(url, True)


def base_game(region, store, title, raw_date, url, image, uid=None, publisher=None,
              price=None, original=None, offer=None, member=None, concept=None,
              release_at=None, edition=None):
    title = str(title or "").strip()
    if not title:
        raise SourceError("Upcoming product missing title")
    url = (playstation_url if store == "playstation" else official_url)(url)
    if not url:
        raise SourceError("Upcoming product missing official link")
    day, precision, text = release(raw_date, None)
    if release_at:
        datetime.fromisoformat(release_at.replace("Z", "+00:00"))
    if price is not None:
        price = amount(price)
    if original is not None:
        original = amount(original)
    if original is not None and price is not None and original <= price:
        raise SourceError("Invalid upcoming promotion")
    key = str(uid or hashlib.sha256((store + region + title + url).encode()).hexdigest()[:20])
    return {"key": key, "id": str(uid) if uid else None, "conceptId": str(concept) if concept else None,
            "region": region, "title": title, "edition": edition or None,
            "publisher": publisher or None, "platform": "ps5" if store == "playstation" else "switch2",
            "releaseDateRaw": text, "datePrecision": precision, "releaseDate": day,
            "releaseAt": release_at, "price": price, "originalPrice": original,
            "currency": CURRENCIES[region], "offer": offer, "memberOffer": member,
            "url": url, "image": image_url(image, store), "versions": []}


def sale_offer(price, original, end=None, start=None, raw_end=None, scope="public"):
    if price is None or original is None or price >= original:
        return None
    percent = (Decimal(str(original - price)) / Decimal(str(original)) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return {"scope": scope, "price": price, "originalPrice": original,
            "discountPercent": float(percent), "startsAt": start, "endsAt": end,
            "endsAtRaw": raw_end}


def parse_hk_page(markup):
    tree = html.fromstring(markup)
    for script in tree.xpath('//script[not(@src)]'):
        raw = (script.text or "").strip()
        if not raw.startswith("self.__next_f.push("):
            continue
        try:
            flight = json.loads(raw[len("self.__next_f.push("):-1])[1]
            marker = '"posts":'
            if marker not in flight:
                continue
            result = json.JSONDecoder().raw_decode(flight[flight.index(marker) + len(marker):])[0]
            if isinstance(result.get("total"), int) and isinstance(result.get("items"), list):
                return result
        except (ValueError, KeyError, IndexError, TypeError):
            continue
    raise SourceError("Nintendo HK lineup payload changed")


def hk_rows(client):
    first = parse_hk_page(client.request(HK_LIST))
    total, rows = first["total"], list(first["items"])
    if not 0 < total <= 5000 or not rows:
        raise SourceError("Nintendo HK lineup empty or oversized")
    size = len(rows)
    for page in range(2, math.ceil(total / size) + 1):
        result = client.json(query_url(HK_API, {"spage": page}))
        items = result.get("items")
        if result.get("total") != total or not isinstance(items, list) or len(items) != min(size, total - len(rows)):
            raise SourceError("Nintendo HK lineup pagination changed")
        rows.extend(items)
    keys = [str((r.get("sys") or {}).get("id")) for r in rows]
    if len(rows) != total or len(set(keys)) != total:
        raise SourceError("Nintendo HK lineup missing or duplicated page")
    return rows, total


def hk_prices(client, ids):
    values = {}
    for start in range(0, len(ids), 50):
        chunk = ids[start:start + 50]
        data = client.json(query_url(HK_PRICE, {"country": "HK", "lang": "zh", "ids": ",".join(chunk)}))
        entries = data.get("prices")
        if data.get("country") != "HK" or data.get("personalized") is not False or not isinstance(entries, list):
            raise SourceError("Nintendo HK price context changed")
        if {str(e.get("title_id")) for e in entries} != set(chunk):
            raise SourceError("Nintendo HK price batch incomplete")
        values.update({str(e["title_id"]): e for e in entries})
    return values


def scrape_hk(client, now):
    rows, total = hk_rows(client)
    upcoming = []
    for row in rows:
        if row.get("hardwareCategory") != "Nintendo Switch 2" or EXCLUDE_WORDS.search(row.get("title") or ""):
            continue
        raw = row.get("releaseDateUndecided") or row.get("releaseDate")
        if raw and "T" in str(raw):
            raw = str(raw)[:10]
        uid = row.get("nsuid")
        link = row.get("pageLinkCustom") or row.get("pageLink") or HK_LIST
        link = link.replace("{NSUID}", str(uid)) if uid else link
        link = urljoin(HK_LIST, link)
        if urlsplit(link).hostname not in ("www.nintendo.com", "ec.nintendo.com", "store.nintendo.com.hk"):
            link = f"https://ec.nintendo.com/HK/zh/titles/{uid}" if uid else HK_LIST
        image = (row.get("imageHero") or {}).get("url")
        g = base_game("hk", "nintendo", row.get("title"), raw, link, image,
                      uid=uid, publisher=row.get("publisher"))
        if still_upcoming(g, now):
            upcoming.append(g)
    prices = hk_prices(client, [g["id"] for g in upcoming if g["id"] and re.fullmatch(r"700\d{11}", g["id"])])
    for g in upcoming:
        p = prices.get(g["id"], {})
        regular, discount = p.get("regular_price"), p.get("discount_price")
        if regular:
            if regular.get("currency") != "HKD":
                raise SourceError("Nintendo HK upcoming currency changed")
            g["price"] = amount(regular["raw_value"])
        if discount:
            if discount.get("currency") != "HKD" or g["price"] is None:
                raise SourceError("Nintendo HK upcoming discount currency changed")
            discounted = amount(discount["raw_value"])
            g["offer"] = sale_offer(discounted, g["price"], discount.get("end_datetime"), discount.get("start_datetime"), discount.get("end_datetime"))
            if g["offer"]:
                g["originalPrice"], g["price"] = g["price"], discounted
    return upcoming, {"name": "Nintendo HK Switch 2 lineup and official price service", "url": HK_LIST,
                      "candidateCount": total, "coverage": "official-lineup", "notes": []}


def jp_rows(client):
    params = {"opt_hard": "05_BEE", "opt_search": 1, "limit": 400, "page": 1,
              "sort": "sodate asc,titlek asc"}
    first = client.json(query_url(JP_API, params)).get("result") or {}
    total, items = first.get("total"), first.get("items")
    if not isinstance(total, int) or not 0 < total <= 20000 or not isinstance(items, list):
        raise SourceError("Nintendo JP search schema changed")
    rows = list(items)
    for page in range(2, math.ceil(total / 400) + 1):
        params["page"] = page
        result = client.json(query_url(JP_API, params)).get("result") or {}
        if result.get("total") != total or not isinstance(result.get("items"), list):
            raise SourceError("Nintendo JP search pagination changed")
        rows.extend(result["items"])
    if len(rows) != total or len({r.get("id") for r in rows}) != total or any(r.get("hard") != "05_BEE" for r in rows):
        raise SourceError("Nintendo JP search coverage incomplete")
    return rows, total


def scrape_jp(client, now):
    rows, total = jp_rows(client)
    games = []
    for row in rows:
        title = row.get("title") or ""
        uid = row.get("nsuid")
        if str(row.get("id", "")).endswith("-2") or EXCLUDE_WORDS.search(title):
            continue
        if uid and not str(uid).startswith(("700100", "700700")):
            continue
        if row.get("ssitu") in ("onsale", "sales_termination"):
            continue
        raw = row.get("sdate")
        if not raw:
            continue
        link = row.get("url") or (f"https://store-jp.nintendo.com/item/software/D{uid}" if uid else JP_LIST)
        art = row.get("iurl")
        if art and not art.startswith("https://") and not art.startswith("/"):
            art = f"https://img-eshop.cdn.nintendo.net/i/{art}.jpg"
        elif art and art.startswith("/"):
            art = urljoin(JP_LIST, art)
        regular = row.get("dprice")
        sale = row.get("sprice")
        regular = amount(regular) if regular is not None else None
        sale = amount(sale) if sale is not None else None
        offer = sale_offer(sale, regular, iso(row.get("sedate"), ZONES["jp"]),
                           iso(row.get("ssdate"), ZONES["jp"]), row.get("sedate"))
        g = base_game("jp", "nintendo", title, raw, link, art, uid=uid,
                      publisher=row.get("maker"), price=sale if offer else regular,
                      original=regular if offer else None, offer=offer)
        if still_upcoming(g, now):
            games.append(g)
    return games, {"name": "Nintendo JP official Switch 2 search", "url": JP_LIST,
                   "candidateCount": total, "coverage": "official-search", "notes": []}


def scrape_us(client, now):
    tree = html.fromstring(client.request(US_LIST))
    scripts = tree.xpath('//script[@id="__NEXT_DATA__"]/text()')
    if len(scripts) != 1:
        raise SourceError("Nintendo US coming-soon page data missing")
    try:
        grid = json.loads(scripts[0])["props"]["pageProps"]["page"]["content"]["merchandisedGrid"][0]
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise SourceError("Nintendo US coming-soon payload changed") from exc
    if not isinstance(grid, list) or not grid:
        raise SourceError("Nintendo US coming-soon list empty")
    games = []
    for row in grid:
        if not isinstance(row, dict):
            continue
        platform = row.get("platform")
        if (platform.get("label") if isinstance(platform, dict) else platform) != "Nintendo Switch 2":
            continue
        if row.get("dlcType") or EXCLUDE_WORDS.search(row.get("name") or ""):
            continue
        uid = row.get("nsuid")
        if not uid or not str(uid).startswith(("700100", "700700")):
            continue
        slug = row.get("urlKey")
        if not slug or not re.fullmatch(r"[a-z0-9-]+", slug):
            raise SourceError("Nintendo US product URL missing")
        picture = row.get("productImageSquare") or row.get("productImage") or {}
        art = picture.get("url") or ("https://assets.nintendo.com/image/upload/f_auto,q_auto,w_160/" + picture["publicId"] if picture.get("publicId") else None)
        if art and "/image/upload/" in art and "w_160" not in art:
            art = art.replace("/image/upload/", "/image/upload/w_160/", 1)
        prices = row.get("prices") or {}
        regular = prices.get("regularPrice")
        final = prices.get("finalPrice")
        if prices and prices.get("currency") != "USD":
            raise SourceError("Nintendo US upcoming currency changed")
        offer = sale_offer(amount(final), amount(regular), (row.get("eshopDetails") or {}).get("discountPriceEnd")) if final is not None and regular is not None else None
        g = base_game("us", "nintendo", row.get("name"), row.get("releaseDateDisplay") or row.get("releaseDate"),
                      f"https://www.nintendo.com/us/store/products/{slug}/", art,
                      uid=uid, publisher=row.get("softwarePublisher"),
                      price=final if final is not None else regular,
                      original=regular if offer else None, offer=offer,
                      edition=row.get("edition"))
        if still_upcoming(g, now):
            games.append(g)
    return games, {"name": "Nintendo US official Coming Soon page", "url": US_LIST,
                   "candidateCount": len(grid), "coverage": "official-curated-page",
                   "notes": ["美服来源为任天堂公开的 Coming Soon 精选页，可能不包含全部待发售游戏。"]}


def ps_headers(region):
    return {"x-psn-store-locale-override": PS_LOCALES[region],
            "x-psn-app-ver": "@sie-ppr-web-store/app/0.114.0-",
            "x-apollo-operation-name": "categoryGridRetrieve",
            "Referer": "https://store.playstation.com/"}


def ps_candidates(client, region):
    category = PS_CATEGORIES[region]
    seen, catalog_keys, result, total = set(), set(), [], None
    for offset in range(0, 10000, 100):
        variables = {"id": category, "pageArgs": {"size": 100, "offset": offset}, "sortBy": None,
                     "filterBy": [f"storeDisplayClassification:{kind}" for kind in PS_TYPES], "facetOptions": []}
        params = {"operationName": "categoryGridRetrieve", "variables": json.dumps(variables, separators=(",", ":")),
                  "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": PS_QUERY_HASH}}, separators=(",", ":"))}
        data = client.json(query_url(PS_API, params), headers=ps_headers(region))
        if data.get("errors"):
            raise SourceError("PlayStation coming-soon category query failed")
        listing = (data.get("data") or {}).get("categoryGridRetrieve") or {}
        page = listing.get("pageInfo") or {}
        count = page.get("totalCount")
        if not isinstance(count, int) or not 0 < count <= 10000 or page.get("offset") != offset:
            raise SourceError("PlayStation coming-soon pagination changed")
        if total is None:
            total = count
        if count != total:
            raise SourceError("PlayStation coming-soon list moved during scan")
        products, concepts = listing.get("products"), listing.get("concepts")
        if products is None:
            products = []
        if concepts is None:
            concepts = []
        if not isinstance(products, list) or not isinstance(concepts, list):
            raise SourceError("PlayStation coming-soon category format changed")
        page_rows = products or concepts
        if len(page_rows) != min(100, total - offset) or page.get("isLast") != (offset + len(page_rows) == total):
            raise SourceError("PlayStation coming-soon page coverage changed")
        for item in page_rows:
            key = item.get("id") if isinstance(item, dict) else None
            if not key or key in catalog_keys:
                raise SourceError("PlayStation coming-soon category repeated an item")
            catalog_keys.add(key)
        # Some locales return products; US currently returns concepts whose
        # product IDs must be resolved from their official detail pages.
        entries = []
        if products:
            entries = [(p.get("id"), p) for p in products]
        elif concepts:
            entries = [(p.get("id"), None) for concept in concepts for p in concept.get("products", [])]
        if not entries:
            raise SourceError("PlayStation coming-soon page unexpectedly empty")
        for uid, row in entries:
            if not uid or not re.fullmatch(r"[A-Z0-9_-]{16,80}", uid):
                raise SourceError("PlayStation coming-soon product ID missing")
            if uid not in seen:
                seen.add(uid)
                result.append((uid, row))
        if page.get("isLast"):
            break
    else:
        raise SourceError("PlayStation coming-soon category exceeds limit")
    if not result or len(catalog_keys) != total:
        raise SourceError("PlayStation coming-soon list has no product IDs")
    return result, total


def ps_detail(markup, uid, region, listing_row):
    tree = html.fromstring(markup)
    product = {}
    ctas = []
    for script in tree.xpath('//script[@type="application/json"]'):
        try:
            payload = json.loads(script.text or "")
        except ValueError:
            continue
        cache = payload.get("cache") or {}
        part = cache.get(f"Product:{uid}") or {}
        product.update(part)
        ctas.extend(v for k, v in cache.items() if k.startswith("GameCTA:") and uid in k and isinstance(v, dict) and v.get("local"))
    if product.get("id") != uid:
        raise SourceError("PlayStation product detail missing identity")
    if product.get("storeDisplayClassification") not in PS_TYPES or "PS5" not in product.get("platforms", []):
        return None
    if EXCLUDE_WORDS.search(product.get("name") or ""):
        return None
    raw_timestamp = product.get("releaseDate")
    if raw_timestamp:
        try:
            release_at = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00")).isoformat()
        except ValueError as exc:
            raise SourceError("PlayStation release timestamp changed") from exc
    else:
        release_at = None
    for item in tree.xpath('//script|//style'):
        item.drop_tree()
    visible = " ".join(tree.xpath("//body")[0].text_content().split())
    patterns = {"hk": r"推出日:\s*(\d{1,2}/\d{1,2}/20\d\d)",
                "jp": r"発売日[:：]\s*(20\d\d[年./]\d{1,2}[月./]\d{1,2}日?)",
                "us": r"Release:\s*(\d{1,2}/\d{1,2}/20\d\d)"}
    found = re.search(patterns[region], visible)
    raw_day = found.group(1) if found else raw_timestamp
    if found and region in ("hk", "us"):
        fields = list(map(int, raw_day.split("/")))
        d, m, y = fields if region == "hk" else (fields[1], fields[0], fields[2])
        release_day = date(y, m, d).isoformat()
    else:
        release_day = raw_timestamp[:10] if raw_timestamp else None
    media = product.get("media") or (listing_row or {}).get("media") or []
    art, fallback = ps_artwork(media) if media else (None, None)
    if not art:
        raise SourceError("PlayStation upcoming cover missing")
    regular_price = None
    offer = member_offer = None
    for cta in ctas:
        local = cta.get("local") or {}
        detail = cta.get("price") or {}
        kind = cta.get("type") or local.get("type") or ""
        if kind == "UPSELL_PS_PLUS_DISCOUNT" or "ps-plus" in local.get("serviceIcons", []):
            current = ps_price(local["priceOrText"], region) if local.get("priceOrText", "").startswith(PS_PREFIXES[region]) else None
            original = ps_price(local["originalPrice"], region) if local.get("originalPrice", "").startswith(PS_PREFIXES[region]) else None
            member_offer = sale_offer(current, original, local.get("offerAvailability"), raw_end=local.get("offerAvailability"), scope="member")
            continue
        if offer:
            continue
        if kind not in ("PREORDER", "BUY_NOW", "PURCHASE", "FREE"):
            continue
        if detail.get("isExclusive") or detail.get("isTiedToSubscription") or "PS_PLUS" in detail.get("serviceBranding", []):
            continue
        value = detail.get("discountedValue")
        base = detail.get("basePriceValue")
        if local.get("priceOrText", "").startswith(PS_PREFIXES[region]):
            current = ps_price(local["priceOrText"], region)
            original = ps_price(local["originalPrice"], region) if local.get("originalPrice", "").startswith(PS_PREFIXES[region]) else current
        elif isinstance(value, int) and isinstance(base, int) and detail.get("currencyCode") == CURRENCIES[region]:
            divisor = 1 if region == "jp" else 100
            current, original = amount(Decimal(value) / divisor), amount(Decimal(base) / divisor)
        else:
            continue
        regular_price = current
        offer = sale_offer(current, original, detail.get("endTime") or local.get("offerAvailability"),
                           raw_end=detail.get("endTime") or local.get("offerAvailability"))
    if regular_price is None and listing_row:
        p = listing_row.get("price") or {}
        if not (p.get("isExclusive") or p.get("isTiedToSubscription")) and p.get("discountedPrice"):
            regular_price = ps_price(p["discountedPrice"], region)
            original = ps_price(p["basePrice"], region) if p.get("basePrice") else regular_price
            offer = sale_offer(regular_price, original)
    concept = product.get("concept") or {}
    if release_day and not re.fullmatch(r"20\d\d-\d\d-\d\d", release_day):
        release_day = None
    g = base_game(region, "playstation", product.get("name") or (listing_row or {}).get("name"),
                  release_day or raw_day, f"https://store.playstation.com/{PS_PATHS[region]}/product/{uid}",
                  art, uid=uid, publisher=product.get("publisherName"), price=regular_price,
                  original=offer["originalPrice"] if offer else None, offer=offer,
                  member=member_offer, concept=concept.get("__ref", "").removeprefix("Concept:"),
                  release_at=release_at, edition=(product.get("edition") or {}).get("name"))
    # Keep the verbatim visible store label even when its date is represented
    # separately as an ISO day for filtering and sorting.
    if found:
        g["releaseDateRaw"] = raw_day
        g["releaseDate"] = release_day
        g["datePrecision"] = "day"
    g["imageFallback"] = fallback
    return g


def scrape_ps(client, region, now):
    candidates, total = ps_candidates(client, region)
    games = []
    for uid, row in candidates:
        url = f"https://store.playstation.com/{PS_PATHS[region]}/product/{uid}"
        g = ps_detail(client.request(url), uid, region, row)
        if g and still_upcoming(g, now):
            games.append(g)
    return games, {"name": "PlayStation Store official Coming Soon / Pre-order category and product pages",
                   "url": f"https://store.playstation.com/{PS_PATHS[region]}/category/{PS_CATEGORIES[region]}/1",
                   "candidateCount": total, "productPages": len(candidates), "coverage": "official-category",
                   "notes": []}


def group_games(games):
    """Keep standard editions in the list; expose sibling products as versions."""
    def without_languages(title):
        # Store locales append language lists to both standard and deluxe
        # products. Remove only an obvious language suffix before comparing.
        return re.sub(r"\s*\((?=[^)]*(?:中文|英文|韓文|日文|Chinese|English|Japanese|Korean))[^)]*\)$", "", title, flags=re.I)

    def stem(title):
        return EDITION_WORDS.sub("", without_languages(title)).strip(" -–—:：")

    groups = {}
    for game in games:
        title_stem = stem(game["title"])
        key = (game["conceptId"], title_stem.casefold(), game["releaseDate"] or game["releaseDateRaw"])
        groups.setdefault(key, []).append(game)
    output = []
    for siblings in groups.values():
        siblings.sort(key=lambda g: (0 if re.search(r"standard|通常|一般|普通|標準", g.get("edition") or "", re.I) else 1,
                                     1 if EDITION_WORDS.search(without_languages(g["title"])) else 0,
                                     g["price"] if g["price"] is not None else float("inf"), g["title"]))
        primary = siblings[0]
        primary["versions"] = [{"key": v["key"], "id": v["id"], "title": v["title"],
                                "edition": v["edition"], "url": v["url"], "price": v["price"],
                                "originalPrice": v["originalPrice"], "offer": v["offer"],
                                "memberOffer": v["memberOffer"]} for v in siblings]
        output.append(primary)
    output.sort(key=lambda g: (g["releaseDate"] is None, g["releaseDate"] or "9999", g["title"].casefold()))
    return output


def validate_snapshot(data):
    region = str(data.get("region", "")).lower()
    store = data.get("store")
    if data.get("schemaVersion") != 1 or data.get("kind") != "upcoming" or region not in ZONES or store not in ("nintendo", "playstation"):
        raise SourceError("Invalid upcoming snapshot metadata")
    if data.get("status") != "success" or data.get("currency") != CURRENCIES[region] or data.get("timezone") != ZONES[region]:
        raise SourceError("Invalid upcoming snapshot context")
    datetime.fromisoformat(data["updatedAt"])
    games = data.get("games")
    if not isinstance(games, list) or not games or data.get("gameCount") != len(games):
        raise SourceError("Empty or incomplete upcoming snapshot; preserving previous data")
    if len({g.get("key") for g in games}) != len(games):
        raise SourceError("Duplicate upcoming game key")
    for g in games:
        if not g.get("title") or g.get("region") != region or g.get("currency") != CURRENCIES[region]:
            raise SourceError("Invalid upcoming game identity")
        if g.get("platform") != ("ps5" if store == "playstation" else "switch2"):
            raise SourceError("Invalid upcoming platform")
        if g.get("datePrecision") not in ("day", "year", "season", "tbd"):
            raise SourceError("Invalid upcoming date precision")
        if g["datePrecision"] == "day" and not g.get("releaseDate"):
            raise SourceError("Missing exact upcoming date")
        if g["datePrecision"] != "day" and g.get("releaseDate"):
            raise SourceError("Approximate upcoming date fabricated")
        (playstation_url if store == "playstation" else official_url)(g.get("url"))
        if not g.get("url"):
            raise SourceError("Missing official upcoming link")
        image_url(g.get("image"), store)
        if g.get("price") is not None:
            amount(g["price"])
        if g.get("offer"):
            o = g["offer"]
            if o.get("scope") != "public" or o.get("price") != g["price"] or o.get("originalPrice") != g["originalPrice"] or not o["originalPrice"] > o["price"] >= 0:
                raise SourceError("Invalid public upcoming offer")
            if o.get("endsAt"):
                datetime.fromisoformat(o["endsAt"].replace("Z", "+00:00"))
        if g.get("memberOffer") and g["memberOffer"].get("scope") != "member":
            raise SourceError("Member offer mislabelled")
        if g.get("memberOffer") and g["memberOffer"].get("endsAt"):
            datetime.fromisoformat(g["memberOffer"]["endsAt"].replace("Z", "+00:00"))
        if not isinstance(g.get("versions"), list) or not g["versions"]:
            raise SourceError("Upcoming versions missing")
    return data


def refresh(region, store, directory, client=None, scraper=None, clock=None):
    client = client or Client()
    directory = Path(directory)
    stem = f"upcoming-{'ps5' if store == 'playstation' else 'ns2'}-{region}"
    destination = directory / f"{stem}.json"
    previous_at = None
    if destination.exists():
        try:
            old = validate_snapshot(json.loads(destination.read_text()))
            if old["store"] == store and old["region"] == region.upper():
                previous_at = old["updatedAt"]
        except (SourceError, ValueError, KeyError, TypeError):
            pass
    now = clock or datetime.now(ZoneInfo(ZONES[region]))
    started = now.isoformat(timespec="seconds")
    try:
        if scraper:
            games, source = scraper(client, now)
        elif store == "playstation":
            games, source = scrape_ps(client, region, now)
        else:
            games, source = {"hk": scrape_hk, "jp": scrape_jp, "us": scrape_us}[region](client, now)
        games = group_games([g for g in games if still_upcoming(g, now)])
        completed = datetime.now(ZoneInfo(ZONES[region])) if clock is None else clock
        snapshot = {"schemaVersion": 1, "kind": "upcoming", "store": store, "region": region.upper(),
                    "timezone": ZONES[region], "currency": CURRENCIES[region],
                    "updatedAt": completed.isoformat(timespec="seconds"), "status": "success",
                    "gameCount": len(games), "source": source, "games": games}
        validate_snapshot(snapshot)
        atomic_json(destination, snapshot)
        atomic_json(directory / f"{stem}.status.json",
                    {"region": region.upper(), "store": store, "status": "success", "attemptedAt": started,
                     "completedAt": snapshot["updatedAt"], "lastSuccessAt": snapshot["updatedAt"],
                     "requestCount": client.request_count, "error": None})
        return snapshot
    except Exception as exc:
        atomic_json(directory / f"{stem}.status.json",
                    {"region": region.upper(), "store": store, "status": "failed", "attemptedAt": started,
                     "completedAt": datetime.now(ZoneInfo(ZONES[region])).isoformat(timespec="seconds"),
                     "lastSuccessAt": previous_at, "requestCount": client.request_count,
                     "error": f"{type(exc).__name__}: {exc}"[:500]})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", choices=("nintendo", "playstation"), required=True)
    parser.add_argument("--region", choices=tuple(ZONES), required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "site/data")
    args = parser.parse_args()
    try:
        snapshot = refresh(args.region, args.store, args.output)
        print(f"Upcoming {args.store} {args.region.upper()}: {snapshot['gameCount']} games at {snapshot['updatedAt']}")
        return 0
    except Exception as exc:
        print(f"FAILED upcoming {args.store} {args.region.upper()}: {exc}. Previous snapshot preserved.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
