/** Read-only backend evidence. Unknown is never rendered as a green pass. */
export function DecisionAudit({ decision }) {
  const tree = decision?.explanation_tree;
  if (!tree) return null;
  const families = decision.evidence_model?.families || {};
  return <section aria-label="Decision evidence audit" className="sp-audit rounded-xl border border-ink-500 bg-ink-800 p-4 space-y-3 min-w-0">
    <div className="flex flex-wrap justify-between gap-2 text-sm"><strong>زمینه و شواهد تصمیم</strong><span className="font-mono text-gold">{tree.status}</span></div>
    <p className="text-xs text-mist-500">قدرت سیگنال: {decision.signal_strength ?? "—"}/100 · احتمال برد تاریخی: ناموجود</p>
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">{Object.entries(families).map(([name, family]) => <div key={name} className="border border-ink-500 rounded p-2 text-xs min-w-0"><span className="font-mono">{name}</span><span className="block text-mist-500 mt-1">{family.value == null ? "شواهد ثبت‌نشده" : `${family.value.toFixed(2)} · پژوهشی`}</span></div>)}</div>
    {tree.blocking_reasons?.length > 0 && <ul className="text-xs text-gold leading-6">{tree.blocking_reasons.map((r, i) => <li key={i} className="break-words">{r.code}: {r.message}</li>)}</ul>}
    <p className="text-xs text-mist-500 leading-6">این نمایش از پاسخ واقعی موتور است. مدل خانواده‌ها فعلاً سایه‌ای است و تصمیم اجرایی را تغییر نمی‌دهد. تأیید ورود در صرافی و همه محدودیت‌های ریسک از این کارت قابل استنتاج نیست.</p>
  </section>;
}
