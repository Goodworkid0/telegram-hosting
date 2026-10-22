import React from 'react'
import ReactDOM from 'react-dom/client'
import { MotionGlobalConfig } from 'framer-motion'
import App from './App'
import './index.css'

// Disable ALL framer-motion animations app-wide. Animated transforms / exit
// animations (AnimatePresence) repeatedly re-composite GPU layers, which crashes
// the Telegram Desktop webview ("web viewer crashed") on interactions like opening
// the post three-dots menu or navigating back out of a DM. With this flag every
// motion component jumps straight to its target state (instant, no tweening), so
// the UI still works — it just doesn't animate. Cheap insurance vs a hard crash.
MotionGlobalConfig.skipAnimations = true

// Capture client-side errors so a crash leaves a trace we can read (backend logs +
// localStorage), instead of the webview silently dying. If a NATIVE crash occurs
// (GPU/renderer), no JS handler fires and nothing is logged — which itself tells us
// the crash is native, not a JS exception.
function reportClientError(kind, detail) {
  try {
    const payload = JSON.stringify({ kind, detail, url: location.href, platform: window.Telegram?.WebApp?.platform, version: window.Telegram?.WebApp?.version, t: Date.now() })
    localStorage.setItem('__lastClientError', payload)
    navigator.sendBeacon?.('/api/client-error', payload)
  } catch (_) {}
}
window.addEventListener('error', (e) => reportClientError('error', { message: e.message, source: e.filename, line: e.lineno, col: e.colno, stack: e.error?.stack?.slice(0, 1500) }))
window.addEventListener('unhandledrejection', (e) => reportClientError('unhandledrejection', { reason: String(e.reason), stack: e.reason?.stack?.slice(0, 1500) }))
// On (re)load after a crash, surface the last captured error to the console.
try { const prev = localStorage.getItem('__lastClientError'); if (prev) console.error('[PREVIOUS CLIENT ERROR]', prev) } catch (_) {}

// Telegram Mini App - expand to full screen
if (window.Telegram?.WebApp) {
  window.Telegram.WebApp.expand()
  window.Telegram.WebApp.ready()
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
