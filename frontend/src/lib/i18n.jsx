/**
 * English-only string lookup. Kept as the same t()/useT() API the pages were
 * written against so call sites don't change; the multi-language machinery
 * (language store, ru/es/zh dictionaries, picker) was removed with the fork.
 *
 * Usage in components:
 *   const t = useT()
 *   <h1>{t('settings.title')}</h1>
 */
import en from './locales/en'

/** Date-formatting locale (fixed). */
export function getDateLocale() {
  return 'en-US'
}

/** Translate — `{name}` placeholders are interpolated from `vars`. */
export function t(key, vars) {
  let s = en[key] ?? key
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      s = s.replaceAll(`{${k}}`, String(v))
    }
  }
  return s
}

/** Hook alias — kept for call-site compatibility. */
export function useT() {
  return t
}
