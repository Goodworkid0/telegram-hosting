import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Shield, User, Key, Check, ArrowRight, Camera, FileText, Settings } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import api from '../lib/api'
import { useT } from '../lib/i18n'

export default function OnboardingModal() {
  const t = useT()
  const { user, setUser } = useAuthStore()
  const [firstName, setFirstName] = useState(user?.first_name || '')
  const [password, setPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [showTelegram, setShowTelegram] = useState(true)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)

  // Stay mounted through the post-setup "done" checklist: setUser() flips
  // is_setup_complete=true immediately, so without `!done` the modal would
  // vanish before the success screen ever renders.
  if (!user || (user.is_setup_complete && !done)) return null

  const validatePassword = (pw) => {
    if (pw.length < 6) return t('modals.onboarding.pw_min')
    if (!/\d/.test(pw)) return t('modals.onboarding.pw_digit')
    return null
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')

    if (!firstName.trim()) { setError(t('modals.onboarding.name_required')); return }
    if (password !== passwordConfirm) { setError(t('modals.onboarding.pw_mismatch')); return }
    const pwError = validatePassword(password)
    if (pwError) { setError(pwError); return }

    setLoading(true)
    try {
      const { data } = await api.post('/api/auth/setup', {
        pin: password, first_name: firstName.trim(), show_telegram: showTelegram,
      })
      setUser(data)
      setDone(true)
    } catch (err) {
      setError(err.response?.data?.detail || t('modals.onboarding.setup_failed'))
    } finally {
      setLoading(false)
    }
  }

  const isValid = firstName.trim().length >= 1 && password.length >= 6 && password === passwordConfirm && /\d/.test(password)

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/90 backdrop-blur-sm p-4">
      <AnimatePresence mode="wait">
        {!done ? (
          <motion.div
            key="form"
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -10 }}
            transition={{ type: 'spring', damping: 26, stiffness: 400 }}
            className="bg-dark-900 border border-primary-500/20 shadow-neon-cyan rounded-2xl max-w-sm w-full overflow-hidden"
          >
            <div className="p-6 border-b border-primary-500/10 bg-dark-950/50">
              <div className="w-12 h-12 rounded-2xl bg-primary-500/10 border border-primary-500/20 flex items-center justify-center mb-4 shadow-neon-cyan">
                <Shield size={22} className="text-primary-400" />
              </div>
              <h2 className="text-lg font-semibold text-white font-display tracking-tight">{t('modals.onboarding.title')}</h2>
              <p className="text-sm text-dark-400 mt-1">{t('modals.onboarding.subtitle')}</p>
            </div>

            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              <div>
                <label className="flex items-center gap-2 text-xs font-medium text-dark-300 mb-1.5 uppercase tracking-wider">
                  <User size={12} /> {t('modals.onboarding.display_name')}
                </label>
                <input
                  type="text"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  placeholder={t('modals.onboarding.display_name_ph')}
                  maxLength={64}
                  className="w-full bg-dark-800/50 border border-dark-700 rounded-xl px-3 py-3 text-sm text-white placeholder-dark-500 focus:border-primary-500/50 focus:outline-none focus:bg-dark-800 transition-all"
                  autoFocus
                />
                <p className="text-[10px] text-dark-500 mt-1 ml-1">{t('modals.onboarding.display_name_hint')}</p>
              </div>

              <div>
                <label className="flex items-center gap-2 text-xs font-medium text-dark-300 mb-1.5 uppercase tracking-wider">
                  <Key size={12} /> {t('modals.onboarding.password')}
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={t('modals.onboarding.password_ph')}
                  className="w-full bg-dark-800/50 border border-dark-700 rounded-xl px-3 py-3 text-sm text-white placeholder-dark-500 focus:border-primary-500/50 focus:outline-none focus:bg-dark-800 transition-all"
                />
                <p className="text-[10px] text-dark-500 mt-1 ml-1">
                  {t('modals.onboarding.password_hint')}
                </p>
              </div>

              <div>
                <label className="flex items-center gap-2 text-xs font-medium text-dark-300 mb-1.5 uppercase tracking-wider">
                  <Check size={12} /> {t('modals.onboarding.confirm_password')}
                </label>
                <input
                  type="password"
                  value={passwordConfirm}
                  onChange={(e) => setPasswordConfirm(e.target.value)}
                  placeholder={t('modals.onboarding.confirm_password_ph')}
                  className={`w-full bg-dark-800/50 border rounded-xl px-3 py-3 text-sm text-white placeholder-dark-500 focus:outline-none focus:bg-dark-800 transition-all ${
                    passwordConfirm && password === passwordConfirm ? 'border-neon-500/50' : 'border-dark-700 focus:border-primary-500/50'
                  }`}
                />
              </div>

              <div className="rounded-xl bg-dark-800/40 border border-dark-700 p-3">
                <label className="flex items-start gap-3 cursor-pointer select-none">
                  <span className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors duration-200 mt-0.5 ${showTelegram ? 'bg-neon-500/25 border-neon-500/60' : 'bg-dark-800 border-dark-600'}`}>
                    <span className={`inline-block h-3.5 w-3.5 rounded-full transition-transform duration-200 ${showTelegram ? 'translate-x-4 bg-neon-400' : 'translate-x-1 bg-dark-400'}`} />
                  </span>
                  <input type="checkbox" checked={showTelegram} onChange={(e) => setShowTelegram(e.target.checked)} className="sr-only" />
                  <span className="min-w-0">
                    <span className="block text-xs font-medium text-dark-200 uppercase tracking-wider">{t('modals.onboarding.show_handle')}</span>
                    <span className="block text-[11px] text-dark-400 mt-0.5 leading-relaxed">
                      {t('modals.onboarding.handle_desc_before')}<span className="text-primary-300">@{user?.username || 'handle'}</span>{t('modals.onboarding.handle_desc_after')}
                    </span>
                  </span>
                </label>
              </div>

              {error && (
                <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2.5">{error}</p>
              )}

              <button
                type="submit"
                disabled={loading || !isValid}
                className="w-full py-3 rounded-xl font-semibold text-sm transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed bg-primary-500 hover:bg-primary-400 text-dark-950 shadow-lg shadow-primary-500/20 hover:shadow-neon-cyan active:scale-[0.98]"
              >
                {loading ? t('modals.onboarding.creating') : t('modals.onboarding.enter')}
              </button>
            </form>
          </motion.div>
        ) : (
          <motion.div
            key="done"
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ type: 'spring', damping: 26, stiffness: 400 }}
            className="bg-dark-900 border border-neon-500/20 shadow-neon-green rounded-2xl max-w-sm w-full overflow-hidden"
          >
            <div className="p-6 border-b border-neon-500/10 bg-dark-950/50 text-center">
              <div className="w-12 h-12 rounded-2xl bg-neon-500/10 border border-neon-500/20 flex items-center justify-center mb-4 mx-auto shadow-neon-green">
                <Check size={22} className="text-neon-400" />
              </div>
              <h2 className="text-lg font-semibold text-white font-display tracking-tight">{t('modals.onboarding.ready_title')}</h2>
              <p className="text-sm text-dark-400 mt-1">{t('modals.onboarding.ready_subtitle')}</p>
            </div>

            <div className="p-6 space-y-3">
              <Link to={`/profile/${user?.id}`} className="flex items-center gap-3 p-3 rounded-xl bg-dark-800/50 border border-dark-700 hover:border-primary-500/30 transition-all group">
                <div className="w-9 h-9 rounded-lg bg-primary-500/10 flex items-center justify-center group-hover:bg-primary-500/20 transition-colors">
                  <Camera size={16} className="text-primary-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-white">{t('modals.onboarding.set_avatar')}</div>
                  <div className="text-xs text-dark-400">{t('modals.onboarding.set_avatar_desc')}</div>
                </div>
                <ArrowRight size={14} className="text-dark-500 group-hover:text-primary-400 transition-colors flex-shrink-0" />
              </Link>

              <Link to={`/profile/${user?.id}`} className="flex items-center gap-3 p-3 rounded-xl bg-dark-800/50 border border-dark-700 hover:border-primary-500/30 transition-all group">
                <div className="w-9 h-9 rounded-lg bg-primary-500/10 flex items-center justify-center group-hover:bg-primary-500/20 transition-colors">
                  <FileText size={16} className="text-primary-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-white">{t('modals.onboarding.write_bio')}</div>
                  <div className="text-xs text-dark-400">{t('modals.onboarding.write_bio_desc')}</div>
                </div>
                <ArrowRight size={14} className="text-dark-500 group-hover:text-primary-400 transition-colors flex-shrink-0" />
              </Link>

              <Link to="/settings" className="flex items-center gap-3 p-3 rounded-xl bg-dark-800/50 border border-dark-700 hover:border-primary-500/30 transition-all group">
                <div className="w-9 h-9 rounded-lg bg-primary-500/10 flex items-center justify-center group-hover:bg-primary-500/20 transition-colors">
                  <Settings size={16} className="text-primary-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-white">{t('modals.onboarding.settings')}</div>
                  <div className="text-xs text-dark-400">{t('modals.onboarding.settings_desc')}</div>
                </div>
                <ArrowRight size={14} className="text-dark-500 group-hover:text-primary-400 transition-colors flex-shrink-0" />
              </Link>

              <button
                onClick={() => setDone(false)}
                className="w-full py-2.5 rounded-xl text-sm text-dark-400 hover:text-white hover:bg-dark-800 transition-colors mt-2"
              >
                {t('modals.onboarding.skip')}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
