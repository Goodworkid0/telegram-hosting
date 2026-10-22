import { createContext, useContext, useState, useCallback } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { CheckCircle, AlertTriangle, Info, X, Bell, Wallet, ShoppingCart, Gavel } from 'lucide-react'

const ToastContext = createContext(null)

const ICONS = {
  success: CheckCircle,
  error: AlertTriangle,
  info: Info,
  order: ShoppingCart,
  wallet: Wallet,
  dispute: Gavel,
  notification: Bell,
}

const COLORS = {
  success: 'border-green-500/40 bg-green-500/10 text-green-300',
  error: 'border-red-500/40 bg-red-500/10 text-red-300',
  info: 'border-cyan-500/40 bg-cyan-500/10 text-cyan-300',
  order: 'border-green-500/40 bg-green-500/10 text-green-300',
  wallet: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
  dispute: 'border-orange-500/40 bg-orange-500/10 text-orange-300',
  notification: 'border-primary-500/40 bg-primary-500/10 text-primary-300',
}

let toastId = 0

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const addToast = useCallback((message, { type = 'info', duration = 4000, title } = {}) => {
    const id = ++toastId
    setToasts(prev => [...prev.slice(-4), { id, message, type, title }])
    if (duration > 0) {
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== id))
      }, duration)
    }
    return id
  }, [])

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const showToast = useCallback((message, type = 'info', title) => {
    return addToast(message, { type, title })
  }, [addToast])

  return (
    <ToastContext.Provider value={{ addToast, removeToast, showToast }}>
      {children}
      {/* Toast container — top-center */}
      <div className="fixed top-16 left-1/2 -translate-x-1/2 z-[9999] flex flex-col gap-2 w-[92vw] max-w-sm pointer-events-none">
        <AnimatePresence mode="popLayout">
          {toasts.map(toast => {
            const Icon = ICONS[toast.type] || Info
            const color = COLORS[toast.type] || COLORS.info
            return (
              <motion.div
                key={toast.id}
                layout
                role="alert"
                aria-live="assertive"
                initial={{ opacity: 0, y: -30, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -20, scale: 0.95 }}
                transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                className={`pointer-events-auto rounded-xl border backdrop-blur-md px-4 py-3 shadow-lg flex items-start gap-3 ${color}`}
              >
                <Icon size={18} className="flex-shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  {toast.title && (
                    <p className="text-sm font-semibold leading-tight">{toast.title}</p>
                  )}
                  <p className="text-xs opacity-90 leading-tight mt-0.5">{toast.message}</p>
                </div>
                <button
                  onClick={() => removeToast(toast.id)}
                  className="flex-shrink-0 opacity-50 hover:opacity-100 transition-opacity"
                >
                  <X size={14} />
                </button>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
