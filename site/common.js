export const REGIONS = {
  hk: { name: "港服", zone: "Asia/Hong_Kong", currency: "HKD", symbol: "HK$" },
  jp: { name: "日服", zone: "Asia/Tokyo", currency: "JPY", symbol: "¥" },
  us: { name: "美服", zone: "America/Los_Angeles", currency: "USD", symbol: "US$" },
};

export const normalize = value => String(value).normalize("NFKC").toLocaleLowerCase().trim();

export function money(value, region) {
  return REGIONS[region].symbol + " " + new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: region === "jp" ? 0 : 2,
    maximumFractionDigits: region === "jp" ? 0 : 2,
  }).format(value);
}

export function validRates(data, now = Date.now()) {
  const date = data?.quoteDate;
  const parsed = Date.parse(date + "T00:00:00Z");
  return data?.schemaVersion === 1 && data.status === "success" && data.targetCurrency === "CNY" &&
    /^\d{4}-\d{2}-\d{2}$/.test(date) && Number.isFinite(parsed) && parsed <= now &&
    new Date(parsed).toISOString().slice(0, 10) === date && Number.isFinite(Date.parse(data.updatedAt)) &&
    ["HKD", "JPY", "USD"].every(currency => Number.isFinite(data.rates?.[currency]) && data.rates[currency] > 0);
}

export function cnyMoney(value, region, rates) {
  if (!REGIONS[region] || !Number.isFinite(value) || value < 0 || !validRates(rates)) return null;
  const amount = value * rates.rates[REGIONS[region].currency];
  if (!Number.isFinite(amount)) return null;
  return "约人民币 ¥ " + new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount);
}

export function localTime(value, region, withYear = false) {
  if (!value || !Number.isFinite(Date.parse(value))) return "";
  return new Intl.DateTimeFormat("zh-CN", { timeZone: REGIONS[region].zone,
    ...(withYear ? { year: "numeric" } : {}), month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(value));
}
