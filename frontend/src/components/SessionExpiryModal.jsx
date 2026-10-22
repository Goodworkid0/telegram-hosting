import { useEffect, useRef, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Clock, LogOut, RefreshCw } from 'lucide-react'
import { useT } from '../lib/i18n'

let _showSessionExpiry = null
const registerSessionExpiry = (fn) => { _showSessionExpiry = fn }
export const triggerSessionExpiryModal = (secondsLeft) =>
  _showSessionExpiry ? _showSessionExpiry(secondsLeft) : Promise.resolve(false)

export default function SessionExpiryModal() {
  const t = useT()
  const [state, setState] = useState(null)
  const resolveRef = useRef(null)
  const countdownRef = useRef(null)

  const show = useCallback((secondsLeft) => {
    return new Promise((resolve) => {
      resolveRef.current = resolve
      setState({ secondsLeft })
    })
  }, [])

  useEffect(() => {
    registerSessionExpiry(show)
    return () => registerSessionExpiry(null)
  }, [show])

  useEffect(() => {
    if (!state) {
      if (countdownRef.current) {
        clearInterval(countdownRef.current)
        countdownRef.current = null
      }
      return
    }

    countdownRef.current = setInterval(() => {
      setState((prev) => {
        if (!prev) return null
        const next = prev.secondsLeft - 1
        if (next <= 0) {
          clearInterval(countdownRef.current)
          countdownRef.current = null
          resolveRef.current?.(false)
          resolveRef.current = null
          return null
        }
        return { secondsLeft: next }
      })
    }, 1000)

    return () => {
      if (countdownRef.current) {
        clearInterval(countdownRef.current)
        countdownRef.current = null
      }
    }
  }, [state?.secondsLeft])

  const handleExtend = () => {
    if (countdownRef.current) {
      clearInterval(countdownRef.current)
      countdownRef.current = null
    }
    resolveRef.current?.(true)
    resolveRef.current = null
    setState(null)
  }

  const handleLogout = () => {
    if (countdownRef.current) {
      clearInterval(countdownRef.current)
      countdownRef.current = null
    }
    resolveRef.current?.(false)
    resolveRef.current = null
    setState(null)
  }

  const formatTime = (seconds) => {
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  return (
    <AnimatePresence>
      {state && (
        <motion.div
          key="session-expiry-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
        >
          <motion.div
            key="session-expiry-box"
            initial={{ opacity: 0, scale: 0.92, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.92, y: 12 }}
            transition={{ type: 'spring', damping: 24, stiffness: 380 }}
            className="bg-dark-900 border border-dark-700 rounded-2xl p-6 max-w-sm w-full shadow-2xl"
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-amber-500/15 flex items-center justify-center flex-shrink-0">
                <Clock size={20} className="text-amber-400" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">{t('modals.session.title')}</h3>
                <p className="text-xs text-dark-400">
                  {t('modals.session.expires_in', { time: formatTime(state.secondsLeft) })}
                </p>
              </div>
            </div>

            <p className="text-sm text-dark-200 mb-6 leading-relaxed">
              {t('modals.session.body')}
            </p>

            <div className="flex gap-3">
              <button
                onClick={handleLogout}
                className="flex items-center gap-2 flex-1 text-sm py-2.5 rounded-xl font-medium bg-dark-800 hover:bg-dark-700 text-dark-300 border border-dark-700 transition-colors justify-center"
              >
                <LogOut size={15} />
                {t('modals.session.logout')}
              </button>
              <button
                onClick={handleExtend}
                className="flex items-center gap-2 flex-1 text-sm py-2.5 rounded-xl font-medium bg-primary-500 hover:bg-primary-600 text-white transition-colors justify-center"
              >
                <RefreshCw size={15} />
                {t('modals.session.stay')}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
