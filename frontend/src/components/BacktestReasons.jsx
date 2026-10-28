import { useI18n } from '../i18n/index.jsx';

export function BacktestReasons({ diagnostics }) {
  const { t } = useI18n();
  if (!diagnostics) return null;
  const groups = [
    ['base_wait_reasons', 'bt_base_reasons'],
    ['strategy_veto_reasons', 'bt_strategy_reasons'],
  ];
  const hasReasons = groups.some(([key]) => Object.keys(diagnostics[key] || {}).length);
  if (!hasReasons) return null;
  return (
    <div className="my-3 space-y-2 text-xs text-mist-300">
      {groups.map(([key, title]) => {
        const reasons = Object.entries(diagnostics[key] || {}).sort((a, b) => b[1].count - a[1].count);
        if (!reasons.length) return null;
        return (
          <details key={key} open className="rounded-lg border border-ink-500 p-2">
            <summary className="cursor-pointer font-medium">{t(title)}</summary>
            <ul className="mt-2 space-y-2">
              {reasons.map(([code, item]) => {
                const label = `bt_reason_${code}`;
                return (
                  <li key={code}>
                    <span>{t(label) === label ? code : t(label)}: <b>{item.count}</b></span>
                    <details className="mt-1 text-mist-500">
                      <summary className="cursor-pointer">{t('bt_reason_example')}</summary>
                      <p dir="auto" className="mt-1 break-words">{item.example}</p>
                    </details>
                  </li>
                );
              })}
            </ul>
          </details>
        );
      })}
      <p className="text-mist-500">{t('bt_reason_overlap')}</p>
    </div>
  );
}
