// Backtest lengths (bars) per timeframe. The server pages history from the
// exchange; "long" can take up to a minute. A few hundred bars (the old
// default) produce a handful of trades — statistically meaningless.
export const BT_PERIODS = {
  "1m": { short: 1500, medium: 3000, long: 8000 },
  "5m": { short: 2000, medium: 6000, long: 15000 },
  "15m": { short: 2000, medium: 6000, long: 15000 },
  "1h": { short: 1500, medium: 4000, long: 10000 },
  "4h": { short: 800, medium: 2000, long: 4000 },
};

export function barsFor(timeframe, period) {
  return (BT_PERIODS[timeframe] || BT_PERIODS["5m"])[period] || BT_PERIODS["5m"].medium;
}
