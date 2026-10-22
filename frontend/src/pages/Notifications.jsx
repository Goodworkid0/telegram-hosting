import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell, CheckCheck, MessageSquare, ChevronRight, CheckCircle, AlertTriangle, ArrowUpCircle, Wallet, XCircle, Gift, Heart, AtSign, Star, Reply, Filter, Award, ShieldCheck, Trophy, VolumeX, Volume2, UserCheck, Crown, UserPlus } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuthStore } from '../store/authStore'
import api from '../lib/api'
import { timeAgo } from '../lib/utils'
import { PageHeading, Button, Tag, EmptyState, LoadingState, tabClass } from '../components/ui'
import { useT } from '../lib/i18n'

// labelKey values are i18n keys — translate with t() at render time.
const TYPE_META = {
  // Forum notifications
  thread_reply:        { icon: Reply,           color: 'text-blue-400',   bg: 'bg-blue-500/10',    labelKey: 'notif.cat_replies' },
  post_reply:          { icon: Reply,           color: 'text-blue-400',   bg: 'bg-blue-500/10',    labelKey: 'notif.cat_replies' },
  mention:             { icon: AtSign,          color: 'text-cyan-400',   bg: 'bg-cyan-500/10',    labelKey: 'notif.cat_mentions' },
  thread_like:         { icon: Heart,           color: 'text-pink-400',   bg: 'bg-pink-500/10',    labelKey: 'notif.cat_likes' },
  post_like:           { icon: Heart,           color: 'text-pink-400',   bg: 'bg-pink-500/10',    labelKey: 'notif.cat_likes' },
  reputation:          { icon: Star,            color: 'text-yellow-400', bg: 'bg-yellow-500/10',  labelKey: 'notif.cat_reputation' },
  new_follower:        { icon: Heart,           color: 'text-pink-400',   bg: 'bg-pink-500/10',    labelKey: 'notif.cat_followers' },
  dm_message:          { icon: MessageSquare,   color: 'text-blue-400',   bg: 'bg-blue-500/10',    labelKey: 'notif.cat_dm' },
  // Finance
  deposit_credited:    { icon: Wallet,          color: 'text-green-400',  bg: 'bg-green-500/10',   labelKey: 'notif.cat_deposits' },
  withdrawal_approved: { icon: Wallet,          color: 'text-green-400',  bg: 'bg-green-500/10',   labelKey: 'notif.cat_withdrawals' },
  withdrawal_rejected: { icon: XCircle,         color: 'text-red-400',    bg: 'bg-red-500/10',     labelKey: 'notif.cat_withdrawals' },
  balance_adjusted:    { icon: Wallet,          color: 'text-amber-400',  bg: 'bg-amber-500/10',   labelKey: 'notif.cat_balance' },
  giveaway_won:        { icon: Gift,            color: 'text-purple-400', bg: 'bg-purple-500/10',  labelKey: 'notif.cat_giveaways' },
  premium_purchase:    { icon: Crown,           color: 'text-amber-400',  bg: 'bg-amber-500/10',   labelKey: 'notif.cat_premium' },
  referral_bonus:      { icon: UserPlus,        color: 'text-teal-400',   bg: 'bg-teal-500/10',    labelKey: 'notif.cat_referral' },
  // Progress & achievements
  level_up:            { icon: ArrowUpCircle,   color: 'text-purple-400', bg: 'bg-purple-500/10',  labelKey: 'notif.cat_level_ups' },
  badge:               { icon: Award,           color: 'text-amber-400',  bg: 'bg-amber-500/10',   labelKey: 'notif.cat_badges' },
  leaderboard:         { icon: Trophy,          color: 'text-yellow-400', bg: 'bg-yellow-500/10',  labelKey: 'notif.cat_leaderboard' },
  // Moderation
  report_resolved:     { icon: CheckCircle,     color: 'text-green-400',  bg: 'bg-green-500/10',   labelKey: 'notif.cat_reports' },
  warning:             { icon: AlertTriangle,   color: 'text-yellow-400', bg: 'bg-yellow-500/10',  labelKey: 'notif.cat_warnings' },
  muted:               { icon: VolumeX,         color: 'text-red-400',    bg: 'bg-red-500/10',     labelKey: 'notif.cat_muted' },
  unmuted:             { icon: Volume2,         color: 'text-green-400',  bg: 'bg-green-500/10',   labelKey: 'notif.cat_unmuted' },
  unbanned:            { icon: UserCheck,       color: 'text-green-400',  bg: 'bg-green-500/10',   labelKey: 'notif.cat_unbanned' },
  // Escrow
  escrow:              { icon: ShieldCheck,      color: 'text-emerald-400', bg: 'bg-emerald-500/10', labelKey: 'notif.cat_escrow' },
  escrow_message:      { icon: MessageSquare,    color: 'text-blue-400',   bg: 'bg-blue-500/10',    labelKey: 'notif.cat_escrow' },
}

// Build unique filter categories (i18n keys) from TYPE_META. 'all' is a sentinel.
const FILTER_CATEGORIES = ['all', ...new Set(Object.values(TYPE_META).map(m => m.labelKey))]

export default function Notifications() {
  const { token } = useAuthStore()
  const navigate = useNavigate()
  const t = useT()
  const [notifications, setNotifications] = useState([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [activeFilter, setActiveFilter] = useState('all')
  const [showFilters, setShowFilters] = useState(false)

  const PER_PAGE = 30

  const loadNotifications = useCallback(async (pageNum = 1, append = false) => {
    if (!token) { setLoading(false); return }
    if (typeof document !== 'undefined' && document.hidden && pageNum === 1) return
    try {
      if (pageNum === 1) setLoading(true)
      else setLoadingMore(true)
      const { data: items } = await api.get('/api/notifications', {
        params: { limit: PER_PAGE, offset: (pageNum - 1) * PER_PAGE }
      })
      if (append) {
        setNotifications(prev => [...prev, ...items])
      } else {
        setNotifications(items)
      }
      setHasMore(items.length === PER_PAGE)
      if (pageNum === 1) {
        const count = items.filter(n => !n.is_read).length
        window.dispatchEvent(new CustomEvent('notifications-unread-updated', { detail: { count } }))
      }
    } catch (e) {
      console.error('Failed to load notifications', e)
    } finally {
      setLoading(false)
      setLoadingMore(false)
    }
  }, [token])

  useEffect(() => {
    if (!token) return
    loadNotifications(1)
    const interval = setInterval(() => loadNotifications(1), 60000)
    return () => clearInterval(interval)
  }, [token, loadNotifications])

  // Auto-mark all as read when page opens
  useEffect(() => {
    if (!token) return
    api.post('/api/notifications/mark-read').then(() => {
      window.dispatchEvent(new CustomEvent('notifications-unread-updated', { detail: { count: 0 } }))
    }).catch(() => {})
  }, [token])

  const loadMore = () => {
    const next = page + 1
    setPage(next)
    loadNotifications(next, true)
  }

  const markAllRead = async () => {
    try {
      await api.post('/api/notifications/mark-read')
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })))
      window.dispatchEvent(new CustomEvent('notifications-unread-updated', { detail: { count: 0 } }))
    } catch (e) {
      console.error(e)
    }
  }

  const handleClick = async (notif) => {
    if (!notif.is_read) {
      try {
        await api.post(`/api/notifications/${notif.id}/read`)
        setNotifications(prev => {
          const next = prev.map(n => n.id === notif.id ? { ...n, is_read: true } : n)
          const count = next.filter(n => !n.is_read).length
          window.dispatchEvent(new CustomEvent('notifications-unread-updated', { detail: { count } }))
          return next
        })
      } catch (e) { /* ignore */ }
    }
    if (notif.link) navigate(notif.link)
  }

  // Filter notifications by category
  const filteredNotifs = activeFilter === 'all'
    ? notifications
    : notifications.filter(n => {
        const meta = TYPE_META[n.type]
        return meta && meta.labelKey === activeFilter
      })

  const unreadCount = notifications.filter(n => !n.is_read).length

  return (
    <div className="space-y-4">
      {/* Header */}
      <PageHeading
        icon={Bell}
        title={t('notif.title')}
        subtitle={unreadCount > 0 ? t('notif.unread_count', { n: unreadCount }) : t('notif.all_caught_up')}
        right={
          <div className="flex items-center gap-2">
            <Button
              variant={activeFilter !== 'all' ? 'secondary' : 'ghost'}
              size="sm"
              icon={Filter}
              onClick={() => setShowFilters(!showFilters)}
            >
              {activeFilter !== 'all' ? t(activeFilter) : t('notif.filter')}
            </Button>
            {unreadCount > 0 && (
              <Button variant="ghost" size="sm" icon={CheckCheck} onClick={markAllRead}>
                {t('notif.mark_all')}
              </Button>
            )}
          </div>
        }
      />

      {/* Filter Bar */}
      <AnimatePresence>
        {showFilters && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div className="flex flex-wrap gap-1.5 pb-2">
              {FILTER_CATEGORIES.map(cat => (
                <button
                  key={cat}
                  onClick={() => setActiveFilter(cat)}
                  className={tabClass(activeFilter === cat)}
                >
                  {cat === 'all' ? t('notif.filter_all') : t(cat)}
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* List */}
      {loading ? (
        <LoadingState label={t('notif.loading')} />
      ) : filteredNotifs.length === 0 ? (
        <EmptyState icon={Bell}>
          {activeFilter !== 'all' ? t('notif.empty_filtered', { filter: t(activeFilter).toLowerCase() }) : t('notif.empty_all')}
        </EmptyState>
      ) : (
        <div className="space-y-2">
          <AnimatePresence>
            {filteredNotifs.map((notif, idx) => {
              const meta = TYPE_META[notif.type] || { icon: Bell, color: 'text-dark-400', bg: 'bg-dark-700', labelKey: 'notif.cat_system' }
              const Icon = meta.icon
              return (
                <motion.button
                  key={notif.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(idx * 0.03, 0.3) }}
                  onClick={() => handleClick(notif)}
                  className={`w-full text-left rounded-xl border p-3 flex items-start gap-3 transition-colors ${
                    !notif.is_read
                      ? 'border-l-2 border-l-primary-500 border-y-primary-500/10 border-r-primary-500/10 bg-primary-500/5 hover:bg-primary-500/10'
                      : 'border-primary-500/10 bg-dark-900/40 hover:bg-dark-800/60'
                  }`}
                >
                  <div className={`w-10 h-10 rounded-xl ${meta.bg} flex items-center justify-center flex-shrink-0`}>
                    <Icon size={18} className={meta.color} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className={`text-sm font-medium leading-tight ${!notif.is_read ? 'text-white' : 'text-dark-300'}`}>
                        {notif.title}
                      </p>
                      {meta.labelKey && <Tag tone="cyan">{t(meta.labelKey)}</Tag>}
                    </div>
                    {notif.body && (
                      <p className="text-xs text-dark-400 mt-0.5 line-clamp-2">{notif.body}</p>
                    )}
                    <p className="text-[10px] text-dark-500 mt-1">{timeAgo(notif.created_at)}</p>
                  </div>
                  <ChevronRight size={16} className="text-dark-600 flex-shrink-0 mt-1" />
                </motion.button>
              )
            })}
          </AnimatePresence>

          {/* Load More */}
          {hasMore && activeFilter === 'all' && (
            <Button
              variant="ghost"
              onClick={loadMore}
              disabled={loadingMore}
              className="w-full"
            >
              {loadingMore ? t('notif.loading_btn') : t('notif.load_older')}
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
