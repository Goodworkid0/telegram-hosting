import { useState, useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import api from '../lib/api'
import { useAuthStore } from '../store/authStore'
import { useToast } from '../components/Toast'
import { timeAgo, formatDate, displayName, realName, telegramHandle } from '../lib/utils'
import { Card, Button, RoleBadge, StatTile, EmptyState, Modal, tabClass, FormInput } from '../components/ui'
import { useT } from '../lib/i18n'
import { roleStyle } from '../components/admin/ui'
import Spinner from '../components/Spinner'
import { Calendar, ThumbsUp, ThumbsDown, Users, Clock, Plus, Minus, Star, Settings, Pencil, FileText, Download, ShoppingCart } from 'lucide-react'
import UserListModal from '../components/UserListModal'

function humanSize(bytes) {
  if (!bytes && bytes !== 0) return ''
  const u = ['B', 'KB', 'MB', 'GB']
  let n = bytes, i = 0
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++ }
  return `${n.toFixed(n < 10 && i > 0 ? 1 : 0)} ${u[i]}`
}

export default function Profile() {
  const { id } = useParams()
  const { user: currentUser, setUser } = useAuthStore()
  const { showToast } = useToast()
  const t = useT()

  const [profile, setProfile] = useState(null)
  const [uploads, setUploads] = useState(null)         // { items, total }
  const [uploadsPage, setUploadsPage] = useState(1)
  const [mine, setMine] = useState(null)               // own uploads incl. pending
  const [minePage, setMinePage] = useState(1)
  const [contentLoadingMore, setContentLoadingMore] = useState(false)
  const [repHistory, setRepHistory] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('uploads')
  const [following, setFollowing] = useState(false)
  const [followTab, setFollowTab] = useState(null) // null | 'followers' | 'following'
  const [showRepModal, setShowRepModal] = useState(false)
  const [repPositive, setRepPositive] = useState(true)
  const [repComment, setRepComment] = useState('')
  const [repSubmitting, setRepSubmitting] = useState(false)
  const [showEdit, setShowEdit] = useState(false)
  const [editForm, setEditForm] = useState({ profile_bio: '' })
  const [editTheme, setEditTheme] = useState({ name_color: '', avatar_border: '', avatar_glow: false })
  const [savingEdit, setSavingEdit] = useState(false)
  const [priceEdit, setPriceEdit] = useState({})       // fileId -> input value
  const [priceSaving, setPriceSaving] = useState(null)

  const openEdit = () => {
    setEditForm({ profile_bio: currentUser?.profile_bio || '' })
    let th = {}
    try { th = currentUser?.profile_theme ? JSON.parse(currentUser.profile_theme) : {} } catch { th = {} }
    setEditTheme({ name_color: th.name_color || '', avatar_border: th.avatar_border || '', avatar_glow: !!th.avatar_glow })
    setShowEdit(true)
  }

  const handleSaveEdit = async () => {
    setSavingEdit(true)
    try {
      const payload = { profile_bio: editForm.profile_bio }
      if (currentUser?.is_premium) {
        payload.profile_theme = JSON.stringify({
          name_color: editTheme.name_color || undefined,
          avatar_border: editTheme.avatar_border || undefined,
          avatar_glow: !!editTheme.avatar_glow,
        })
      }
      const { data } = await api.put('/api/auth/profile', payload)
      setUser(data)
      setShowEdit(false)
      loadProfile()
      showToast(t('profile.updated'), 'success')
    } catch (err) {
      showToast(err.response?.data?.detail || t('profile.update_failed'), 'error')
    } finally {
      setSavingEdit(false)
    }
  }

  useEffect(() => {
    loadProfile()
    setTab('uploads')
    setMine(null)
    setRepHistory(null)
  }, [id])

  const loadProfile = async () => {
    try {
      setLoading(true)
      const [profileRes, uploadsRes] = await Promise.all([
        api.get(`/api/users/${id}`),
        api.get(`/api/users/${id}/files`, { params: { page: 1, per_page: 20 } }),
      ])
      setProfile(profileRes.data)
      setUploads(uploadsRes.data)
      setUploadsPage(1)
      setFollowing(profileRes.data.is_following || false)
    } catch (err) {
      if (import.meta.env.DEV) console.error('Failed to load profile:', err)
    } finally {
      setLoading(false)
    }
  }

  const loadMoreUploads = async () => {
    setContentLoadingMore(true)
    try {
      const next = uploadsPage + 1
      const { data } = await api.get(`/api/users/${id}/files`, { params: { page: next, per_page: 20 } })
      setUploads(prev => ({ ...data, items: [...(prev?.items || []), ...(data.items || [])] }))
      setUploadsPage(next)
    } catch { /* keep current list */ } finally { setContentLoadingMore(false) }
  }

  const loadMine = async (page = 1, append = false) => {
    try {
      const { data } = await api.get('/api/files/mine', { params: { page, per_page: 20 } })
      setMine(prev => append ? { ...data, items: [...(prev?.items || []), ...(data.items || [])] } : data)
      setMinePage(page)
    } catch { setMine({ items: [], total: 0, total_earnings: 0 }) }
  }

  const handleFollow = async () => {
    try {
      if (following) {
        await api.delete(`/api/users/${id}/follow`)
        setFollowing(false)
        setProfile(p => ({ ...p, follower_count: (p.follower_count || 1) - 1 }))
      } else {
        await api.post(`/api/users/${id}/follow`)
        setFollowing(true)
        setProfile(p => ({ ...p, follower_count: (p.follower_count || 0) + 1 }))
      }
    } catch (err) {
      showToast(t('profile.action_failed'), 'error')
    }
  }

  const loadRepHistory = async () => {
    try {
      const res = await api.get(`/api/reputation/users/${id}`)
      setRepHistory(res.data)
    } catch (err) {
      if (import.meta.env.DEV) console.error('Failed to load reputation:', err)
    }
  }

  const handleGiveRep = async () => {
    if (!repComment.trim()) {
      showToast(t('profile.comment_required'), 'error')
      return
    }
    try {
      setRepSubmitting(true)
      await api.post(`/api/reputation/users/${id}`, {
        is_positive: repPositive,
        comment: repComment.trim()
      })
      showToast(repPositive ? t('profile.rep_given_pos') : t('profile.rep_given_neg'), 'success')
      setShowRepModal(false)
      setRepComment('')
      loadProfile()
      if (tab === 'reputation') loadRepHistory()
    } catch (err) {
      const msg = err.response?.data?.detail || t('profile.rep_failed')
      showToast(msg, 'error')
    } finally {
      setRepSubmitting(false)
    }
  }

  const savePrice = async (file) => {
    const raw = (priceEdit[file.id] ?? '').trim()
    const price = raw === '' ? null : Number(raw)
    if (price !== null && (!Number.isFinite(price) || price < 0)) {
      showToast(t('files.price_ph'), 'error')
      return
    }
    setPriceSaving(file.id)
    try {
      const { data } = await api.patch(`/api/files/${file.id}/price`, { price })
      showToast(t('files.price_saved'), 'success')
      setMine(prev => prev ? {
        ...prev,
        items: prev.items.map(f => f.id === file.id ? { ...f, price: data.price } : f),
      } : prev)
      setPriceEdit(pe => ({ ...pe, [file.id]: data.price != null ? String(data.price) : '' }))
    } catch (err) {
      showToast(err.response?.data?.detail || t('profile.failed'), 'error')
    } finally {
      setPriceSaving(null)
    }
  }

  if (loading) {
    return <Spinner className="min-h-[60vh]" />
  }

  if (!profile) {
    return (
      <Card className="p-8 text-center">
        <EmptyState>{t('profile.user_not_found')}</EmptyState>
      </Card>
    )
  }

  const isOwnProfile = currentUser?.id === profile.id
  const reputation = (profile.rep_positive || 0) - (profile.rep_negative || 0)

  // Subscriber name color / avatar border to render on the header.
  const profileTheme = (() => {
    try {
      return profile.profile_theme
        ? (typeof profile.profile_theme === 'string' ? JSON.parse(profile.profile_theme) : profile.profile_theme)
        : null
    } catch { return null }
  })()
  const themeBorder = profileTheme?.avatar_border || null
  const avatarThemeStyle = themeBorder
    ? { boxShadow: [`0 0 0 2px ${themeBorder}`, profileTheme.avatar_glow ? `0 0 16px ${themeBorder}` : ''].filter(Boolean).join(', ') }
    : undefined

  const fileRow = (f) => (
    <Card key={f.id} className="flex items-center gap-3 !p-3">
      <FileText size={16} className="text-primary-400 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-white truncate" title={f.file_name}>{f.file_name}</p>
        <p className="text-[11px] text-dark-400 font-mono flex flex-wrap gap-x-2">
          <span>{timeAgo(f.created_at)}</span>
          {f.file_size != null && <span>{humanSize(f.file_size)}</span>}
          {f.download_count > 0 && <span className="inline-flex items-center gap-0.5"><Download size={9} /> {f.download_count}</span>}
        </p>
      </div>
      {f.price > 0 && (
        <span className="text-[10px] font-semibold text-amber-300 bg-amber-500/10 border border-amber-500/20 px-1.5 py-0.5 rounded flex-shrink-0">
          ${Number(f.price).toFixed(2)}
        </span>
      )}
    </Card>
  )

  const statusTag = (f) => {
    if (f.status === 'PENDING') return <span className="text-[10px] font-medium text-yellow-300 bg-yellow-500/10 border border-yellow-500/20 px-1.5 py-0.5 rounded">{t('files.status_pending')}</span>
    if (f.status === 'REJECTED') return <span className="text-[10px] font-medium text-red-300 bg-red-500/10 border border-red-500/20 px-1.5 py-0.5 rounded" title={f.reject_reason || ''}>{t('files.status_rejected')}</span>
    return null
  }

  return (
    <div className="space-y-4">
      {/* Profile Banner */}
      {profile.profile_banner_url && (
        <div className="relative h-32 rounded-xl overflow-hidden border border-primary-500/15">
          <img src={profile.profile_banner_url} alt="" className="w-full h-full object-cover" />
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-dark-950/60 to-transparent" />
        </div>
      )}

      {/* Profile Header */}
      <Card className="overflow-visible p-6">
          <div className="flex items-start gap-4">
            {/* Avatar — overlaps banner */}
            <div
              className={`w-20 h-20 rounded-xl bg-dark-800 flex items-center justify-center overflow-hidden flex-shrink-0 ring-4 ring-primary-500/20 border border-dark-950 avatar-glow ${profile.profile_banner_url ? '-mt-12' : ''}`}
              style={avatarThemeStyle}
            >
              {profile.avatar_url ? (
                <img src={profile.avatar_url} alt="" className="w-full h-full object-cover" />
              ) : (
                <span className="text-2xl font-bold text-primary-400">
                  {realName(profile)[0] || '?'}
                </span>
              )}
            </div>

            {/* Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h1
                  className={`font-display text-xl font-bold ${profileTheme?.name_color ? '' : roleStyle(profile.role).text}`}
                  style={profileTheme?.name_color ? { color: profileTheme.name_color } : undefined}
                >
                  {profile.first_name || profile.username || t('profile.user_fallback')}
                </h1>
                {telegramHandle(profile) && (
                  <span className="text-sm font-mono text-primary-400/70">{telegramHandle(profile)}</span>
                )}
                {profile.is_premium && (
                  <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-amber-300 bg-amber-500/10 border border-amber-500/20 px-1.5 py-0.5 rounded">
                    <Star size={10} /> {t('shop.sub_active_short')}
                  </span>
                )}
                {profile.role && profile.role !== 'user' && (
                  <RoleBadge role={profile.role} />
                )}
              </div>

              {profile.profile_bio && (
                <p className="text-dark-300 mt-2 text-sm">{profile.profile_bio}</p>
              )}

              {/* Online Status */}
              <div className="flex items-center gap-2 mt-2 text-xs text-dark-400 font-mono">
                <Clock size={12} />
                <span>{t('profile.last_seen', { time: timeAgo(profile.last_seen_at || profile.created_at) })}</span>
                <span>•</span>
                <Calendar size={12} />
                <span>{t('profile.joined', { date: formatDate(profile.created_at) })}</span>
              </div>
            </div>
          </div>

          {/* Stats Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 pt-4 border-t border-primary-500/10">
            <StatTile label={t('profile.stat_uploads')} value={profile.upload_count || 0} />
            <StatTile label={t('profile.stat_downloads')} value={profile.download_count || 0} accent="cyan" />
            <StatTile
              label={t('profile.stat_reputation')}
              value={`${reputation > 0 ? '+' : ''}${reputation}`}
              accent={reputation > 0 ? 'green' : reputation < 0 ? 'red' : 'default'}
            />
            <StatTile label={t('profile.stat_followers')} value={profile.follower_count || 0} onClick={() => setFollowTab('followers')} />
          </div>

          {/* Actions */}
          {!isOwnProfile && currentUser && (
            <div className="flex gap-3 mt-4 pt-4 border-t border-primary-500/10">
              <Button
                variant={following ? 'primary' : 'secondary'}
                icon={Users}
                onClick={handleFollow}
                className="flex-1"
              >
                {following ? t('profile.following') : t('profile.follow')}
              </Button>
              <Button
                variant="neon"
                icon={Star}
                onClick={() => setShowRepModal(true)}
                title={t('profile.give_rep_title')}
              >
                {t('profile.rep')}
              </Button>
            </div>
          )}

          {isOwnProfile && (
            <div className="mt-4 pt-4 border-t border-primary-500/10 flex items-center gap-3 flex-wrap">
              <Button variant="primary" size="sm" icon={Pencil} onClick={openEdit}>
                {t('profile.edit_profile')}
              </Button>
              <Link
                to="/settings"
                className="inline-flex items-center gap-2 text-sm text-primary-400 hover:underline font-mono"
              >
                <Settings size={16} />
                {t('profile.more_settings')}
              </Link>
            </div>
          )}
      </Card>

      {/* Tabs — sticky */}
      <div className="sticky top-16 z-20 -mx-1 px-1 py-1 bg-dark-950/80 backdrop-blur-sm rounded-xl">
        <div className="flex gap-1 bg-dark-900/80 rounded-xl p-1 border border-primary-500/15">
          <button onClick={() => setTab('uploads')} className={`flex-1 ${tabClass(tab === 'uploads')}`}>
            {t('profile.tab_uploads', { n: uploads?.total ?? 0 })}
          </button>
          {isOwnProfile && (
            <button
              onClick={() => { setTab('mine'); if (!mine) loadMine() }}
              className={`flex-1 ${tabClass(tab === 'mine')}`}
            >
              {t('files.mine_title')}
            </button>
          )}
          <button
            onClick={() => { setTab('reputation'); if (!repHistory) loadRepHistory() }}
            className={`flex-1 ${tabClass(tab === 'reputation')}`}
          >
            {t('profile.tab_reputation')}
          </button>
        </div>
      </div>

      {/* Uploads (public, approved) */}
      {tab === 'uploads' && (
        <div className="space-y-2">
          {(!uploads || uploads.items.length === 0) ? (
            <Card><EmptyState icon={FileText}>{t('profile.no_uploads')}</EmptyState></Card>
          ) : (
            <>
              {uploads.items.map(fileRow)}
              {uploads.items.length < uploads.total && (
                <Button variant="secondary" className="w-full" disabled={contentLoadingMore} onClick={loadMoreUploads}>
                  {contentLoadingMore ? '…' : t('common.load_more')}
                </Button>
              )}
            </>
          )}
          {isOwnProfile && (
            <p className="text-[11px] text-dark-500 text-center">{t('files.upload_hint')}</p>
          )}
        </div>
      )}

      {/* My Files (own profile: all statuses + price editing + earnings) */}
      {tab === 'mine' && isOwnProfile && (
        <div className="space-y-2">
          {mine === null ? (
            <Spinner size="sm" className="py-8" />
          ) : (
            <>
              {mine.total_earnings > 0 && (
                <Card className="!p-3 !bg-amber-500/5 !border-amber-500/20 flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-amber-500/20 flex items-center justify-center flex-shrink-0">
                    <ShoppingCart size={17} className="text-amber-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs text-dark-400">{t('files.earned')}</div>
                    <div className="text-sm font-bold text-amber-400 font-mono">${Number(mine.total_earnings).toFixed(2)}</div>
                  </div>
                </Card>
              )}
              {mine.items.length === 0 ? (
                <Card>
                  <EmptyState icon={FileText}>{t('profile.no_uploads')}</EmptyState>
                  <p className="text-dark-500 text-sm text-center">{t('files.upload_hint')}</p>
                </Card>
              ) : (
                mine.items.map(f => (
                  <Card key={f.id} className="!p-3 space-y-2">
                    <div className="flex items-center gap-3">
                      <FileText size={16} className="text-primary-400 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-white truncate" title={f.file_name}>{f.file_name}</p>
                        <p className="text-[11px] text-dark-400 font-mono flex flex-wrap gap-x-2">
                          <span>{timeAgo(f.created_at)}</span>
                          {f.file_size != null && <span>{humanSize(f.file_size)}</span>}
                          {f.download_count > 0 && <span className="inline-flex items-center gap-0.5"><Download size={9} /> {f.download_count}</span>}
                          {f.purchase_count > 0 && <span>{f.purchase_count} {t('files.sales')}</span>}
                        </p>
                      </div>
                      {statusTag(f)}
                    </div>
                    {f.status === 'REJECTED' && f.reject_reason && (
                      <p className="text-[11px] text-red-300/80">{f.reject_reason}</p>
                    )}
                    <div className="flex items-center gap-2">
                      <FormInput
                        type="number"
                        min="0"
                        step="0.01"
                        placeholder={t('files.price_ph')}
                        value={priceEdit[f.id] ?? (f.price != null ? String(f.price) : '')}
                        onChange={e => setPriceEdit(pe => ({ ...pe, [f.id]: e.target.value }))}
                        className="flex-1"
                      />
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={priceSaving === f.id}
                        onClick={() => savePrice(f)}
                      >
                        {priceSaving === f.id ? '…' : t('files.set_price')}
                      </Button>
                    </div>
                  </Card>
                ))
              )}
              {mine.items.length < mine.total && (
                <Button variant="secondary" className="w-full" onClick={() => loadMine(minePage + 1, true)}>
                  {t('common.load_more')}
                </Button>
              )}
            </>
          )}
        </div>
      )}

      {tab === 'reputation' && (
        <div className="space-y-2">
          {repHistory ? (
            <>
              {/* Summary */}
              <Card className="flex items-center justify-center gap-6">
                <div className="flex items-center gap-2 text-neon-400">
                  <ThumbsUp size={16} /> <span className="font-bold text-lg font-mono">+{repHistory.total_positive || 0}</span>
                </div>
                <div className="flex items-center gap-2 text-red-400">
                  <ThumbsDown size={16} /> <span className="font-bold text-lg font-mono">-{repHistory.total_negative || 0}</span>
                </div>
              </Card>

              {/* Entries */}
              {(!repHistory.entries || repHistory.entries.length === 0) ? (
                <Card><EmptyState icon={Star}>{t('profile.no_reputation')}</EmptyState></Card>
              ) : (
                repHistory.entries.map(entry => (
                  <Card key={entry.id} className="flex items-start gap-3">
                    <div className={`mt-0.5 w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                      entry.is_positive ? 'bg-neon-500/20' : 'bg-red-500/20'
                    }`}>
                      {entry.is_positive ? <Plus size={14} className="text-neon-400" /> : <Minus size={14} className="text-red-400" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 text-sm">
                        <Link
                          to={`/profile/${entry.from_user?.id}`}
                          className="font-semibold text-white hover:text-primary-400"
                        >
                          {entry.from_user ? displayName(entry.from_user) : t('profile.unknown')}
                        </Link>
                        <span className="text-dark-400 text-xs font-mono">{timeAgo(entry.created_at)}</span>
                      </div>
                      {entry.comment && (
                        <p className="text-dark-300 text-sm mt-1">{entry.comment}</p>
                      )}
                    </div>
                  </Card>
                ))
              )}
            </>
          ) : (
            <Spinner size="sm" className="py-8" />
          )}
        </div>
      )}

      {/* Followers / Following list */}
      <UserListModal
        open={!!followTab}
        onClose={() => setFollowTab(null)}
        url={followTab ? `/api/users/${id}/${followTab}` : null}
        title={
          <div className="flex gap-1.5 normal-case">
            {['followers', 'following'].map((ft) => (
              <button
                key={ft}
                onClick={() => setFollowTab(ft)}
                className={`rounded px-2.5 py-1 text-xs font-semibold capitalize transition-colors ${
                  followTab === ft
                    ? 'bg-primary-500/20 text-primary-200 border border-primary-500/40'
                    : 'text-dark-400 border border-transparent hover:text-dark-200'
                }`}
              >
                {ft === 'followers' ? t('profile.followers_tab') : t('profile.following_tab')} {ft === 'followers' ? (profile.follower_count || 0) : (profile.following_count || 0)}
              </button>
            ))}
          </div>
        }
      />

      {/* Rep Modal */}
      <Modal open={showRepModal} onClose={() => setShowRepModal(false)} title={t('profile.give_reputation')} maxWidth="max-w-md">
        <div className="space-y-4">
          <div className="flex gap-2">
            <button
              onClick={() => setRepPositive(true)}
              className={`flex-1 py-3 rounded-xl font-semibold flex items-center justify-center gap-2 transition-colors ${
                repPositive ? 'bg-neon-500/20 text-neon-400 ring-1 ring-neon-500/50' : 'bg-dark-800 text-dark-400'
              }`}
            >
              <ThumbsUp size={16} /> {t('profile.rep_plus')}
            </button>
            <button
              onClick={() => setRepPositive(false)}
              className={`flex-1 py-3 rounded-xl font-semibold flex items-center justify-center gap-2 transition-colors ${
                !repPositive ? 'bg-red-500/20 text-red-400 ring-1 ring-red-500/50' : 'bg-dark-800 text-dark-400'
              }`}
            >
              <ThumbsDown size={16} /> {t('profile.rep_minus')}
            </button>
          </div>

          <textarea
            value={repComment}
            onChange={e => setRepComment(e.target.value)}
            placeholder={t('profile.rep_comment_placeholder')}
            rows={3}
            className="w-full bg-dark-950/60 border border-primary-500/15 rounded-lg px-4 py-3 text-sm text-white font-mono placeholder:text-dark-500 focus:outline-none focus:border-primary-500/50 resize-none"
          />

          <Button
            variant="primary"
            onClick={handleGiveRep}
            disabled={repSubmitting || !repComment.trim()}
            className="w-full"
          >
            {repSubmitting ? t('profile.submitting') : t('profile.give_reputation_btn')}
          </Button>
        </div>
      </Modal>

      {/* Edit own profile (bio + subscriber appearance) */}
      <Modal open={showEdit} onClose={() => setShowEdit(false)} title={t('profile.edit_title')} maxWidth="max-w-md">
        <div className="space-y-4">
          <div>
            <label className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-primary-400/70">{t('profile.bio')}</label>
            <textarea
              value={editForm.profile_bio}
              onChange={e => setEditForm(f => ({ ...f, profile_bio: e.target.value }))}
              rows={3} maxLength={2000}
              placeholder={t('profile.bio_placeholder')}
              className="w-full bg-dark-950/60 border border-primary-500/15 rounded-lg px-4 py-3 text-sm text-white placeholder:text-dark-500 focus:outline-none focus:border-primary-500/50 resize-none"
            />
          </div>

          {currentUser?.is_premium ? (
            <div className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Star size={14} className="text-amber-400" />
                <h3 className="font-semibold text-amber-200 text-sm">{t('profile.premium_appearance')}</h3>
              </div>
              <div>
                <label className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-primary-400/70">{t('profile.name_color')}</label>
                <div className="flex items-center gap-2">
                  <input type="color" value={editTheme.name_color || '#ffffff'} onChange={e => setEditTheme(t => ({ ...t, name_color: e.target.value }))} className="w-10 h-10 rounded-lg border border-dark-700 cursor-pointer bg-transparent" />
                  <input type="text" value={editTheme.name_color} onChange={e => setEditTheme(t => ({ ...t, name_color: e.target.value }))} placeholder={t('profile.color_placeholder_default')} className="flex-1 bg-dark-950/60 border border-primary-500/15 rounded-lg px-3 py-2 text-sm text-white" />
                </div>
              </div>
              <div>
                <label className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-primary-400/70">{t('profile.avatar_border')}</label>
                <div className="flex items-center gap-2">
                  <input type="color" value={editTheme.avatar_border || '#00c8e6'} onChange={e => setEditTheme(t => ({ ...t, avatar_border: e.target.value }))} className="w-10 h-10 rounded-lg border border-dark-700 cursor-pointer bg-transparent" />
                  <input type="text" value={editTheme.avatar_border} onChange={e => setEditTheme(t => ({ ...t, avatar_border: e.target.value }))} placeholder={t('profile.color_placeholder_none')} className="flex-1 bg-dark-950/60 border border-primary-500/15 rounded-lg px-3 py-2 text-sm text-white" />
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm text-dark-200 cursor-pointer">
                <input type="checkbox" checked={editTheme.avatar_glow} onChange={e => setEditTheme(t => ({ ...t, avatar_glow: e.target.checked }))} />
                {t('profile.avatar_glow')}
              </label>
              <div className="flex items-center gap-3 pt-1">
                <div className="w-12 h-12 rounded-xl bg-dark-700 flex items-center justify-center font-bold"
                  style={editTheme.avatar_border ? { boxShadow: [`0 0 0 2px ${editTheme.avatar_border}`, editTheme.avatar_glow ? `0 0 14px ${editTheme.avatar_border}` : ''].filter(Boolean).join(', ') } : undefined}>
                  <span className={editTheme.name_color ? '' : roleStyle(currentUser?.role).text} style={editTheme.name_color ? { color: editTheme.name_color } : undefined}>{(currentUser?.username || 'U')[0]?.toUpperCase()}</span>
                </div>
                <span className={`font-semibold ${editTheme.name_color ? '' : roleStyle(currentUser?.role).text}`} style={editTheme.name_color ? { color: editTheme.name_color } : undefined}>{currentUser?.username || 'username'}</span>
              </div>
            </div>
          ) : (
            <Link to="/shop" onClick={() => setShowEdit(false)} className="block text-xs text-amber-300/90 hover:underline">
              {t('profile.get_premium_link')}
            </Link>
          )}

          <div className="flex gap-2 pt-1">
            <Button variant="ghost" className="flex-1" onClick={() => setShowEdit(false)}>{t('common.cancel')}</Button>
            <Button variant="primary" className="flex-1" onClick={handleSaveEdit} disabled={savingEdit}>
              {savingEdit ? t('common.saving') : t('common.save')}
            </Button>
          </div>
          <p className="text-[10px] text-dark-500 text-center">
            {t('profile.edit_footer')} <Link to="/settings" className="text-primary-400 hover:underline" onClick={() => setShowEdit(false)}>{t('profile.edit_footer_settings')}</Link>.
          </p>
        </div>
      </Modal>
    </div>
  )
}
