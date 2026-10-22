import { getDateLocale, t } from './i18n'

function decodeJwtPayload(token) {
  if (!token) return null
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    const payload = parts[1]
    const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(decoded)
  } catch {
    return null
  }
}

export function getTokenExpiryMs(token) {
  const payload = decodeJwtPayload(token)
  if (!payload?.exp) return null
  return payload.exp * 1000
}

// The backend serializes naive UTC timestamps with no timezone suffix
// (e.g. "2026-06-24T10:00:00"). JS parses such strings as LOCAL time, which skews
// relative times by the viewer's offset — west-of-UTC users saw everything as
// "just now". Treat zone-less ISO datetimes as UTC by appending "Z".
export function parseDate(dateStr) {
  if (!dateStr) return null
  let s = dateStr
  if (typeof s === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(s)) {
    s += 'Z'
  }
  return new Date(s)
}

export function timeAgo(dateStr) {
  if (!dateStr) return t('time.never')
  const diff = Date.now() - parseDate(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return t('time.just_now')
  if (mins < 60) return t('time.m_ago', { n: mins })
  const hours = Math.floor(mins / 60)
  if (hours < 24) return t('time.h_ago', { n: hours })
  const days = Math.floor(hours / 24)
  if (days < 30) return t('time.d_ago', { n: days })
  const months = Math.floor(days / 30)
  if (months < 12) return t('time.mo_ago', { n: months })
  return t('time.y_ago', { n: Math.floor(months / 12) })
}

export function formatDate(dateStr, options = {}) {
  if (!dateStr) return ''
  const date = parseDate(dateStr)
  if (options.relative) {
    const today = new Date()
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)
    if (date.toDateString() === today.toDateString()) return t('time.today')
    if (date.toDateString() === yesterday.toDateString()) return t('time.yesterday')
    return date.toLocaleDateString(getDateLocale(), { month: 'short', day: 'numeric', year: date.getFullYear() !== today.getFullYear() ? 'numeric' : undefined })
  }
  if (options.time) {
    return t('time.at', {
      date: date.toLocaleDateString(getDateLocale(), { month: 'short', day: 'numeric', year: 'numeric' }),
      time: date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    })
  }
  return date.toLocaleDateString(getDateLocale())
}

// Premium appearance: a user's chosen name color (profile_theme.name_color)
// takes PRIORITY over their role color wherever their name is rendered.
function parseProfileTheme(user) {
  const raw = user?.profile_theme
  if (!raw) return null
  try { return typeof raw === 'string' ? JSON.parse(raw) : raw } catch { return null }
}

function customNameColor(user) {
  const c = parseProfileTheme(user)?.name_color
  return typeof c === 'string' && c ? c : null
}

// Inline style for a username element, or undefined. An inline color always
// overrides a Tailwind text-color class, so spreading this next to the existing
// role className makes the premium color win automatically.
export function nameColorStyle(user) {
  const c = customNameColor(user)
  return c ? { color: c } : undefined
}

export function displayName(user, showAt = true) {
  if (!user) return 'unknown'
  if (user.show_telegram === false) {
    return user.first_name || 'User'
  }
  const name = user.username || user.first_name
  if (!name) return 'User'
  return showAt ? `@${name}` : name
}

// The plain display name (never the @handle).
export function realName(user) {
  if (!user) return 'unknown'
  return user.first_name || user.username || 'User'
}

// The @handle to show alongside the display name, or null when it shouldn't be
// shown (privacy off, no username, or it would just duplicate the display name).
export function telegramHandle(user) {
  if (!user || user.show_telegram === false || !user.username) return null
  if (user.username === user.first_name) return null
  return `@${user.username}`
}

// Normalize a user-authored link href so scheme-less URLs don't resolve relative
// to the current page (which made "example.com" or the literal "url" placeholder
// route to /app/thread/example.com on our own platform). Returns a safe href and
// whether it points outside the app (external links open in a new tab).
export function normalizeLinkHref(href) {
  const blocked = { href: undefined, isExternal: false }
  if (!href || typeof href !== 'string') return blocked
  const h = href.trim()
  if (!h) return blocked

  // Protocol-relative URLs (//host/path) → external https. Check before the
  // single-slash case below, since "//cdn.com" also starts with "/".
  if (h.startsWith('//')) return { href: `https:${h}`, isExternal: true }

  // In-page anchors and root-relative app paths stay internal.
  if (h.startsWith('#') || h.startsWith('/')) return { href: h, isExternal: false }

  // Standard web/contact schemes pass through; only http(s) opens in a new tab.
  if (/^https?:/i.test(h)) return { href: h, isExternal: true }
  if (/^(mailto:|tel:)/i.test(h)) return { href: h, isExternal: false }

  // Block any other scheme (javascript:, data:, vbscript:, …) outright.
  if (/^[a-z][a-z0-9+.-]*:/i.test(h)) return blocked

  // Bare domain or "domain/path" (e.g. example.com, www.foo.com/bar) → external https.
  return { href: `https://${h}`, isExternal: true }
}
