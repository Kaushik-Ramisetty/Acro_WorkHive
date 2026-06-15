// Single source of truth for money formatting in the app.
// All historical fixtures in this codebase were authored in USD; we convert to
// INR using a configurable rate (overridable via VITE_USD_TO_INR) and format
// with the Indian numbering system (1,00,000 lakh / 10,00,000 crore).

const RAW_RATE = (typeof import.meta !== 'undefined' && import.meta?.env?.VITE_USD_TO_INR);
export const USD_TO_INR = Number(RAW_RATE) > 0 ? Number(RAW_RATE) : 83;

const INR_FORMATTER = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
});
const INR_FORMATTER_2DP = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
});

/**
 * Convert USD → INR. Accepts a number or a currency string like "$1,234.50",
 * "$4.2M", "$680K". Returns a Number rounded to the nearest rupee.
 */
export function usdToInr(amount, rate = USD_TO_INR) {
  const usd = parseUsdAmount(amount);
  if (Number.isNaN(usd)) return 0;
  return Math.round(usd * rate);
}

/**
 * Parse a USD-style string ("$1,234.50", "$4.2M", "$680K") or number into a Number.
 */
export function parseUsdAmount(raw) {
  if (typeof raw === 'number') return raw;
  if (raw == null) return 0;
  const str = String(raw).trim();
  if (!str) return 0;
  // Handle suffix multipliers: K (thousand), M (million), B (billion)
  const m = str.match(/^-?\s*\$?\s*([0-9,]+(?:\.[0-9]+)?)\s*([KMB])?\s*$/i);
  if (!m) return Number(str.replace(/[^0-9.\-]/g, '')) || 0;
  const num = parseFloat(m[1].replace(/,/g, ''));
  const sfx = (m[2] || '').toUpperCase();
  const mul = sfx === 'B' ? 1e9 : sfx === 'M' ? 1e6 : sfx === 'K' ? 1e3 : 1;
  return num * mul;
}

/**
 * Format a NUMBER (already in INR) using Indian-locale currency formatting.
 *   formatINR(100000)   →  "₹1,00,000"
 *   formatINR(1234.5, { decimals: 2 }) →  "₹1,234.50"
 */
export function formatINR(amount, { decimals = 0 } = {}) {
  const n = Number(amount);
  if (!Number.isFinite(n)) return '₹0';
  return decimals > 0 ? INR_FORMATTER_2DP.format(n) : INR_FORMATTER.format(n);
}

/**
 * Convert a USD value (number OR string like "$8,450") and return the formatted INR string.
 *   formatUsdAsInr('$8,450')  →  "₹7,01,350"
 *   formatUsdAsInr('$4.2M')   →  "₹34,86,00,000"
 */
export function formatUsdAsInr(usdAmount, opts) {
  return formatINR(usdToInr(usdAmount), opts);
}

/**
 * Format an INR amount in the compact Indian style for big numbers:
 *   1,500       → "₹1,500"
 *   2,50,000    → "₹2.50 Lakh"
 *   1,20,00,000 → "₹1.20 Cr"
 */
export function formatINRCompact(amount) {
  const n = Number(amount);
  if (!Number.isFinite(n) || n === 0) return '₹0';
  const abs = Math.abs(n);
  if (abs >= 1e7) return '₹' + (n / 1e7).toFixed(2).replace(/\.?0+$/, '') + ' Cr';
  if (abs >= 1e5) return '₹' + (n / 1e5).toFixed(2).replace(/\.?0+$/, '') + ' Lakh';
  return formatINR(n);
}

export default formatINR;
