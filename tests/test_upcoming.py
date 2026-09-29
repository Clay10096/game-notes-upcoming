import json
from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import SourceError
from scrape_upcoming import (base_game, group_games, ps_detail, refresh, release,
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

    def snapshot(self, games):
        games = group_games(games)
        return {"schemaVersion": 1, "kind": "upcoming", "store": "nintendo", "region": "JP",
                "timezone": "Asia/Tokyo", "currency": "JPY", "updatedAt": self.now.isoformat(),
                "status": "success", "gameCount": len(games), "games": games}


if __name__ == "__main__":
    unittest.main()
