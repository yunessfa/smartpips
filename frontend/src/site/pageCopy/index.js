import { useI18n } from "../../i18n/index.jsx";
import en from "./en.js";
import fa from "./fa.js";

/**
 * Copy for the public sub-pages, split by locale so neither file grows past
 * the point of being editable.
 *
 * TWO THINGS TO SET BEFORE LAUNCH
 *
 * 1. Plan prices — `pricing.plans[].price` in en.js and fa.js are placeholders
 *    ("—"). I am not going to invent your commercial terms, so they sit in one
 *    obvious place for you to fill in. Left as "—", the page renders as
 *    "pricing on request", which is a legitimate state, not a broken one.
 * 2. CONTACT_EMAIL below — the contact form has no backend endpoint, so it
 *    composes a mail message instead of silently dropping submissions. Point it
 *    at the inbox you actually read.
 */

export const CONTACT_EMAIL = "support@smartpips.ir";

export const pageCopy = { en, fa };

/** Persian is the default locale, matching the rest of the app. */
export function usePageCopy() {
  const { lang } = useI18n();
  return lang === "en" ? en : fa;
}

export { en, fa };
