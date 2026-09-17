// Shared crypto symbol universe used by the Scalp page and the Bitunix panel,
// so the "which coins exist" list has a single source of truth.
export const CRYPTO_BASE = [
  "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "TRX", "TON", "DOT",
  "MATIC", "LTC", "AVAX", "LINK", "ATOM", "UNI", "XLM", "ETC", "FIL", "APT",
  "ARB", "OP", "NEAR", "INJ", "SUI", "SEI", "RNDR", "IMX", "AAVE", "MKR",
  "GRT", "SAND", "MANA", "EOS", "XTZ", "ALGO", "FTM", "THETA", "KAVA", "FLOW",
  "CHZ", "ENJ", "ZIL", "ONE", "HBAR", "VET", "ICP", "QNT", "EGLD", "CRV",
];

// Bitunix perpetual symbols, e.g. "BTCUSDT"
export const BITUNIX_SYMBOLS = CRYPTO_BASE.map((b) => `${b}USDT`);
