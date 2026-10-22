import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { lazy, Suspense, useEffect, useState } from 'react'
import { useAuthStore } from './store/authStore'
import { useBrandingStore } from './store/brandingStore'
import { useT } from './lib/i18n'

// Lazy-loaded pages
const Files = lazy(() => import('./pages/Files'))
const Profile = lazy(() => import('./pages/Profile'))
const Shop = lazy(() => import('./pages/Shop'))
const Settings = lazy(() => import('./pages/Settings'))
const Notifications = lazy(() => import('./pages/Notifications'))
const Admin = lazy(() => import('./pages/Admin'))

// Components
import Layout from './components/Layout'
import ErrorBoundary from './components/ErrorBoundary'
import { ToastProvider } from './components/Toast'
import ConfirmModal from './components/ConfirmModal'
import SessionExpiryModal from './components/SessionExpiryModal'
import OnboardingModal from './components/OnboardingModal'

// Loading screen
function LoadingScreen() {
  const t = useT()
  const { appName, logoUrl, loaded } = useBrandingStore()
  const tg = window.Telegram?.WebApp
  const bgColor = tg?.themeParams?.bg_color || '#0f172a'
  const textColor = tg?.themeParams?.text_color || '#e2e8f0'
  const hintColor = tg?.themeParams?.hint_color || '#64748b'

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: bgColor }}>
      <div className="text-center">
        {loaded ? (
          <>
            {logoUrl ? (
              <img src={logoUrl} alt={appName} className="w-20 h-20 rounded-2xl mx-auto mb-4 shadow-lg" />
            ) : (
              <div className="w-20 h-20 bg-gradient-to-br from-primary-400 to-primary-600 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg shadow-primary-500/20">
                <span className="text-3xl font-bold text-white">{appName?.[0] || 'F'}</span>
              </div>
            )}
            <h1 className="font-display font-bold text-xl mb-1" style={{ color: textColor }}>{appName}</h1>
          </>
        ) : (
          <div className="w-20 h-20 rounded-2xl flex items-center justify-center mx-auto mb-4" style={{ backgroundColor: hintColor + '20' }}>
            <div className="w-8 h-8 border-2 border-primary-400 border-t-transparent rounded-full animate-spin" />
          </div>
        )}
        <p className="text-sm" style={{ color: hintColor }}>{t('app.loading')}</p>
        {tg && (
          <p className="text-xs mt-2 opacity-50" style={{ color: hintColor }}>
            v{tg.version}
          </p>
        )}
      </div>
    </div>
  )
}

// Telegram-only gate
function TelegramGate() {
  const t = useT()
  const { appName, logoUrl, botUsername } = useBrandingStore()
  return (
    <div className="min-h-screen bg-dark-950 flex items-center justify-center p-6">
      <div className="text-center max-w-sm">
        {logoUrl ? (
          <img src={logoUrl} alt={appName} className="w-20 h-20 rounded-2xl mx-auto mb-6 object-cover" />
        ) : (
          <div className="w-20 h-20 bg-gradient-to-br from-primary-400 to-primary-600 rounded-2xl flex items-center justify-center mx-auto mb-6">
            <span className="text-3xl font-bold">{appName?.[0] || 'F'}</span>
          </div>
        )}
        <h1 className="font-display font-bold text-2xl gradient-text mb-3">{appName}</h1>
        <p className="text-dark-300 text-sm mb-6">{t('app.telegram_only')}</p>
        <a
          href={`https://t.me/${botUsername}`}
          className="inline-flex items-center gap-2 bg-[#2AABEE] hover:bg-[#229ED9] text-white font-semibold px-6 py-3 rounded-xl transition-colors"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69.01-.03.01-.14-.07-.2-.08-.06-.2-.04-.28-.02-.12.02-2.02 1.28-5.69 3.77-.54.37-1.03.55-1.47.54-.48-.01-1.4-.27-2.09-.49-.84-.28-1.51-.42-1.45-.89.03-.25.38-.5 1.04-.78 4.07-1.77 6.79-2.94 8.15-3.51 3.88-1.62 4.69-1.9 5.21-1.91.12 0 .37.03.54.17.14.12.18.28.2.47-.01.06.01.24 0 .37z"/></svg>
          {t('app.open_in_telegram')}
        </a>
        <p className="text-dark-500 text-xs mt-4">{t('app.search_bot', { bot: botUsername })}</p>
      </div>
    </div>
  )
}

// Full-screen block shown to non-staff while maintenance mode is on
function MaintenanceScreen() {
  const t = useT()
  const { appName, logoUrl } = useBrandingStore()
  return (
    <div className="min-h-screen bg-dark-950 flex items-center justify-center p-6">
      <div className="text-center max-w-sm">
        {logoUrl ? (
          <img src={logoUrl} alt={appName} className="w-20 h-20 rounded-2xl mx-auto mb-6 object-cover opacity-60" />
        ) : (
          <div className="w-20 h-20 bg-dark-800 rounded-2xl flex items-center justify-center mx-auto mb-6">
            <span className="text-3xl">🔧</span>
          </div>
        )}
        <h1 className="font-display font-bold text-2xl mb-3">{appName}</h1>
        <p className="text-dark-300 text-sm mb-6">
          {t('app.maintenance')}
        </p>
        <button
          onClick={() => window.location.reload()}
          className="bg-primary-500 hover:bg-primary-400 text-white px-6 py-2 rounded-xl font-semibold transition-colors"
        >
          {t('common.retry')}
        </button>
      </div>
    </div>
  )
}

const ALLOW_BROWSER_VIEW = import.meta.env.VITE_ALLOW_BROWSER_VIEW === 'true'

const isTelegramWebApp = () => {
  if (ALLOW_BROWSER_VIEW) return true
  const tg = window.Telegram?.WebApp
  if (tg?.initData && tg.initData.length > 0) return true
  if (tg?.initDataUnsafe?.user) return true
  return false
}

function App() {
  const tGlobal = useT()
  const { initTelegram, restoreSession, devLogin, isInitialized, isLoading, user, isModerator } = useAuthStore()
  const { maintenanceMode } = useBrandingStore()
  const [blockedByGate, setBlockedByGate] = useState(false)

  useEffect(() => {
    useBrandingStore.getState().load()

    const init = async () => {
      if (!import.meta.env.DEV && !isTelegramWebApp()) {
        const hasSession = await restoreSession()
        if (!hasSession) {
          setBlockedByGate(true)
          return
        }
      }

      const hasSession = await restoreSession()
      
      if (!hasSession) {
        await initTelegram()
        
        if (!window.Telegram?.WebApp?.initDataUnsafe?.user) {
          if (import.meta.env.DEV || ALLOW_BROWSER_VIEW) {
            if (import.meta.env.DEV) console.log('Dev/Browser mode: auto-login')
            await devLogin('123456789')
          }
        }
      }
    }
    
    init()
  }, [])

  if (blockedByGate) return <TelegramGate />
  if (!isInitialized || isLoading) return <LoadingScreen />
  if (maintenanceMode && !isModerator()) return <MaintenanceScreen />
  if (!user && isTelegramWebApp()) return (
    <div className="min-h-screen bg-dark-950 flex items-center justify-center p-6">
      <div className="text-center max-w-sm">
        <p className="text-red-400 font-semibold mb-2">{tGlobal('app.signin_failed')}</p>
        <p className="text-dark-400 text-sm mb-4">{tGlobal('app.signin_failed_detail')}</p>
        <button onClick={() => window.location.reload()} className="bg-primary-500 text-white px-6 py-2 rounded-xl font-semibold">{tGlobal('common.retry')}</button>
      </div>
    </div>
  )

  return (
    <ToastProvider>
    <ConfirmModal />
    <SessionExpiryModal />
    <OnboardingModal />
    <BrowserRouter basename={import.meta.env.PROD ? '/app' : '/'}>
      <ErrorBoundary>
        <Suspense fallback={<LoadingScreen />}>
          <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Files />} />
          <Route path="files" element={<Files />} />
          <Route path="profile/:id" element={<Profile />} />
          <Route path="shop" element={<Shop />} />

          {/* Utility Routes */}
          <Route path="settings" element={<Settings />} />
          <Route path="wallet" element={<Navigate to="/shop" replace />} />
          <Route path="deposit" element={<Navigate to="/shop" replace />} />
          <Route path="notifications" element={<Notifications />} />

          {/* Admin */}
          <Route path="admin" element={<Admin />} />
        </Route>
        </Routes>
        </Suspense>
      </ErrorBoundary>
    </BrowserRouter>
    </ToastProvider>
  )
}

export default App
