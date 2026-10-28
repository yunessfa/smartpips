// Engine levels only. Never invent nearer targets or change order execution.
export function takeProfitPlan(signal) {
  const entry = Number(signal?.entry ?? signal?.entry_price);
  const side = signal?.signal ?? (signal?.direction === 'short' ? 'sell' : signal?.direction === 'long' ? 'buy' : null);
  if (!(entry > 0 && Number.isFinite(entry)) || !['buy','sell'].includes(side)) return [];
  const source = signal?.tp_levels;
  if (!Array.isArray(source) || source.length < 2 || source.length > 3) return [];
  const direction = side === 'buy' ? 1 : -1;
  const levels = source.map((level,index)=>({label:`TP${index+1}`,price:Number(level.price),pct:Number(level.pct),r:Number(level.r)}));
  let distance=0;
  for (const level of levels) {
    const move=(level.price-entry)*direction;
    if (!Number.isFinite(level.price) || !(level.price>0) || !Number.isFinite(level.pct) || !(level.pct>0 && level.pct<=100) || !(move>distance)) return [];
    distance=move;
  }
  if (Math.abs(levels.reduce((sum,level)=>sum+level.pct,0)-100)>.001) return [];
  return levels;
}
export function analysisTargetLevels(signal) {
  if (!signal || !['buy','sell'].includes(signal.signal)) return [];
  const plan=takeProfitPlan(signal);
  return plan.length ? plan.map(level=>[`${level.label} · ${level.pct}%`,level.price,'#72bc8f'])
    : signal.take_profit != null ? [['Signal TP',signal.take_profit,'#72bc8f']] : [];
}
export function exitSlices(plan,quantity) {
  const qty=Number(quantity);
  return plan.map(level=>({...level, quantity:Number.isFinite(qty)&&qty>0 ? qty*level.pct/100 : null}));
}

// Keep small-coin axis labels distinct instead of rounding every target to 0.99.
export function chartPriceFormat(price) {
  const n = Number(price);
  const precision = Number.isFinite(n) && n > 0
    ? Math.max(2, Math.min(10, 6 - Math.floor(Math.log10(n)))) : 2;
  return { type: 'price', precision, minMove: 10 ** -precision };
}
