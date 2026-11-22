cd "$1"
for s in BTCUSDT ETHUSDT SOLUSDT XRPUSDT DOGEUSDT ADAUSDT AVAXUSDT LINKUSDT SUIUSDT BNBUSDT LTCUSDT AAVEUSDT; do
  for y in 2021 2022 2023 2024 2025 2026; do for m in 01 02 03 04 05 06 07 08 09 10 11 12; do
    [ "$y$m" -gt 202610 ] && continue
    f=$s-5m-$y-$m.zip; [ -f $f ] && continue
    echo "https://data.binance.vision/data/futures/um/monthly/klines/$s/5m/$f"
  done; done
done | xargs -P 12 -n 1 curl -sfO
ls *.zip | wc -l
