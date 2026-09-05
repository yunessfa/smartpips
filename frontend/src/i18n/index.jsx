import { createContext, useContext, useEffect, useState } from "react";
import { translations } from "./translations";

const I18nContext = createContext(null);

export function I18nProvider({ children }) {
  const [lang, setLang] = useState(() => localStorage.getItem("lang") || "fa");

  useEffect(() => {
    localStorage.setItem("lang", lang);
    const dir = lang === "fa" ? "rtl" : "ltr";
    document.documentElement.lang = lang;
    document.documentElement.dir = dir;
    document.documentElement.classList.toggle("font-fa", lang === "fa");
  }, [lang]);

  const t = (key) =>
    translations[lang]?.[key] ?? translations.en[key] ?? key;

  const value = {
    lang,
    setLang,
    toggle: () => setLang((l) => (l === "fa" ? "en" : "fa")),
    t,
    dir: lang === "fa" ? "rtl" : "ltr",
    isRTL: lang === "fa",
  };

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside I18nProvider");
  return ctx;
}
