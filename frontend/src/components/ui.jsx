export function Panel({ title, action, children, className = "" }) {
  return (
    <section className={`bg-ink-700/80 border border-ink-500 rounded-2xl shadow-panel overflow-hidden ${className}`}>
      {(title || action) && (
        <header className="flex items-center justify-between px-4 py-3 border-b border-ink-500 bg-gradient-to-b from-ink-600/40 to-transparent">
          <h2 className="text-sm font-semibold tracking-wide text-mist-100">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-4" style={{ height: '80%' }}>{children}</div>
    </section>
  );
}

export function Badge({ tone = "neutral", children }) {
  const tones = {
    neutral: "bg-ink-600 text-mist-300 border-ink-500",
    up: "bg-up/10 text-up border-up/30",
    down: "bg-down/10 text-down border-down/30",
    gold: "bg-gold/10 text-gold-soft border-gold/30",
    info: "bg-info/10 text-info border-info/30",
  };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium border ${tones[tone]}`}>
      {children}
    </span>
  );
}

export function Button({ variant = "primary", className = "", ...props }) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-gold/40 disabled:opacity-50 disabled:cursor-not-allowed";
  const variants = {
    primary: "bg-gradient-to-b from-gold-soft to-gold text-ink-900 hover:brightness-105 shadow-sm shadow-gold/20",
    ghost: "bg-ink-600 text-mist-100 hover:bg-ink-500 border border-ink-500",
    danger: "bg-down/15 text-down hover:bg-down/25 border border-down/30",
  };
  return <button className={`${base} ${variants[variant]} ${className}`} {...props} />;
}

export function Field({ label, hint, children }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium text-mist-300">{label}</span>
      {children}
      {hint && <span className="block text-xs text-mist-500">{hint}</span>}
    </label>
  );
}

export function Input(props) {
  return (
    <input
      {...props}
      className={`w-full bg-ink-800 border border-ink-500 rounded-lg px-3 py-2 text-sm text-mist-100 placeholder-mist-500 focus:outline-none focus:border-gold/50 focus:ring-1 focus:ring-gold/30 ${props.className || ""}`}
    />
  );
}

export function Select({ children, ...props }) {
  return (
    <select
      {...props}
      className={`w-full bg-ink-800 border border-ink-500 rounded-lg px-3 py-2 text-sm text-mist-100 focus:outline-none focus:border-gold/50 ${props.className || ""}`}
    >
      {children}
    </select>
  );
}

export function Spinner({ label }) {
  return (
    <div className="flex items-center gap-2 text-mist-500 text-sm">
      <span className="h-3 w-3 rounded-full border-2 border-mist-500 border-t-transparent animate-spin" />
      {label}
    </div>
  );
}
