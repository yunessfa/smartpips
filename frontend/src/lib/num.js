// Convert Persian (۰-۹) and Arabic-Indic (٠-٩) digits to ASCII, and strip
// thousands separators so prices from the AI parse reliably.
const FA = "۰۱۲۳۴۵۶۷۸۹";
const AR = "٠١٢٣٤٥٦٧٨٩";

export function toAsciiDigits(input) {
  if (input == null) return "";
  let s = String(input);
  s = s.replace(/[۰-۹]/g, (d) => String(FA.indexOf(d)));
  s = s.replace(/[٠-٩]/g, (d) => String(AR.indexOf(d)));
  return s;
}

// Extract the first numeric value from a string like "۵۲٬۵۰۰ - ۵۳٬۰۰۰".
export function parsePrice(value) {
  if (value == null || value === "") return "";
  const ascii = toAsciiDigits(value).replace(/[,٬،_\s]/g, "");
  const m = ascii.match(/-?\d+(\.\d+)?/);
  return m ? m[0] : "";
}

export function fmtPrice(n) {
  if (n == null || n === "" || Number.isNaN(Number(n))) return "—";
  const num = Number(n);
  const max = Math.abs(num) >= 1000 ? 2 : 6;
  return num.toLocaleString("en-US", { maximumFractionDigits: max });
}
