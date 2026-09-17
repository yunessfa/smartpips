import { useEffect, useMemo, useRef, useState } from "react";
import { Badge, Button, Spinner } from "../components/ui.jsx";
import { SignalChart, indicatorsToStudies, resolveTVSymbol } from "../components/TradingView.jsx";
import { LogTradeModal } from "../components/TradeModal.jsx";
import { chatApi, strategyApi, tradesApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";
import { useLiveCtx, useLivePrice, useLivePricesFor, isCryptoSymbol } from "../live/LivePrices.jsx";
import { parsePrice, fmtPrice } from "../lib/num.js";

// Core symbols we always keep a live price for (used to ground the AI).
const CORE_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];

export default function Chat() {
  const { t, isRTL } = useI18n();
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [studies, setStudies] = useState([]);
  const live = useLiveCtx();
  useLivePricesFor(CORE_SYMBOLS); // keep live prices ready to ground the AI
  const scrollRef = useRef(null);
  const taRef = useRef(null);

  async function loadConversations() {
    try { setConversations(await chatApi.conversations()); } catch { /* ignore */ }
  }
  useEffect(() => { loadConversations(); }, []);

  useEffect(() => {
    strategyApi
      .indicators()
      .then((list) => setStudies(indicatorsToStudies(list.filter((i) => i.is_active))))
      .catch(() => {});
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  function autosize() {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 180) + "px";
  }

  async function openConversation(id) {
    setActiveId(id);
    setSidebarOpen(false);
    try {
      const conv = await chatApi.conversation(id);
      setMessages(conv.messages);
    } catch (e) { setError(e.message); }
  }

  function newChat() {
    setActiveId(null);
    setMessages([]);
    setError(null);
    setSidebarOpen(false);
  }

  async function send(text) {
    const content = (text ?? input).trim();
    if (!content || sending) return;
    setError(null);
    setInput("");
    if (taRef.current) taRef.current.style.height = "auto";
    setMessages((m) => [...m, { role: "user", content, id: `u-${Date.now()}` }]);
    setSending(true);
    try {
      const snapshot = {};
      const map = live?.prices || {};
      for (const sym of Object.keys(map)) {
        if (Number.isFinite(map[sym]?.price)) snapshot[sym] = map[sym].price;
      }
      const res = await chatApi.send(content, activeId, snapshot);
      setActiveId(res.conversation_id);
      setMessages((m) => [...m, res.message]);
      loadConversations(); // refresh history list / titles
    } catch (e) {
      setError(e.message);
    } finally {
      setSending(false);
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  }

  async function deleteConversation(id, e) {
    e.stopPropagation();
    try {
      await chatApi.remove(id);
      if (id === activeId) newChat();
      loadConversations();
    } catch { /* ignore */ }
  }

  const HistoryList = (
    <div className="h-full flex flex-col bg-ink-800">
      <div className="p-3">
        <Button onClick={newChat} className="w-full">+ {t("new_chat")}</Button>
      </div>
      <div className="px-3 pb-2 text-xs font-medium text-mist-500">{t("chat_history")}</div>
      <div className="flex-1 overflow-y-auto px-2 pb-3 space-y-1">
        {conversations.length === 0 ? (
          <p className="text-mist-500 text-xs px-2">{t("no_chats")}</p>
        ) : (
          conversations.map((c) => (
            <div
              key={c.id}
              onClick={() => openConversation(c.id)}
              className={`group flex items-center justify-between gap-2 px-3 py-2 rounded-lg cursor-pointer transition ${
                c.id === activeId ? "bg-ink-600" : "hover:bg-ink-700"
              }`}
            >
              <span className="text-sm text-mist-100 truncate flex-1">{c.title}</span>
              <button
                onClick={(e) => deleteConversation(c.id, e)}
                className="opacity-0 group-hover:opacity-100 text-mist-500 hover:text-down text-xs shrink-0"
                aria-label={t("delete")}
              >✕</button>
            </div>
          ))
        )}
      </div>
    </div>
  );

  return (
    <div className="flex-1 flex min-h-0">
      {/* desktop history sidebar */}
      <aside className={`hidden lg:block w-64 shrink-0 ${isRTL ? "border-l" : "border-r"} border-ink-500`}>
        {HistoryList}
      </aside>

      {/* mobile history drawer */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setSidebarOpen(false)} />
          <aside className={`absolute top-0 ${isRTL ? "right-0" : "left-0"} h-full w-72`}>{HistoryList}</aside>
        </div>
      )}

      {/* conversation column */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="flex items-center justify-between gap-3 px-4 md:px-6 py-3 border-b border-ink-500 bg-ink-800/60 backdrop-blur">
          <div className="flex items-center gap-2 min-w-0">
            <button onClick={() => setSidebarOpen(true)} className="lg:hidden text-mist-300 p-1" aria-label={t("chat_history")}>
              <ListIcon />
            </button>
            <div className="min-w-0">
              <h1 className="text-base font-semibold text-mist-100 truncate">{t("chat_title")}</h1>
              <p className="text-xs text-mist-500 truncate hidden sm:block">{t("chat_subtitle")}</p>
            </div>
          </div>
          <Button variant="ghost" onClick={newChat}>{t("new_chat")}</Button>
        </header>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 md:px-8 py-6">
          <div className="max-w-3xl mx-auto space-y-5">
            {messages.length === 0 && !sending && <Welcome onPick={send} />}
            {messages.map((m, i) => <MessageBubble key={m.id ?? i} message={m} studies={studies} />)}
            {sending && (
              <div className="flex justify-start">
                <div className="bg-ink-700 border border-ink-500 rounded-2xl rounded-tl-sm px-4 py-3">
                  <Spinner label={t("analysing")} />
                </div>
              </div>
            )}
            {error && (
              <div className="text-down text-sm bg-down/10 border border-down/30 rounded-lg px-3 py-2">{error}</div>
            )}
          </div>
        </div>

        {/* composer */}
        <div className="border-t border-ink-500 bg-ink-800/70 backdrop-blur px-4 md:px-8 py-4">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-end gap-2 bg-ink-700 border border-ink-500 rounded-2xl px-3 py-2 focus-within:border-gold/50">
              <textarea
                ref={taRef}
                rows={1}
                value={input}
                onChange={(e) => { setInput(e.target.value); autosize(); }}
                onKeyDown={onKeyDown}
                placeholder={t("composer_placeholder")}
                className="flex-1 bg-transparent resize-none outline-none text-sm text-mist-100 placeholder-mist-500 max-h-44 py-1.5"
              />
              <Button onClick={() => send()} disabled={sending || !input.trim()}>{t("send")}</Button>
            </div>
            <p className="text-[11px] text-mist-500 mt-2 text-center"></p>
          </div>
        </div>
      </div>
    </div>
  );
}

function Welcome({ onPick }) {
  const { t } = useI18n();
  const pool = [
    "sugg_1", "sugg_2", "sugg_3", "sugg_4", "sugg_5",
    "sugg_6", "sugg_7", "sugg_8", "sugg_9", "sugg_10",
  ];
  // Pick 4 distinct suggestions at random, fresh on every mount / new chat.
  const suggestions = useMemo(() => {
    const shuffled = [...pool].sort(() => Math.random() - 0.5).slice(0, 4);
    return shuffled.map((k) => t(k));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div className="text-center py-10">
      <img src="/logo-icon.png" alt="SmartPips" className="h-14 w-14 rounded-2xl object-cover mb-4 mx-auto shadow-lg shadow-gold/20" />
      <h2 className="text-xl font-semibold text-mist-100">{t("welcome_title")}</h2>
      <p className="text-mist-500 text-sm mt-1">{t("welcome_sub")}</p>
      <div className="mt-6 grid sm:grid-cols-2 gap-2.5 max-w-xl mx-auto">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => onPick(s)}
            className="text-start text-sm text-mist-300 bg-ink-700/80 border border-ink-500 rounded-xl px-4 py-3 hover:border-gold/40 hover:text-mist-100 hover:bg-ink-700 transition"
          >{s}</button>
        ))}
      </div>
    </div>
  );
}

function MessageBubble({ message, studies }) {
  const { t } = useI18n();
  const isUser = message.role === "user";
  if (isUser) {
    return (
      <div className="flex justify-end rise">
        <div className="bg-gold text-ink-900 rounded-2xl rounded-tr-sm px-4 py-2.5 max-w-[85%] whitespace-pre-wrap text-sm font-medium shadow-lg shadow-gold/10">
          {message.content}
        </div>
      </div>
    );
  }
  const news = Array.isArray(message.news_used) ? message.news_used : [];
  const recs = Array.isArray(message.recommendations) ? message.recommendations : [];
  return (
    <div className="flex justify-start rise">
      <div className="max-w-[92%] w-full">
        <div className="bg-ink-700 border border-ink-500 rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-mist-100 whitespace-pre-wrap leading-relaxed">
          {message.content}
        </div>

        {news.length > 0 && (
          <div className="mt-2 bg-ink-800 border border-ink-500 rounded-xl px-3 py-2.5">
            <p className="text-xs text-mist-500 mb-1.5">📰 {t("news_referenced")}</p>
            <ul className="space-y-1">
              {news.map((n, i) => (
                <li key={i} className="text-xs">
                  <a href={n.link} target="_blank" rel="noreferrer" className="text-info hover:underline">{n.title}</a>
                  <span className="text-mist-500"> — {n.source}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {recs.length > 0 && (
          <div className="mt-3 grid gap-3">
            {recs.map((rec, i) => <RecommendationCard key={i} rec={rec} studies={studies} />)}
          </div>
        )}
      </div>
    </div>
  );
}

function RecommendationCard({ rec, studies }) {
  const { t } = useI18n();
  const [logging, setLogging] = useState(false);
  const [logged, setLogged] = useState(false);
  const tone = rec.action === "buy" ? "up" : rec.action === "sell" ? "down" : "neutral";
  const tvSymbol = resolveTVSymbol(rec);
  const usedInds = Array.isArray(rec.indicators_used) ? rec.indicators_used : [];

  // Live price for this symbol — crypto via WebSocket, metals via backend poll.
  const liveSym = (rec.symbol || "").toUpperCase();
  const livePrice = useLivePrice(liveSym);

  const initial = {
    symbol: rec.symbol,
    tradingview_symbol: tvSymbol,
    direction: rec.action === "sell" ? "short" : "long",
    entry_price: parsePrice(livePrice?.price ?? rec.entry),
    take_profit: parsePrice(rec.take_profit),
    stop_loss: parsePrice(rec.stop_loss),
    source: "assistant",
  };

  async function saveTrade(payload) {
    await tradesApi.create(payload);
    setLogged(true);
  }

  return (
    <div className="bg-ink-800 border border-ink-500 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-ink-500 flex-wrap gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold text-mist-100 tnum">{rec.symbol}</span>
          <Badge tone={tone}>{(rec.action || "hold").toUpperCase()}</Badge>
          {rec.confidence && <Badge tone="gold">{rec.confidence} {t("confidence")}</Badge>}
          {rec.risk_reward && <Badge tone="info">{t("risk_reward")}: {rec.risk_reward}</Badge>}
          {rec.timeframe && <Badge tone="info"><span className="tnum">{rec.timeframe}</span></Badge>}
        </div>
        {livePrice && Number.isFinite(livePrice.price) && (
          <div className="flex items-center gap-1.5 text-xs">
            <span className="h-1.5 w-1.5 rounded-full bg-up live-dot" />
            <span className="text-mist-500">{t("live")}:</span>
            <span className="tnum text-mist-100">${fmtPrice(livePrice.price)}</span>
            {Number.isFinite(livePrice.changePercent) && livePrice.changePercent !== 0 && (
              <span className={`tnum ${livePrice.changePercent >= 0 ? "text-up" : "text-down"}`}>
                ({livePrice.changePercent >= 0 ? "+" : ""}{fmtPrice(livePrice.changePercent)}%)
              </span>
            )}
          </div>
        )}
      </div>

      <div className="px-4 pt-3" style={{ height: "53%" }}><SignalChart symbol={tvSymbol} studies={studies} height={260} /></div>

      {usedInds.length > 0 && (
        <div className="px-4 pt-3 flex items-center gap-1.5 flex-wrap">
          {usedInds.map((ind, i) => <Badge key={i} tone="info">{ind}</Badge>)}
        </div>
      )}

      <div className="grid grid-cols-3 gap-2 px-4 py-3">
        <Level label={t("entry")} value={rec.entry} tone="info" />
        <Level label={t("take_profit")} value={rec.take_profit} tone="up" />
        <Level label={t("stop_loss")} value={rec.stop_loss} tone="down" />
      </div>
      {rec.rationale && <p className="px-4 text-xs text-mist-300 leading-relaxed">{rec.rationale}</p>}

      <div className="px-4 py-3">
        {logged ? (
          <p className="text-up text-sm">✓ {t("trade_logged")}</p>
        ) : (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-mist-500">{t("did_you_take")}</span>
            <Button onClick={() => setLogging(true)}>{t("yes_log_it")}</Button>
          </div>
        )}
      </div>

      {logging && (
        <LogTradeModal initial={initial} onClose={() => setLogging(false)} onSaved={saveTrade} />
      )}
    </div>
  );
}

function Level({ label, value, tone }) {
  const color = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-info";
  return (
    <div className="bg-ink-700 border border-ink-500 rounded-lg px-2 py-2 text-center">
      <p className="text-[11px] text-mist-500">{label}</p>
      <p className={`tnum text-sm font-medium mt-0.5 ${color}`}>{value || "—"}</p>
    </div>
  );
}

function ListIcon() { return (<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>); }
