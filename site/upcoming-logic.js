import { REGIONS, normalize } from "./common.js";

export const UPCOMING_PAGE_SIZE = 32;
const hosts = {
  link: ["nintendo.com", "nintendo.com.hk", "nintendo.co.jp", "store.playstation.com"],
  image: ["nintendo.com", "nintendo.com.hk", "nintendo.co.jp", "nintendo.net", "images.ctfassets.net", "image.api.playstation.com"],
};
export function upcomingUrl(value, kind = "link") {
  if (typeof value !== "string" || !hosts[kind]) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password && hosts[kind].some(domain => url.hostname === domain || url.hostname.endsWith("." + domain)) ? url.href : null;
  } catch { return null; }
}
const object = value => value != null && typeof value === "object" && !Array.isArray(value);
const price = value => typeof value === "number" && Number.isFinite(value) && value >= 0;
const day = value => typeof value === "string" && /^20\d\d-\d\d-\d\d$/.test(value) &&
  Number.isFinite(Date.parse(value + "T00:00:00Z")) && new Date(value + "T00:00:00Z").toISOString().slice(0, 10) === value;
const instant = value => typeof value === "string" && /^20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(value) &&
  day(value.slice(0, 10)) && Number(value.slice(11, 13)) < 24 && Number(value.slice(14, 16)) < 60 &&
  Number(value.slice(17, 19)) < 60 && Number.isFinite(Date.parse(value));
function validOffer(offer, scope) {
  return offer == null || object(offer) && offer.scope === scope && price(offer.price) &&
    price(offer.originalPrice) && offer.originalPrice > offer.price &&
    Number.isFinite(offer.discountPercent) && offer.discountPercent >= 0 && offer.discountPercent <= 100 &&
    Math.abs(offer.discountPercent - (1 - offer.price / offer.originalPrice) * 100) <= 0.11 &&
    (offer.startsAt == null || instant(offer.startsAt)) && (offer.endsAt == null || instant(offer.endsAt)) &&
    (!offer.startsAt || !offer.endsAt || Date.parse(offer.startsAt) < Date.parse(offer.endsAt)) &&
    (offer.endsAtRaw == null || typeof offer.endsAtRaw === "string");
}
function validVersion(version) {
  return object(version) && typeof version.key === "string" && version.key.trim() &&
    typeof version.title === "string" && version.title.trim() && upcomingUrl(version.url) &&
    (version.id == null || typeof version.id === "string") &&
    (version.edition == null || typeof version.edition === "string") &&
    (version.price == null || price(version.price)) &&
    (version.originalPrice == null || price(version.originalPrice) && price(version.price) && version.originalPrice > version.price) &&
    validOffer(version.offer, "public") && validOffer(version.memberOffer, "member") &&
    (!version.offer || version.offer.price === version.price && version.offer.originalPrice === version.originalPrice);
}
export function storeDay(now, region) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-US", { timeZone: REGIONS[region].zone,
    year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date(now)).map(part => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}
export function isUpcoming(game, region, now = Date.now()) {
  if (game.releaseAt) return Date.parse(game.releaseAt) > now;
  if (game.datePrecision === "day") return game.releaseDate > storeDay(now, region);
  return true;
}
export function validUpcoming(data, region, store, now = Date.now()) {
  if (!Object.hasOwn(REGIONS, region) || !["nintendo", "playstation"].includes(store) || !object(data)) return false;
  const games = data?.games;
  const platform = store === "playstation" ? "ps5" : "switch2";
  return data?.schemaVersion === 1 && data.kind === "upcoming" && data.store === store &&
    data.region === region.toUpperCase() && data.timezone === REGIONS[region].zone &&
    data.currency === REGIONS[region].currency && data.status === "success" &&
    (data.source == null || object(data.source)) &&
    (data.source?.notes == null || Array.isArray(data.source.notes) && data.source.notes.every(note => typeof note === "string")) &&
    instant(data.updatedAt) && Date.parse(data.updatedAt) <= now + 300000 && Array.isArray(games) && games.length > 0 && games.length <= 25000 &&
    data.gameCount === games.length && games.every(game => validVersion(game) &&
      game.region === region && game.platform === platform && game.currency === data.currency &&
      ["publisher", "conceptId", "releaseDateRaw"].every(key => game[key] == null || typeof game[key] === "string") &&
      ["day", "year", "season", "tbd"].includes(game.datePrecision) &&
      (game.datePrecision === "day" ? day(game.releaseDate) : game.releaseDate == null) &&
      (game.releaseAt == null || instant(game.releaseAt)) &&
      upcomingUrl(game.url) && (!game.image || upcomingUrl(game.image, "image")) &&
      (!game.imageFallback || upcomingUrl(game.imageFallback, "image")) &&
      Array.isArray(game.versions) && game.versions.length > 0 && game.versions.every(validVersion) &&
      new Set(game.versions.map(version => version.key)).size === game.versions.length) &&
    new Set(games.map(game => game.key)).size === games.length;
}
export function activeOffer(offer, now = Date.now()) {
  return offer && (!offer.startsAt || Date.parse(offer.startsAt) <= now) && (!offer.endsAt || Date.parse(offer.endsAt) > now) ? offer : null;
}
export function currentVersion(version, now = Date.now()) {
  const offer = activeOffer(version.offer, now);
  return { ...version, price: version.offer && !offer ? version.offer.originalPrice : version.price,
    originalPrice: version.offer && !offer ? null : version.originalPrice,
    offer, memberOffer: activeOffer(version.memberOffer, now) };
}
export function matchingVersions(game, { query = "", priceState = "all" } = {}, now = Date.now()) {
  const terms = normalize(query).split(/\s+/).filter(Boolean);
  return game.versions.map((version, index) => ({ version: currentVersion(version, now), index })).filter(({ version }) =>
    terms.every(term => normalize(`${game.title} ${version.title} ${version.edition || ""}`).includes(term)) &&
    (priceState === "all" || priceState === "priced" && version.price != null || priceState === "unpriced" && version.price == null ||
      priceState === "offer" && Boolean(version.offer) || priceState === "member" && Boolean(version.memberOffer)));
}
export function filterUpcoming(games, region, { query = "", period = "all", priceState = "all", sort = "release", choices = new Map() } = {}, now = Date.now()) {
  const today = storeDay(now, region);
  const year = today.slice(0, 4);
  const close = new Date(Date.parse(today + "T00:00:00Z") + 90 * 86400000).toISOString().slice(0, 10);
  const filtered = games.filter(game => isUpcoming(game, region, now) &&
    (period === "all" || period === "soon" && game.datePrecision === "day" && game.releaseDate <= close ||
      period === "year" && (game.datePrecision === "day" ? game.releaseDate.startsWith(year) :
        ["year", "season"].includes(game.datePrecision) && game.releaseDateRaw?.includes(year)) ||
      period === "approximate" && ["year", "season"].includes(game.datePrecision) ||
      period === "tbd" && game.datePrecision === "tbd")).flatMap(game => {
    const versions = matchingVersions(game, { query, priceState }, now);
    const selected = versions.find(item => item.version.key === choices.get(game.key)) || versions[0];
    return selected ? [{ ...game, price: selected.version.price, originalPrice: selected.version.originalPrice,
      offer: selected.version.offer, memberOffer: selected.version.memberOffer, selectedVersionIndex: selected.index }] : [];
  });
  const dateOrder = (a, b) => (a.releaseDate || "9999").localeCompare(b.releaseDate || "9999") ||
    (a.releaseAt ? Date.parse(a.releaseAt) : Infinity) - (b.releaseAt ? Date.parse(b.releaseAt) : Infinity) || a.title.localeCompare(b.title);
  const priceOrder = (a, b) => (a.price ?? Infinity) - (b.price ?? Infinity) || dateOrder(a, b);
  const order = { release: dateOrder, price: priceOrder, discount: (a, b) => (b.offer?.discountPercent || 0) - (a.offer?.discountPercent || 0) || dateOrder(a, b),
    title: (a, b) => a.title.localeCompare(b.title) }[sort] || dateOrder;
  return filtered.sort(order);
}
export function displayDate(game) {
  if (game.datePrecision === "tbd") return game.releaseDateRaw || "发售日待定";
  if (game.datePrecision !== "day") return game.releaseDateRaw || "发售日待定";
  const raw = game.releaseDateRaw;
  return raw && !/^20\d\d-\d\d-\d\d(?:T.*)?$/.test(raw) ? raw : game.releaseDate.replaceAll("-", "/");
}
