import { REGIONS, normalize } from "./common.js";

export const UPCOMING_PAGE_SIZE = 32;
const hosts = {
  link: ["nintendo.com", "nintendo.com.hk", "nintendo.co.jp", "store.playstation.com"],
  image: ["nintendo.com", "nintendo.com.hk", "nintendo.co.jp", "nintendo.net", "images.ctfassets.net", "image.api.playstation.com"],
};
export function upcomingUrl(value, kind = "link") {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password && hosts[kind].some(domain => url.hostname === domain || url.hostname.endsWith("." + domain)) ? url.href : null;
  } catch { return null; }
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
export function validUpcoming(data, region, store) {
  if (!REGIONS[region] || !["nintendo", "playstation"].includes(store)) return false;
  const games = data?.games;
  const platform = store === "playstation" ? "ps5" : "switch2";
  return data?.schemaVersion === 1 && data.kind === "upcoming" && data.store === store &&
    data.region === region.toUpperCase() && data.timezone === REGIONS[region].zone &&
    data.currency === REGIONS[region].currency && data.status === "success" &&
    Number.isFinite(Date.parse(data.updatedAt)) && Array.isArray(games) && games.length > 0 &&
    data.gameCount === games.length && new Set(games.map(game => game.key)).size === games.length &&
    games.every(game => typeof game.key === "string" && typeof game.title === "string" && game.title &&
      game.region === region && game.platform === platform && game.currency === data.currency &&
      ["day", "year", "season", "tbd"].includes(game.datePrecision) &&
      (game.datePrecision === "day" ? /^20\d\d-\d\d-\d\d$/.test(game.releaseDate) : game.releaseDate == null) &&
      (game.releaseAt == null || Number.isFinite(Date.parse(game.releaseAt))) &&
      upcomingUrl(game.url) && (!game.image || upcomingUrl(game.image, "image")) &&
      (game.price == null || Number.isFinite(game.price) && game.price >= 0) &&
      (game.originalPrice == null || Number.isFinite(game.originalPrice) && game.originalPrice > game.price) &&
      (!game.offer || game.offer.scope === "public" && game.offer.price === game.price &&
        game.offer.originalPrice === game.originalPrice && game.offer.price < game.offer.originalPrice) &&
      (!game.memberOffer || game.memberOffer.scope === "member") &&
      Array.isArray(game.versions) && game.versions.length > 0);
}
export function filterUpcoming(games, region, { query = "", period = "all", priceState = "all", sort = "release" } = {}, now = Date.now()) {
  const today = storeDay(now, region);
  const year = today.slice(0, 4);
  const close = new Date(Date.parse(today + "T00:00:00Z") + 90 * 86400000).toISOString().slice(0, 10);
  const terms = normalize(query).split(/\s+/).filter(Boolean);
  const filtered = games.filter(game => isUpcoming(game, region, now) && terms.every(term => normalize(game.title).includes(term)) &&
    (period === "all" || period === "soon" && game.datePrecision === "day" && game.releaseDate <= close ||
      period === "year" && (game.datePrecision === "day" ? game.releaseDate.startsWith(year) :
        ["year", "season"].includes(game.datePrecision) && game.releaseDateRaw?.includes(year)) ||
      period === "approximate" && ["year", "season"].includes(game.datePrecision) ||
      period === "tbd" && game.datePrecision === "tbd") &&
    (priceState === "all" || priceState === "priced" && game.price != null ||
      priceState === "unpriced" && game.price == null ||
      priceState === "offer" && Boolean(game.offer) ||
      priceState === "member" && Boolean(game.memberOffer)));
  const dateOrder = (a, b) => (a.releaseDate || "9999").localeCompare(b.releaseDate || "9999") || a.title.localeCompare(b.title);
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
