import { useI18n } from '../i18n/index.jsx';
import { fmtPrice } from '../lib/num.js';
import { takeProfitPlan, exitSlices } from '../lib/takeProfitPlan.js';

export function TakeProfitPlan({ signal, quantity, unit='', execution='single', attachedTarget }) {
  const {isRTL}=useI18n();
  const plan=takeProfitPlan(signal);
  if(!plan.length) return null;
  const rows=exitSlices(plan,quantity);
  const target=attachedTarget ?? signal.take_profit;
  return <section data-tp-plan className="rounded-lg border border-gold/30 bg-ink-800 p-3 my-3 text-xs space-y-2" aria-label={isRTL?'برنامه خروج پله‌ای':'Staged exit plan'}>
    <h3 className="text-gold-soft font-semibold">{isRTL?'برنامه خروج پله‌ای موتور':'Engine staged exit plan'}</h3>
    <p className="text-mist-400 leading-relaxed">{isRTL?'درصد هر پله از حجم اولیه است، نه حجم باقی‌مانده. رسیدن به تارگت یا زمان آن تضمین‌شده نیست.':'Each percentage refers to the original position, not the remainder. Target achievement and timing are not guaranteed.'}</p>
    <div className="space-y-2">{rows.map(level=><div key={level.label} data-tp-row className="flex justify-between items-start gap-3 border-b border-ink-600 pb-2 last:border-0">
      <span className="text-up tnum shrink-0">{level.label} · {fmtPrice(level.price)}</span>
      <span className="text-mist-300 text-end min-w-0 break-words">{isRTL?'خروج':'Close'} {level.pct}%
        {level.quantity!=null&&<span className="block tnum" dir="ltr">≈ {Number(level.quantity.toPrecision(8))} {unit}</span>}
      </span>
    </div>)}</div>
    {execution==='single' ? <div role="note" className="text-mist-300 leading-relaxed space-y-1">
      <p>{isRTL?`توجه: این فرم فقط یک TP برای کل پوزیشن می‌فرستد: ${fmtPrice(target)}. سه خروج بالا خودکار ثبت نمی‌شوند.`:`This form submits one TP for the entire position: ${fmtPrice(target)}. The three exits above are not placed automatically.`}</p>
      <p>{isRTL?'برای اجرای این برنامه، سفارش‌های خروج Reduce-only/کاهش پوزیشن را در صرافی با قیمت و مقدار هر ردیف تنظیم کنید؛ ثبت معامله در ژورنال جای سفارش صرافی را نمی‌گیرد.':'To execute the plan, configure reduce-only position exits on the exchange at the listed prices and quantities; a journal entry is not an exchange order.'}</p>
      <p>{isRTL?'در دمو این فرم نیز TP تک‌قیمتی است؛ جدول بالا صرفاً راهنمای پله‌هاست. برنامه خودکار قبلی را بدون هماهنگی با سفارش‌های خروج پله‌ای هم‌زمان نگه ندارید.':'This demo form also uses a single TP; the table is guidance only. Coordinate existing automatic exits before adding staged exits.'}</p>
    </div>:<p className="text-mist-400 leading-relaxed">{isRTL?'این پله‌ها در ژورنال ثبت می‌شوند؛ ثبت ژورنال به‌معنی ارسال سفارش خروج پله‌ای به صرافی نیست.':'These levels are recorded in the journal; logging does not submit staged exchange exit orders.'}</p>}
  </section>;
}
