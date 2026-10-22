import { useEffect, useRef, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { AlertTriangle } from 'lucide-react'
import { useT } from '../lib/i18n'

/* ── global bridge so non-React code can trigger our React modal ── */
let _showConfirm = null
const registerConfirm = (fn) => { _showConfirm = fn }
export const globalConfirm   = (msg) =>
  _showConfirm ? _showConfirm(msg) : Promise.resolve(window.confirm(msg))

export default function ConfirmModal() {
  const t = useT()
  const [state, setState] = useState(null) // { message }
  const resolveRef = useRef(null)

  const show = useCallback((message) => {
    return new Promise((resolve) => {
      resolveRef.current = resolve
      setState({ message })
    })
  }, [])

  useEffect(() => {
    registerConfirm(show)
    return () => registerConfirm(null)
  }, [show])

  const handleResult = (ok) => {
    resolveRef.current?.(ok)
    resolveRef.current = null
    setState(null)
  }

  return (
    <AnimatePresence>
      {state && (
        <motion.div
          key="confirm-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-[9998] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
          onClick={() => handleResult(false)}
          role="dialog"
          aria-modal="true"
          aria-label={t('modals.confirm.title')}
        >
          <motion.div
            key="confirm-box"
            initial={{ opacity: 0, scale: 0.92, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.92, y: 12 }}
            transition={{ type: 'spring', damping: 24, stiffness: 380 }}
            className="bg-dark-900 border border-dark-700 rounded-2xl p-5 max-w-sm w-full shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Icon */}
            <div className="flex items-center gap-3 mb-4">
              <div className="w-9 h-9 rounded-xl bg-primary-500/15 flex items-center justify-center flex-shrink-0">
                <AlertTriangle size={18} className="text-primary-400" />
              </div>
              <h3 className="text-sm font-semibold text-white">{t('modals.confirm.title')}</h3>
            </div>

            {/* Message */}
            <p className="text-sm text-dark-200 mb-5 leading-relaxed pl-12">
              {state.message}
            </p>

            {/* Buttons */}
            <div className="flex gap-3 pl-12">
              <button
                onClick={() => handleResult(false)}
                className="btn-secondary flex-1 text-sm py-2.5"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={() => handleResult(true)}
                className="flex-1 text-sm py-2.5 rounded-xl font-medium bg-primary-500 hover:bg-primary-600 text-white transition-colors"
              >
                {t('common.confirm')}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
