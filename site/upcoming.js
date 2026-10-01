import { REGIONS, money, cnyMoney, validRates, localTime } from "./common.js";
import { UPCOMING_PAGE_SIZE, upcomingUrl, validUpcoming, filterUpcoming, matchingVersions, displayDate } from "./upcoming-logic.js";

const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
let store = ["nintendo", "playstation"].includes(params.get("store")) ? params.get("store") : "nintendo";
let region = Object.hasOwn(REGIONS, params.get("region")) ? params.get("region") : "hk";
let snapshot = null, status = null, rates = null, rateStatus = null, page = 1, token = 0, observer = null;
const cache = new Map();
const lastGood = new Map(), choices = new Map();
const CACHE_MS = 5 * 60 * 1000;
let loadedAt = 0, networkFallback = false;

const el = (tag, cls, content) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (content != null) node.textContent = content;
  return node;
};
const options = () => ({ query: $("search").value, period: $("period").value,
  priceState: $("price-state").value, sort: $("sort").value, choices });
function syncUrl() {
  const values = new URLSearchParams({ store, region });
  const filters = options();
  if (filters.query) values.set("q", filters.query);
  if (filters.period !== "all") values.set("period", filters.period);
  if (filters.priceState !== "all") values.set("price", filters.priceState);
  if (filters.sort !== "release") values.set("sort", filters.sort);
  history.replaceState(null, "", "?" + values.toString());
}
function offerLine(offer, label) {
  const box = el("div", "upcoming-offer");
  box.append(el("span", "upcoming-offer-tag" + (offer.scope === "member" ? " member" : ""), label),
    el("span", "", `−${offer.discountPercent}% · 原价 ${money(offer.originalPrice, region)}`));
  const end = offer.endsAt ? localTime(offer.endsAt, region, true) + "（商店当地时间）" : offer.endsAtRaw || "截止时间未公布";
  box.append(el("span", "upcoming-offer-end", offer.endsAt || offer.endsAtRaw ? `优惠截止 ${end}` : end));
  return box;
}
function card(game) {
  const item = el("li", "upcoming-row");
  const identity = el("div", "game-identity");
  const thumb = el("div", "thumbnail", "暂无图片");
  const src = upcomingUrl(game.image, "image");
  if (src) {
    const img = el("img");
    img.alt = ""; img.width = 80; img.height = 80; img.loading = "lazy"; img.decoding = "async";
    img.dataset.src = src;
    const fallback = upcomingUrl(game.imageFallback, "image");
    let usedFallback = false;
    img.addEventListener("error", () => {
      if (!usedFallback && fallback && fallback !== src) { usedFallback = true; img.src = fallback; }
      else img.hidden = true;
    });
    thumb.append(img);
  }
  const info = el("div", "upcoming-identity-text");
  const title = el("a", "game-title", game.title);
  title.href = upcomingUrl(game.url); title.target = "_blank"; title.rel = "noopener noreferrer";
  info.append(title);
  const meta = el("div", "game-meta");
  meta.append(el("span", "platform-tag " + game.platform, game.platform === "ps5" ? "PS5" : "Switch 2"));
  if (game.publisher) meta.append(el("span", "", game.publisher));
  info.append(meta);
  const versions = matchingVersions(game, options());
  let selector = null;
  if (versions.length > 1) {
    const wrapper = el("label", "version-label");
    wrapper.append(el("span", "sr-only", "选择游戏版本"));
    selector = el("select", "version-select");
    versions.forEach(({ version, index }) => selector.add(new Option(version.edition || version.title, String(index))));
    selector.value = String(game.selectedVersionIndex);
    wrapper.append(selector); info.append(wrapper);
  } else if (versions[0]?.version.edition) {
    info.append(el("div", "game-publisher", "版本：" + versions[0].version.edition));
  }
  identity.append(thumb, info);
  const release = el("div", "upcoming-release");
  release.append(el("span", "upcoming-release-label", "发售日"), el("span", "upcoming-release-value", displayDate(game)));
  if (game.datePrecision !== "day") release.append(el("span", "upcoming-precision", game.datePrecision === "tbd" ? "日期待定" : "仅公布大致时间"));
  const priceCell = el("div", "upcoming-price");
  const link = el("a", "upcoming-link", "官方商品页 ↗");
  link.target = "_blank"; link.rel = "noopener noreferrer";
  function showVersion(version) {
    title.textContent = version.title;
    title.href = upcomingUrl(version.url);
    const price = version.price;
    priceCell.replaceChildren(el("div", price == null ? "upcoming-unpriced" : "price-current",
      price == null ? "售价未公布" : money(price, region)));
    if (price != null && rates) {
      const converted = cnyMoney(price, region, rates);
      if (converted) priceCell.append(el("div", "price-cny", converted));
    }
    if (version.offer) priceCell.append(offerLine(version.offer, "普通优惠"));
    if (version.memberOffer) {
      const member = offerLine(version.memberOffer, "PS Plus 专享");
      member.prepend(el("span", "upcoming-member-price", money(version.memberOffer.price, region)));
      priceCell.append(member);
    }
    link.href = upcomingUrl(version.url) || upcomingUrl(game.url);
    const catalogOnly = !version.id && /\/games\/switch2\/(?:index\.html|lineup)\/?(?:\?.*)?$/.test(new URL(link.href).pathname);
    link.textContent = catalogOnly ? "官方目录 ↗" : "官方商品页 ↗";
    link.setAttribute("aria-label", (catalogOnly ? "查看官方目录：" : "查看官方商品页：") + version.title);
  }
  showVersion((versions.find(item => item.index === game.selectedVersionIndex) || versions[0]).version);
  if (selector) selector.addEventListener("change", () => {
    choices.set(game.key, game.versions[Number(selector.value)].key);
    render();
  });
  item.append(identity, release, priceCell, link);
  return item;
}
function lazyImages() {
  observer?.disconnect();
  const images = $("game-list").querySelectorAll("img[data-src]");
  const load = image => { image.src = image.dataset.src; delete image.dataset.src; };
  if (!("IntersectionObserver" in window)) { images.forEach(load); return; }
  observer = new IntersectionObserver(entries => entries.forEach(entry => {
    if (entry.isIntersecting) { load(entry.target); observer.unobserve(entry.target); }
  }), { rootMargin: "150px 0px" });
  images.forEach(image => observer.observe(image));
}
function render() {
  if (!snapshot) return;
  syncUrl();
  const games = filterUpcoming(snapshot.games, region, options());
  const count = filterUpcoming(snapshot.games, region).length;
  const pages = Math.max(1, Math.ceil(games.length / UPCOMING_PAGE_SIZE));
  page = Math.max(1, Math.min(page, pages));
  $("count").replaceChildren(el("strong", "", String(games.length)), document.createTextNode(` 款符合条件 · 本区 ${count} 款待发售`));
  $("game-list").replaceChildren(...games.slice((page - 1) * UPCOMING_PAGE_SIZE, page * UPCOMING_PAGE_SIZE).map(card));
  $("no-results").hidden = games.length > 0;
  $("results").hidden = games.length === 0;
  $("pagination").hidden = pages <= 1;
  $("page-label").textContent = `${page} / ${pages} 页`;
  $("prev").disabled = page <= 1; $("next").disabled = page >= pages;
  const notes = [...(snapshot.source?.notes || [])];
  if (networkFallback) notes.unshift("网络读取失败，暂时展示本次访问已缓存的有效数据。");
  if (status?.status === "failed") notes.unshift("本来源最近一次更新失败，当前展示上次有效快照。请以官方页面为准。");
  else if (Date.now() - Date.parse(snapshot.updatedAt) > 36 * 3600000) notes.unshift("本来源数据已超过一天未更新，可能已过期。请核对官方商品页。");
  $("notice").textContent = notes.join(" "); $("notice").hidden = notes.length === 0;
  $("updated").textContent = "更新 " + localTime(snapshot.updatedAt, region, true) + " · 商店当地时间";
  $("source-note").textContent = `${store === "playstation" ? "PlayStation Store" : "Nintendo"} · ${REGIONS[region].name} · ${REGIONS[region].zone} · 实际抓取时间如上。`;
  lazyImages();
}
async function fetchJson(url, optional = false) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(url, { cache: "no-cache", signal: controller.signal });
    if (!response.ok) throw new Error("HTTP " + response.status);
    return await response.json();
  } catch (error) { if (optional) return null; throw error; }
  finally { clearTimeout(timeout); }
}
async function loadRates() {
  const [data, state] = await Promise.all([fetchJson("./data/fx.json", true), fetchJson("./data/fx.status.json", true)]);
  rates = validRates(data) ? data : null; rateStatus = state;
  const note = $("fx-note");
  if (!rates) note.textContent = "人民币参考价暂不可用；请按当地货币查看售价。";
  else note.textContent = `${rateStatus?.status === "failed" ? "沿用" : "参考"} ${rates.quoteDate} 汇率换算人民币；实际扣款以支付渠道为准。`;
  if (snapshot) render();
}
async function load(nextStore, nextRegion, force = false) {
  if (store !== nextStore || region !== nextRegion) choices.clear();
  store = nextStore; region = nextRegion; const current = ++token;
  document.querySelectorAll("[data-store]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.store === store)));
  document.querySelectorAll("[data-region]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.region === region)));
  snapshot = null; status = null; networkFallback = false; page = 1; observer?.disconnect();
  $("game-list").replaceChildren(); $("results").hidden = false; $("results").setAttribute("aria-busy", "true");
  $("no-results").hidden = true; $("notice").hidden = true; $("error").hidden = true; $("pagination").hidden = true;
  $("count").textContent = "正在加载游戏…"; $("updated").textContent = "正在读取 " + REGIONS[region].name + " 数据…";
  syncUrl();
  const stem = `upcoming-${store === "playstation" ? "ps5" : "ns2"}-${region}`;
  if (force || cache.get(stem)?.expiresAt <= Date.now()) cache.delete(stem);
  try {
    if (!cache.has(stem)) cache.set(stem, { expiresAt: Date.now() + CACHE_MS,
      promise: Promise.all([fetchJson(`./data/${stem}.json`), fetchJson(`./data/${stem}.status.json`, true)]) });
    const [data, state] = await cache.get(stem).promise;
    if (current !== token) return;
    if (!validUpcoming(data, region, store)) throw new Error("数据格式不完整");
    lastGood.set(stem, { data, state }); loadedAt = Date.now();
    snapshot = data; status = state; render();
  } catch {
    if (current !== token) return;
    cache.delete(stem);
    if (lastGood.has(stem)) {
      const previous = lastGood.get(stem);
      snapshot = previous.data; status = previous.state; networkFallback = true; render();
      return;
    }
    $("error").hidden = false; $("results").hidden = true;
    $("updated").textContent = "数据暂不可用";
    $("count").textContent = "暂无可展示的有效数据";
    $("error-message").textContent = "该区可能尚未完成首次抓取，或网络暂时不可用。请稍后重新读取。";
  } finally { if (current === token) $("results").setAttribute("aria-busy", "false"); }
}

$("search").value = params.get("q") || "";
for (const [id, key] of [["period", "period"], ["price-state", "price"], ["sort", "sort"]]) {
  if ([...$(id).options].some(option => option.value === params.get(key))) $(id).value = params.get(key);
}
document.querySelectorAll("[data-store]").forEach(button => button.addEventListener("click", () => load(button.dataset.store, region)));
document.querySelectorAll("[data-region]").forEach(button => button.addEventListener("click", () => load(store, button.dataset.region)));
let debounce;
$("search").addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(() => { page = 1; render(); }, 130); });
for (const id of ["period", "price-state", "sort"]) $(id).addEventListener("change", () => { page = 1; render(); });
$("reset").addEventListener("click", () => { $("search").value = ""; $("period").value = "all"; $("price-state").value = "all"; $("sort").value = "release"; choices.clear(); page = 1; render(); });
$("retry").addEventListener("click", () => { loadRates(); load(store, region, true); });
for (const [id, delta] of [["prev", -1], ["next", 1]]) $(id).addEventListener("click", () => {
  page += delta; render(); $("results").scrollIntoView({ block: "start" }); $("results").focus({ preventScroll: true });
});
loadRates();
load(store, region);
setInterval(() => { if (!document.hidden && snapshot) render(); }, 60000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && Date.now() - loadedAt >= CACHE_MS) { loadRates(); load(store, region, true); }
});
