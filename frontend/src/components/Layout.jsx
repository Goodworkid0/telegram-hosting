import { Outlet, Link, useLocation } from 'react-router-dom'
import { User, Settings, Wallet, Shield, Bell, UserCog, MessageSquare, Users, Megaphone, ExternalLink, FolderArchive } from 'lucide-react'
import { useAuthStore } from '../store/authStore'
import { useBrandingStore } from '../store/brandingStore'
import api from '../lib/api'
import { motion, AnimatePresence } from 'framer-motion'
import { useMemo, useState, useEffect, useCallback, useRef } from 'react'
import { useToast } from './Toast'
import useTelegramBackButton from '../lib/useTelegramBackButton'
import { useT } from '../lib/i18n'

export default function Layout() {
  const location = useLocation()
  useTelegramBackButton()
  const t = useT()
  const { user, token, isAdmin } = useAuthStore()
  // Backend sends roles uppercase ('ADMIN'); normalize for display/compare
  const role = String(user?.role || 'user').toLowerCase()
  const [showUserMenu, setShowUserMenu] = useState(false)
  const [unreadNotifs, setUnreadNotifs] = useState(0)
  const { appName, logoUrl, showLogo, announcementsUrl, officialGroupUrl, supportUsername, supportDisplayName } = useBrandingStore()
  const { addToast } = useToast()
  const prevUnreadRef = useRef(0)

  const refreshSignals = useCallback(async () => {
    if (!user || !token) return
    if (typeof document !== 'undefined' && document.hidden) return
    try {
      const unreadRes = await api.get('/api/notifications/unread-count')
      const newCount = unreadRes.data.count || 0
      // Show toast if new notifications appeared (but not on first load)
      if (newCount > prevUnreadRef.current && prevUnreadRef.current > 0) {
        const diff = newCount - prevUnreadRef.current
        addToast(
          diff === 1 ? t('common.new_notification_one') : t('common.new_notification_many', { n: diff }),
          { type: 'notification', title: t('common.new_notification_title') }
        )
      }
      prevUnreadRef.current = newCount
      setUnreadNotifs(newCount)
    } catch {
    }
  }, [user, token, addToast])

  useEffect(() => {
    refreshSignals()
    const interval = setInterval(refreshSignals, 30000)
    return () => clearInterval(interval)
  }, [refreshSignals])

  useEffect(() => {
    const onUnreadUpdate = (event) => {
      const count = event?.detail?.count
      if (typeof count === 'number') setUnreadNotifs(count)
    }
    window.addEventListener('notifications-unread-updated', onUnreadUpdate)
    return () => window.removeEventListener('notifications-unread-updated', onUnreadUpdate)
  }, [])

  useEffect(() => {
    if (!token) return
    const onFocus = () => refreshSignals()
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [token, refreshSignals])

  const navItems = useMemo(() => {
    const items = [
      { path: '/', icon: FolderArchive, label: t('nav.files') },
      { path: `/profile/${user?.id}`, icon: User, label: t('menu.profile') },
      { path: '/shop', icon: Wallet, label: t('menu.wallet') },
      { path: '/notifications', icon: Bell, label: t('nav.notifications'), badge: unreadNotifs },
    ]
    if (isAdmin()) {
      items.push({ path: '/admin', icon: Shield, label: t('nav.admin') })
    }
    return items
  }, [user, unreadNotifs, t])

  const isImpersonating = typeof window !== 'undefined' && !!sessionStorage.getItem('admin_token')

  const returnToAdmin = () => {
    const adminToken = sessionStorage.getItem('admin_token')
    if (adminToken) {
      localStorage.setItem('token', adminToken)
      sessionStorage.removeItem('admin_token')
      window.location.reload()
    }
  }

  return (
    <div className="min-h-screen bg-dark-950 pb-[calc(80px+env(safe-area-inset-bottom,0px))]">
      {isImpersonating && (
        <div className="bg-primary-500/10 border-b border-primary-500/20 sticky top-0 z-[60]">
          <div className="max-w-4xl mx-auto px-4 py-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <UserCog size={14} className="text-primary-400" />
              <span className="text-xs font-medium text-primary-300">
                {t('menu.viewing_as')} <span className="font-bold">@{user?.username || '?'}</span>
              </span>
            </div>
            <button
              onClick={returnToAdmin}
              className="text-[11px] font-semibold bg-primary-500/15 text-primary-400 px-3 py-1 rounded-lg hover:bg-primary-500/25 transition-all border border-primary-500/20"
            >
              {t('menu.back_to_admin')}
            </button>
          </div>
        </div>
      )}

      <header className={`sticky ${isImpersonating ? 'top-[36px]' : 'top-0'} z-50 glass`}>
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Link to="/" className="flex items-center gap-2">
              {showLogo && (logoUrl ? (
                <img src={logoUrl} alt={appName} className="w-8 h-8 rounded-lg object-cover" />
              ) : (
                <div className="w-8 h-8 bg-gradient-to-br from-primary-400 to-primary-600 rounded-lg flex items-center justify-center">
                  <span className="text-lg font-bold">{appName?.[0] || 'H'}</span>
                </div>
              ))}
              <span className="font-display font-bold text-lg gradient-text tracking-tight">{appName}</span>
            </Link>
          </div>

          <div className="flex items-center gap-1">
            <Link
              to="/shop"
              className="group flex items-center gap-1.5 bg-dark-800/80 px-3 py-1.5 rounded-lg hover:bg-dark-700 transition-colors"
            >
              <Wallet size={14} className="text-primary-400 group-hover:text-primary-300 transition-colors" />
              <span className="font-semibold text-sm group-hover:text-white transition-colors">
                ${user?.balance?.toFixed(2) || '0.00'}
              </span>
            </Link>

            <Link
              to="/notifications"
              className="group relative flex items-center justify-center w-8 h-8 rounded-lg hover:bg-dark-800/80 transition-colors"
            >
              <Bell size={18} className={unreadNotifs > 0 ? 'text-primary-400 animate-pulse' : 'text-dark-300 group-hover:text-white transition-colors'} />
              {unreadNotifs > 0 && (
                <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-[16px] bg-red-500 text-[9px] font-bold rounded-full flex items-center justify-center px-0.5">
                  {unreadNotifs > 99 ? '99+' : unreadNotifs}
                </span>
              )}
            </Link>

            <div className="relative">
              <button
                onClick={() => setShowUserMenu(!showUserMenu)}
                aria-expanded={showUserMenu}
                aria-haspopup="true"
                aria-label={t('menu.profile')}
                className="flex items-center justify-center w-8 h-8 rounded-lg hover:bg-dark-800/80 transition-colors"
              >
                <div className="w-7 h-7 rounded-full bg-gradient-to-br from-primary-400 to-accent-purple flex items-center justify-center overflow-hidden">
                  {user?.avatar_url ? (
                    <img src={user.avatar_url} alt="" className="w-full h-full object-cover" />
                  ) : (
                    <span className="text-xs font-bold">{user?.username?.[0]?.toUpperCase() || 'U'}</span>
                  )}
                </div>
              </button>

              <AnimatePresence>
                {showUserMenu && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setShowUserMenu(false)} />
                    <motion.div
                      initial={{ opacity: 0, y: -10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -10 }}
                      className="absolute right-0 top-full mt-2 w-48 bg-dark-800 border border-dark-700 rounded-xl shadow-xl z-50 overflow-hidden"
                    >
                      <div className="p-3 border-b border-dark-700">
                        <p className="font-medium text-sm">{user?.first_name || user?.username}</p>
                        <p className="text-xs text-dark-400">@{user?.username || 'guest'}</p>
                        {role !== 'user' && (
                          <span className={`inline-block text-[10px] mt-1 px-1.5 py-0.5 rounded ${
                            role === 'admin' ? 'bg-red-500/20 text-red-400' :
                            role === 'moderator' ? 'bg-blue-500/20 text-blue-400' : ''
                          }`}>
                            {role}
                          </span>
                        )}
                      </div>
                      <div className="p-1">
                        <Link to={`/profile/${user?.id}`} className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-dark-700 rounded-lg transition-colors" onClick={() => setShowUserMenu(false)}>
                          <User size={16} />
                          {t('menu.profile')}
                        </Link>
                        <Link to="/settings" className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-dark-700 rounded-lg transition-colors" onClick={() => setShowUserMenu(false)}>
                          <Settings size={16} />
                          {t('menu.settings')}
                        </Link>

                        {isImpersonating && (
                          <div className="border-t border-b border-primary-500/10 my-1 py-1">
                            <div className="flex items-center gap-2 px-3 py-1.5">
                              <UserCog size={14} className="text-primary-400" />
                              <span className="text-xs text-primary-300">{t('menu.viewing_as')} <span className="font-semibold">@{user?.username || '?'}</span></span>
                            </div>
                            <button
                              onClick={() => { setShowUserMenu(false); returnToAdmin() }}
                              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-primary-400 hover:bg-primary-500/10 rounded-lg transition-colors"
                            >
                              <Shield size={14} />
                              {t('menu.back_to_admin')}
                            </button>
                          </div>
                        )}

                        {isAdmin() && (
                          <Link to="/admin" className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-dark-700 rounded-lg transition-colors text-red-400" onClick={() => setShowUserMenu(false)}>
                            <Shield size={16} />
                            {t('menu.admin_dashboard')}
                          </Link>
                        )}
                        <Link to="/shop" className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-dark-700 rounded-lg transition-colors" onClick={() => setShowUserMenu(false)}>
                          <Wallet size={16} />
                          {t('menu.wallet')}
                        </Link>

                        {(announcementsUrl || officialGroupUrl || supportUsername) && (
                          <div className="border-t border-primary-500/10 mt-1 pt-1">
                            {supportUsername && (
                              <a href={`https://t.me/${supportUsername.replace(/^@/, '')}`} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-dark-700 rounded-lg transition-colors" onClick={() => setShowUserMenu(false)}>
                                <MessageSquare size={16} />
                                {supportDisplayName || t('menu.support')}
                                <ExternalLink size={11} className="text-dark-500 ml-auto" />
                              </a>
                            )}
                            {announcementsUrl && (
                              <a href={announcementsUrl} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-dark-700 rounded-lg transition-colors" onClick={() => setShowUserMenu(false)}>
                                <Megaphone size={16} />
                                {t('menu.announcements')}
                                <ExternalLink size={11} className="text-dark-500 ml-auto" />
                              </a>
                            )}
                            {officialGroupUrl && (
                              <a href={officialGroupUrl} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-dark-700 rounded-lg transition-colors" onClick={() => setShowUserMenu(false)}>
                                <Users size={16} />
                                {t('menu.official_group')}
                                <ExternalLink size={11} className="text-dark-500 ml-auto" />
                              </a>
                            )}
                          </div>
                        )}
                      </div>
                    </motion.div>
                  </>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-4">
        <main id="main-content" className="flex-1">
          <Outlet />
        </main>
      </main>

      <nav className="fixed bottom-0 left-0 right-0 bg-dark-950/90 backdrop-blur-xl border-t border-primary-500/10 pb-[env(safe-area-inset-bottom)]" aria-label={t('nav.files')}>
        <div className="max-w-4xl mx-auto px-2">
          <div className="flex justify-around py-1.5">
            {navItems.map(item => {
              const isActive = item.path === '/'
                ? (location.pathname === '/' || location.pathname === '/files')
                : (location.pathname === item.path || location.pathname.startsWith(item.path + '/'))
              const Icon = item.icon

              return (
                <Link
                  key={item.path}
                  to={item.path}
                  aria-current={isActive ? 'page' : undefined}
                  className={`relative flex flex-col items-center gap-0.5 px-3 py-1.5 rounded-lg transition-colors ${
                    isActive ? 'text-primary-400' : 'text-dark-400 hover:text-dark-200'
                  }`}
                >
                  {isActive && (
                    <motion.div
                      layoutId="nav-indicator"
                      className="absolute inset-0 bg-primary-500/10 rounded-lg border border-primary-500/20"
                    />
                  )}
                  <div className="relative">
                    <Icon size={18} />
                    {item.badge > 0 && (
                      <span className="absolute -top-1 -right-1 min-w-[14px] h-3.5 px-0.5 bg-primary-500 text-[9px] font-bold rounded-full flex items-center justify-center">
                        {item.badge > 99 ? '99+' : item.badge}
                      </span>
                    )}
                  </div>
                  <span className="text-[10px]">{item.label}</span>
                </Link>
              )
            })}
          </div>
        </div>
      </nav>
    </div>
  )
}
