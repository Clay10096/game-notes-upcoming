import test from "node:test";
import assert from "node:assert/strict";
import { displayDate, filterUpcoming, isUpcoming, upcomingUrl, validUpcoming } from "../site/upcoming-logic.js";

const now = Date.parse("2026-09-29T02:00:00Z");
const base = { key: "no-id", id: null, title: "Year only", region: "jp", platform: "switch2",
  datePrecision: "year", releaseDateRaw: "2027年", releaseDate: null, releaseAt: null,
  price: null, originalPrice: null, offer: null, memberOffer: null, currency: "JPY",
  url: "https://www.nintendo.com/jp/games/switch2/index.html", image: null,
  versions: [{ key: "no-id", title: "Year only", url: "https://www.nintendo.com/jp/games/switch2/index.html" }] };
const day = { ...base, key: "priced", title: "Exact release", datePrecision: "day", releaseDateRaw: "2026.10.1",
  releaseDate: "2026-10-01", price: 5000, offer: null };
const expired = { ...day, key: "expired", title: "Already out", releaseDate: "2026-09-28" };
const offer = { ...day, key: "offer", title: "Preorder offer", price: 4000, originalPrice: 5000,
  offer: { scope: "public", price: 4000, originalPrice: 5000, discountPercent: 20, endsAt: null } };
test("upcoming validation accepts unpriced year-only games without an ID", () => {
  const snapshot = { schemaVersion: 1, kind: "upcoming", store: "nintendo", region: "JP",
    timezone: "Asia/Tokyo", currency: "JPY", status: "success", updatedAt: "2026-09-29T00:05:00+09:00",
    gameCount: 1, games: [base] };
  assert.ok(validUpcoming(snapshot, "jp", "nintendo"));
  assert.equal(validUpcoming({ ...snapshot, games: [{ ...base, releaseDate: "2027-01-01" }] }, "jp", "nintendo"), false);
  assert.equal(validUpcoming({ ...snapshot, kind: "discount" }, "jp", "nintendo"), false);
});
test("exact releases leave the list; year-only entries wait for official update", () => {
  assert.equal(isUpcoming(expired, "jp", now), false);
  assert.equal(isUpcoming(base, "jp", now), true);
  assert.deepEqual(filterUpcoming([base, expired, day], "jp", {}, now).map(g => g.key), ["priced", "no-id"]);
});
test("date and price filters preserve unknown states and release order", () => {
  const games = [base, day, offer, expired];
  assert.deepEqual(filterUpcoming(games, "jp", { period: "approximate" }, now).map(g => g.key), ["no-id"]);
  assert.deepEqual(filterUpcoming(games, "jp", { priceState: "unpriced" }, now).map(g => g.key), ["no-id"]);
  assert.deepEqual(filterUpcoming(games, "jp", { priceState: "offer" }, now).map(g => g.key), ["offer"]);
  assert.deepEqual(filterUpcoming(games, "jp", { query: "EXACT" }, now).map(g => g.key), ["priced"]);
  assert.equal(displayDate(base), "2027年");
  assert.equal(displayDate(day), "2026.10.1");
});
test("official links permit source art and reject lookalike hosts", () => {
  assert.ok(upcomingUrl("https://images.ctfassets.net/o5v89n4kg6h4/art.jpg", "image"));
  assert.equal(upcomingUrl("https://store.playstation.com.attacker.test/product/a"), null);
});
