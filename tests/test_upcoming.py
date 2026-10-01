import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import SourceError
from check_site import validate_status
from scrape_upcoming import (base_game, expire_offers, group_games, ps_candidates, ps_concept_detail, ps_detail, ps_page_game, refresh, release, scrape_jp,
                             sale_offer, still_upcoming, validate_snapshot)


class UpcomingTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 29, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))

    def game(self, title="Example", raw="2026.10.1", price=None, uid=None):
        return base_game("jp", "nintendo", title, raw,
                         "https://www.nintendo.com/jp/games/switch2/index.html", None,
                         uid=uid, price=price)

    def test_date_precision_preserves_year_season_and_tbd_without_inventing_day(self):
        for raw, precision in (("2027", "year"), ("2027年春", "season"),
                               ("今冬", "season"), ("未定", "tbd")):
            day, actual, text = release(raw, self.now)
            self.assertIsNone(day)
            self.assertEqual(actual, precision)
            self.assertEqual(text, raw)
        self.assertEqual(release("2027.2.16", self.now), ("2027-02-16", "day", "2027.2.16"))

    def test_unpriced_game_with_no_product_id_is_valid(self):
        game = self.game("Year-only listing", "2027年", None)
        self.assertIsNone(game["id"])
        self.assertIsNone(game["price"])
        snapshot = self.snapshot([game])
        self.assertEqual(validate_snapshot(snapshot), snapshot)

    def test_public_and_member_offers_remain_distinct(self):
        product_id = "HP5846-PPSA33879_00-0000000000000000"
        media = [{"type": "IMAGE", "role": "GAMEHUB_COVER_ART",
                  "url": "https://image.api.playstation.com/example.jpg"}]
        cache = {
            f"Product:{product_id}": {"id": product_id, "name": "Example", "releaseDate": "2026-10-29T00:00:00Z",
                "storeDisplayClassification": "FULL_GAME", "platforms": ["PS5"], "media": media,
                "concept": {"__ref": "Concept:123"}, "edition": {"name": "一般版"}},
            f"GameCTA:PREORDER:{product_id}": {"type": "PREORDER", "local": {"priceOrText": "HK$80.00", "originalPrice": "HK$100.00"},
                                               "price": {"currencyCode": "HKD", "basePriceValue": 10000,
                                                         "discountedValue": 8000, "endTime": "2026-10-28T00:00:00Z"}},
            f"GameCTA:UPSELL_PS_PLUS_DISCOUNT:{product_id}": {"type": "UPSELL_PS_PLUS_DISCOUNT",
                "local": {"priceOrText": "HK$70.00", "originalPrice": "HK$100.00",
                          "offerAvailability": "2026-10-27T00:00:00Z", "serviceIcons": ["ps-plus"]}},
        }
        markup = '<html><body><script type="application/json">' + json.dumps({"cache": cache}) + \
                 '</script><p>推出日:29/10/2026</p></body></html>'
        game = ps_detail(markup, product_id, "hk", None)
        self.assertEqual(game["price"], 80)
        self.assertEqual(game["originalPrice"], 100)
        self.assertEqual(game["offer"]["discountPercent"], 20)
        self.assertEqual(game["offer"]["endsAt"], "2026-10-28T00:00:00Z")
        self.assertEqual(game["memberOffer"]["scope"], "member")
        self.assertEqual(game["memberOffer"]["price"], 70)

    def test_multiple_editions_show_standard_first(self):
        deluxe = self.game("Example デラックスエディション", uid="70070000000001", price=200)
        standard = self.game("Example", uid="70010000000001", price=100)
        grouped = group_games([deluxe, standard])
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["title"], "Example")
        self.assertEqual([v["price"] for v in grouped[0]["versions"]], [100, 200])
        standard_ps = base_game("hk", "playstation", "Anvil Saga (繁體中文, 英文)", "2026-10-01",
                                "https://store.playstation.com/zh-hant-hk/product/EXAMPLE-STANDARD", None,
                                uid="EXAMPLE-STANDARD", concept="123", edition="一般版", price=198)
        deluxe_ps = base_game("hk", "playstation", "Anvil Saga - Deluxe Edition (繁體中文, 英文)", "2026-10-01",
                              "https://store.playstation.com/zh-hant-hk/product/EXAMPLE-DELUXE", None,
                              uid="EXAMPLE-DELUXE", concept="123", edition="豪華版", price=278)
        unrelated = base_game("hk", "playstation", "Anvil Saga 2 (繁體中文, 英文)", "2026-10-01",
                              "https://store.playstation.com/zh-hant-hk/product/EXAMPLE-SEQUEL", None,
                              uid="EXAMPLE-SEQUEL", concept="123", price=298)
        grouped = group_games([deluxe_ps, unrelated, standard_ps])
        self.assertEqual(len(grouped), 2)
        self.assertEqual(len(next(g for g in grouped if g["title"].startswith("Anvil Saga ("))["versions"]), 2)

    def test_exact_release_expires_but_year_only_waits_for_official_update(self):
        self.assertFalse(still_upcoming(self.game(raw="2026.9.29"), self.now))
        self.assertTrue(still_upcoming(self.game(raw="2026.9.30"), self.now))
        self.assertTrue(still_upcoming(self.game(raw="2026"), self.now))

    def test_changed_release_date_replaces_snapshot_and_failure_retains_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            dates = iter(("2026.10.1", "2026.11.1"))
            def source(client, now):
                return [self.game(raw=next(dates))], {"name": "fixture", "url": "https://www.nintendo.com/jp/games/switch2/index.html"}
            first = refresh("jp", "nintendo", directory, scraper=source, clock=self.now)
            second = refresh("jp", "nintendo", directory, scraper=source, clock=self.now)
            self.assertNotEqual(first["games"][0]["releaseDate"], second["games"][0]["releaseDate"])
            path = directory / "upcoming-ns2-jp.json"
            before = path.read_bytes()
            def fails(client, now):
                raise SourceError("official source unavailable")
            with self.assertRaises(SourceError):
                refresh("jp", "nintendo", directory, scraper=fails, clock=self.now)
            self.assertEqual(before, path.read_bytes())
            status = json.loads((directory / "upcoming-ns2-jp.status.json").read_text())
            self.assertEqual(status["status"], "failed")
            self.assertEqual(status["lastSuccessAt"], second["updatedAt"])

    def test_announced_only_last_page_is_not_a_failed_scan(self):
        product_id = "UP1234-PPSA12345_00-EXAMPLE000000000"
        first = [{"id": str(i), "products": [{"id": product_id}]} for i in range(100)]
        last = [{"id": "10017135", "products": []}]
        class FixtureClient:
            def json(self, url, headers):
                rows = first if not getattr(self, "called", False) else last
                offset = 0 if rows is first else 100
                self.called = True
                return {"data": {"categoryGridRetrieve": {"products": [], "concepts": rows,
                    "pageInfo": {"totalCount": 101, "offset": offset, "isLast": offset == 100}}}}
        candidates, total = ps_candidates(FixtureClient(), "us")
        self.assertEqual(total, 101)
        self.assertEqual(candidates, [(product_id, None), ("10017135", last[0])])
        first[0]["products"] = None
        with self.assertRaises(SourceError):
            ps_candidates(FixtureClient(), "us")

    def test_announced_concept_preserves_unpriced_release_and_platform(self):
        concept = {"id": "12345", "isAnnounce": True, "products": [], "defaultProduct": None,
                   "name": "Announced game", "publisherName": "Example publisher", "platforms": [],
                   "compatibilityNoticesByPlatform": {"PS5": [{"type": "PS5_VIBRATION"}]},
                   "media": [{"type": "IMAGE", "role": "GAMEHUB_COVER_ART",
                              "url": "https://image.api.playstation.com/example.jpg"}],
                   "releaseDate": {"type": "DAY_MONTH_YEAR", "value": "2026-10-14T14:00:00Z"}}
        def markup(label):
            return '<html><body><script type="application/json">' + json.dumps({"cache": {"Concept:12345": concept}}) + \
                   '</script><span data-qa="mfe-game-title#release-date">' + label + '</span></body></html>'
        game = ps_concept_detail(markup("10/14/2026 02:00 PM UTC"), "12345", "us", concept)
        self.assertIsNone(game["id"])
        self.assertIsNone(game["price"])
        self.assertEqual(game["releaseDate"], "2026-10-14")
        self.assertEqual(game["releaseAt"], "2026-10-14T14:00:00+00:00")
        countdown = ps_concept_detail(markup("03:32:51"), "12345", "us", concept)
        self.assertEqual(countdown["releaseDateRaw"], "2026-10-14")
        concept["releaseDate"] = {"type": "YEAR", "value": "2027"}
        game = ps_concept_detail(markup("2027"), "12345", "us", concept)
        self.assertEqual(game["datePrecision"], "year")
        self.assertIsNone(game["releaseDate"])
        concept["compatibilityNoticesByPlatform"] = {"PS4": [{}]}
        self.assertIsNone(ps_concept_detail(markup("2027"), "12345", "us", concept))

    def test_every_edition_must_be_decodable_and_valid_before_publishing(self):
        snapshot = self.snapshot([self.game(price=100)])
        for field, value in (("price", "100"), ("price", float("nan")), ("price", -1),
                             ("price", True), ("originalPrice", 80), ("title", None),
                             ("url", "https://example.com/game"), ("id", 123)):
            with self.subTest(field=field, value=value):
                broken = deepcopy(snapshot)
                broken["games"][0]["versions"][0][field] = value
                with self.assertRaises(SourceError):
                    validate_snapshot(broken)
        for field, value in (("releaseDate", "2026-02-30"), ("releaseAt", "2026-10-01T00:00:00")):
            broken = deepcopy(snapshot)
            broken["games"][0][field] = value
            with self.assertRaises(SourceError):
                validate_snapshot(broken)

    def test_bad_member_discount_never_passes_as_an_ordinary_valid_price(self):
        snapshot = self.snapshot([self.game(price=100)])
        offer = sale_offer(80, 100, "2026-10-20T00:00:00Z", scope="member")
        for field, value in (("scope", "public"), ("price", "80"), ("originalPrice", -100),
                             ("discountPercent", 99), ("endsAt", "2026-02-30T00:00:00Z")):
            broken = deepcopy(snapshot)
            broken["games"][0]["versions"][0]["memberOffer"] = {**offer, field: value}
            with self.assertRaises(SourceError):
                validate_snapshot(broken)

    def test_expired_offers_are_removed_at_the_cutoff_without_losing_regular_price(self):
        game = self.game(price=80)
        game["originalPrice"] = 100
        game["offer"] = sale_offer(80, 100, self.now.isoformat())
        game["memberOffer"] = sale_offer(70, 100, self.now.isoformat(), scope="member")
        expire_offers(game, self.now)
        self.assertEqual(game["price"], 100)
        self.assertIsNone(game["originalPrice"])
        self.assertIsNone(game["offer"])
        self.assertIsNone(game["memberOffer"])
        game["offer"] = sale_offer(80, 100)
        expire_offers(game, self.now)
        self.assertIsNotNone(game["offer"])

    def test_empty_or_invalid_source_keeps_snapshot_bytes_and_marks_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            refresh("jp", "nintendo", directory, scraper=lambda c, n: ([self.game()], {}), clock=self.now)
            path = directory / "upcoming-ns2-jp.json"
            before = path.read_bytes()
            bad = self.game(price=100)
            bad["memberOffer"] = sale_offer(80, 100, scope="public")
            for games in ([], [bad]):
                with self.assertRaises(SourceError):
                    refresh("jp", "nintendo", directory, scraper=lambda c, n: (games, {}), clock=self.now)
                self.assertEqual(path.read_bytes(), before)
                state = json.loads((directory / "upcoming-ns2-jp.status.json").read_text())
                self.assertEqual(state["status"], "failed")
                validate_status(state, json.loads(before))

    def test_punctuation_variants_merge_but_early_release_editions_stay_separate(self):
        def product(uid, title, raw):
            return base_game("us", "playstation", title, raw,
                "https://store.playstation.com/en-us/product/" + uid, None, uid=uid, concept="123", price=40)
        standard = product("STANDARD", "Clive Barker’s Hellraiser", "2026-10-29")
        deluxe = product("DELUXE", "Clive Barker's Hellraiser Deluxe Edition", "2026-10-29")
        early = product("EARLY", "Clive Barker's Hellraiser Deluxe Edition", "2026-10-26")
        result = group_games([standard, deluxe, early])
        self.assertEqual(len(result), 2)
        self.assertEqual(len(next(g for g in result if g["releaseDate"] == "2026-10-29")["versions"]), 2)

    def test_status_must_match_the_snapshot_it_describes(self):
        snapshot = self.snapshot([self.game()])
        status = {"region": "JP", "store": "nintendo", "status": "success", "error": None,
                  "attemptedAt": snapshot["updatedAt"], "completedAt": snapshot["updatedAt"],
                  "lastSuccessAt": snapshot["updatedAt"]}
        validate_status(status, snapshot)
        for field, value in (("region", "HK"), ("lastSuccessAt", "2026-09-28T12:00:00+09:00"),
                             ("attemptedAt", "2026-09-30T12:00:00+09:00"), ("completedAt", "2026-09-29T12:00:00")):
            with self.assertRaises(SourceError):
                validate_status({**status, field: value}, snapshot)

    def test_jp_search_keeps_hardware_announced_games_and_full_bundles(self):
        base = {"id": "announced", "title": "Announced game", "sdate": "2027年", "ssitu": "not_found",
                "sform": None, "url": "https://www.nintendo.com/jp/games/switch2/index.html"}
        rows = [base, {**base, "id": "console", "title": "Console", "sform": "hard"},
                {**base, "id": "controller", "title": "Controller", "sform": "accessory"},
                {**base, "id": "console-bundle", "title": "Console bundle", "sform": "hard-soft"},
                {**base, "id": "uncategorized-hardware", "title": "Accessory", "url": "https://www.nintendo.com/jp/hardware/switch2/index.html"},
                {**base, "id": "70070000000001", "nsuid": "70070000000001", "title": "Complete bundle", "sform": "DL_DLC"},
                {**base, "id": "70050000000001", "nsuid": "70050000000001", "title": "Standalone DLC", "sform": "DL_DLC"}]
        with patch("scrape_upcoming.jp_rows", return_value=(rows, len(rows))):
            games, source = scrape_jp(None, self.now)
        self.assertEqual({g["title"] for g in games}, {"Announced game", "Complete bundle", "Console", "Controller", "Console bundle", "Accessory"})

    def test_http_200_shell_is_revalidated_once_without_skipping_a_product(self):
        uid = "JP1234-PPSA12345_00-EXAMPLE000000000"
        product = {"id": uid, "name": "Example", "releaseDate": "2027-01-01T00:00:00Z",
                   "storeDisplayClassification": "FULL_GAME", "platforms": ["PS5"],
                   "media": [{"type": "IMAGE", "role": "GAMEHUB_COVER_ART", "url": "https://image.api.playstation.com/example.jpg"}]}
        markup = '<html><body><script type="application/json">' + json.dumps({"cache": {"Product:" + uid: product}}) + '</script></body></html>'
        class FixtureClient:
            calls = []
            def request(self, url, headers=None):
                self.calls.append((url, headers))
                return markup if len(self.calls) == 2 else '<html><body>Store loading</body></html>'
        client = FixtureClient()
        url = "https://store.playstation.com/ja-jp/product/" + uid
        game = ps_page_game(client, url, uid, "jp", None, False)
        self.assertEqual(game["id"], uid)
        self.assertEqual(game["releaseDate"], "2027-01-01")
        self.assertEqual(len(client.calls), 2)
        self.assertTrue(client.calls[1][0].startswith(url + "?refresh="))
        self.assertEqual(client.calls[1][1], {"Cache-Control": "no-cache"})
        with self.assertRaises(SourceError):
            ps_page_game(client, url, uid, "jp", None, False)

    def snapshot(self, games):
        games = group_games(games)
        return {"schemaVersion": 1, "kind": "upcoming", "store": "nintendo", "region": "JP",
                "timezone": "Asia/Tokyo", "currency": "JPY", "updatedAt": self.now.isoformat(),
                "status": "success", "gameCount": len(games), "games": games}


if __name__ == "__main__":
    unittest.main()
