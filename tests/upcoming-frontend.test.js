import test from "node:test";
import assert from "node:assert/strict";
import { activeOffer, currentVersion, displayDate, filterUpcoming, isUpcoming, matchingVersions, upcomingUrl, validUpcoming } from "../site/upcoming-logic.js";
import { readFileSync } from "node:fs";

const now = Date.parse("2026-09-29T02:00:00Z");
const base = { key: "no-id", id: null, title: "Year only", region: "jp", platform: "switch2",
  datePrecision: "year", releaseDateRaw: "2027年", releaseDate: null, releaseAt: null,
  price: null, originalPrice: null, offer: null, memberOffer: null, currency: "JPY",
  url: "https://www.nintendo.com/jp/games/switch2/index.html", image: null,
  versions: [{ key: "no-id", title: "Year only", url: "https://www.nintendo.com/jp/games/switch2/index.html" }] };
const withVersion = game => ({ ...game, versions: [{ ...game, versions: undefined }] });
const day = withVersion({ ...base, key: "priced", title: "Exact release", datePrecision: "day", releaseDateRaw: "2026.10.1",
  releaseDate: "2026-10-01", price: 5000, offer: null });
const expired = withVersion({ ...day, key: "expired", title: "Already out", releaseDate: "2026-09-28" });
const offer = withVersion({ ...day, key: "offer", title: "Preorder offer", price: 4000, originalPrice: 5000,
  offer: { scope: "public", price: 4000, originalPrice: 5000, discountPercent: 20, endsAt: null } });
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
test("all six published snapshot shapes are valid for the web reader", () => {
  for (const [platform, store] of [["ns2", "nintendo"], ["ps5", "playstation"]]) {
    for (const region of ["hk", "jp", "us"]) {
      const data = JSON.parse(readFileSync(new URL(`../site/data/upcoming-${platform}-${region}.json`, import.meta.url)));
      assert.equal(validUpcoming(data, region, store), true, `${platform}-${region}`);
    }
  }
});
test("malformed sibling editions and invalid dates reject the whole snapshot", () => {
  const snapshot = { schemaVersion: 1, kind: "upcoming", store: "nintendo", region: "JP", timezone: "Asia/Tokyo",
    currency: "JPY", status: "success", updatedAt: "2026-09-29T00:05:00+09:00", gameCount: 1, games: [day] };
  for (const corrupt of [null, { ...day, releaseDate: "2026-02-30" },
    { ...day, releaseAt: "2026-10-01T00:00:00" },
    { ...day, versions: [{ ...day.versions[0], price: -1 }] },
    { ...day, versions: [{ ...day.versions[0], url: "javascript:alert(1)" }] },
    { ...day, memberOffer: { scope: "member", price: 1, originalPrice: 0, discountPercent: 99 } }]) {
    assert.equal(validUpcoming({ ...snapshot, games: [corrupt] }, "jp", "nintendo", now), false);
  }
  assert.equal(validUpcoming(snapshot, "constructor", "nintendo", now), false);
});
test("an offer ends at the exact cutoff and unknown deadlines stay unknown", () => {
  const timed = { ...offer.offer, endsAt: new Date(now).toISOString() };
  assert.equal(activeOffer(timed, now), null);
  assert.equal(activeOffer(timed, now - 1), timed);
  assert.deepEqual(currentVersion({ ...offer, offer: timed }, now).price, 5000);
  assert.equal(currentVersion({ ...offer, offer: timed }, now).originalPrice, null);
  assert.equal(currentVersion({ ...day, memberOffer: timed }, now).memberOffer, null);
  assert.equal(activeOffer(offer.offer, now), offer.offer);
  assert.equal(activeOffer({ ...timed, endsAt: null, startsAt: new Date(now + 1).toISOString() }, now), null);
});
test("search and price filters find sibling editions and sort the displayed price", () => {
  const sibling = { ...offer.versions[0], key: "deluxe", title: "Exact release Deluxe", edition: "Deluxe" };
  const grouped = { ...day, versions: [day.versions[0], sibling] };
  assert.equal(filterUpcoming([grouped], "jp", { priceState: "offer" }, now)[0].selectedVersionIndex, 1);
  assert.equal(filterUpcoming([grouped], "jp", { query: "deluxe" }, now).length, 1);
  assert.equal(matchingVersions(grouped, { priceState: "offer" }, now).length, 1);
  const choices = new Map([[grouped.key, sibling.key]]);
  assert.equal(filterUpcoming([grouped], "jp", { choices }, now)[0].price, 4000);
});
test("release filtering uses store days through midnight and US daylight saving", () => {
  const hk = withVersion({ ...day, region: "hk", releaseDate: "2026-10-01" });
  assert.equal(isUpcoming(hk, "hk", Date.parse("2026-09-30T15:59:59Z")), true);
  assert.equal(isUpcoming(hk, "hk", Date.parse("2026-09-30T16:00:00Z")), false);
  const us = withVersion({ ...day, region: "us", releaseDate: "2026-03-08" });
  assert.equal(isUpcoming(us, "us", Date.parse("2026-03-08T07:59:59Z")), true);
  assert.equal(isUpcoming(us, "us", Date.parse("2026-03-08T08:00:00Z")), false);
  const exact = { ...us, releaseAt: "2026-03-08T10:00:00Z" };
  assert.equal(isUpcoming(exact, "us", Date.parse("2026-03-08T09:59:59Z")), true);
  assert.equal(isUpcoming(exact, "us", Date.parse("2026-03-08T10:00:00Z")), false);
});
