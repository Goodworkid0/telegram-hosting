import { useState, useEffect } from 'react'
import api from '../../lib/api'
import { t } from '../../lib/i18n'
import { parseDate } from '../../lib/utils'
import { useAuthStore } from '../../store/authStore'
import { Card, Button, FormInput, FormSelect, StatTile, EmptyState, LoadingState, Modal } from '../../components/admin/ui'

// Safely turn an axios error into a display string. FastAPI 422 responses put an
// ARRAY of {loc,msg} objects in `detail`; passing that array to a toast renders
// objects as React children and crashes the page. Always coerce to a string.
function errMsg(err, fallback = 'Failed') {
  const d = err?.response?.data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) return d.map(e => e?.msg).filter(Boolean).join(', ') || fallback
  if (d && typeof d === 'object') return d.msg || fallback
  return fallback
}

const MUTE_PRESETS = [
  { label: '1 hour', minutes: 60 },
  { label: '6 hours', minutes: 360 },
  { label: '1 day', minutes: 1440 },
  { label: '7 days', minutes: 10080 },
  { label: 'Permanent', minutes: null },
]

export default function AdminUsers({ showToast, showConfirm, showPrompt }) {
  const { isAdmin } = useAuthStore()
  const [users, setUsers] = useState([])
  const [usersTotal, setUsersTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loadingMore, setLoadingMore] = useState(false)
  const PER_PAGE = 50
  const [stats, setStats] = useState(null)
  const [userSearch, setUserSearch] = useState('')
  const [userFilterRole, setUserFilterRole] = useState('all')
  const [showCreateUser, setShowCreateUser] = useState(false)
  const [newUser, setNewUser] = useState({ telegram_id: '', username: '', first_name: '', role: 'USER' })
  const [expandedUser, setExpandedUser] = useState(null)
  const [expandedUserData, setExpandedUserData] = useState(null)
  const [allBadges, setAllBadges] = useState([])
  const [loading, setLoading] = useState(true)
  const [muteUserId, setMuteUserId] = useState(null)
  const [muteReason, setMuteReason] = useState('')

  const loadData = async (pageVal = 1, append = false) => {
    if (append) setLoadingMore(true)
    else setLoading(true)
    try {
      const reqs = [api.get('/api/admin/users', { params: { page: pageVal, per_page: PER_PAGE } })]
      if (!append) reqs.push(api.get('/api/admin/stats'))
      const [usersRes, statsRes] = await Promise.all(reqs)
      if (statsRes) setStats(statsRes.data)
      // Endpoint is paginated ({items, total, page, per_page}); tolerate a bare array too.
      const list = Array.isArray(usersRes.data) ? usersRes.data : usersRes.data.items || []
      setUsersTotal(Array.isArray(usersRes.data) ? usersRes.data.length : usersRes.data.total || 0)
      setUsers(prev => append ? [...prev, ...list] : list)
      setPage(pageVal)
    } catch (err) {
      if (!append) showToast(t('common.load_failed'), 'error')
    } finally {
      setLoading(false)
      setLoadingMore(false)
    }
  }

  useEffect(() => {
    if (isAdmin()) loadData(1, false)
  }, [])

  const loadUserDetail = async (userId) => {
    if (expandedUser === userId) { setExpandedUser(null); return }
    try {
      const res = await api.get(`/api/admin/users/${userId}`)
      setExpandedUserData(res.data)
      setExpandedUser(userId)
    } catch { showToast('Failed to load user', 'error') }
  }

  const handleRoleChange = async (userId, newRole) => {
    try {
      await api.put(`/api/admin/users/${userId}/role`, null, { params: { role: newRole } })
      showToast('Role updated', 'success')
      loadData()
    } catch (err) {
      showToast(errMsg(err), 'error')
    }
  }

  const handleBanUser = (userId) => {
    showPrompt(
      'Ban User',
      'Ban reason:',
      'Enter reason...',
      async (reason) => {
        if (!reason) return
        try {
          await api.post(`/api/admin/users/${userId}/ban`, null, { params: { reason } })
          showToast('User banned', 'success')
          loadData()
          if (expandedUser === userId) loadUserDetail(userId)
        } catch (err) { showToast(errMsg(err), 'error') }
      }
    )
  }

  const handleUnbanUser = async (userId) => {
    try {
      await api.post(`/api/admin/users/${userId}/unban`)
      showToast('User unbanned', 'success')
      loadData()
      if (expandedUser === userId) loadUserDetail(userId)
    } catch (err) { showToast(errMsg(err), 'error') }
  }

  const handleAdjustBalance = (userId) => {
    showPrompt(
      'Adjust Balance',
      'Amount to add (use negative to subtract):',
      '0.00',
      async (amount) => {
        if (!amount || isNaN(parseFloat(amount))) return
        try {
          await api.put(`/api/admin/users/${userId}/balance`, null, { params: { amount: parseFloat(amount) } })
          showToast('Balance updated', 'success')
          loadData()
          if (expandedUser === userId) loadUserDetail(userId)
        } catch (err) { showToast(errMsg(err), 'error') }
      }
    )
  }

  const handlePremiumToggle = async (userId, isPremium) => {
    try {
      await api.put(`/api/admin/users/${userId}/premium?is_premium=${!isPremium}`)
      showToast(`Premium ${isPremium ? 'revoked' : 'granted'}`, 'success')
      loadData()
      if (expandedUser === userId) loadUserDetail(userId)
    } catch (err) { showToast(errMsg(err), 'error') }
  }

  const loadAllBadges = async () => {
    try { const { data } = await api.get('/api/admin/badges'); setAllBadges(data) }
    catch { showToast(t('common.load_failed'), 'error') }
  }

  const handleAwardBadge = async (userId, badgeId) => {
    try {
      await api.post(`/api/badges/${badgeId}/award/${userId}`)
      showToast('Badge awarded', 'success')
      if (allBadges.length === 0) loadAllBadges()
    } catch (err) { showToast(errMsg(err), 'error') }
  }

  const handleMute = async (userId, reason, minutes) => {
    if (!reason?.trim()) { showToast('Reason required', 'error'); return }
    try {
      await api.post(`/api/mod/mute/${userId}`, null, {
        params: { reason: reason.trim(), ...(minutes ? { duration_minutes: minutes } : {}) }
      })
      showToast('User muted', 'success')
      setMuteUserId(null); setMuteReason('')
      loadData()
      if (expandedUser === userId) loadUserDetail(userId)
    } catch (err) { showToast(errMsg(err), 'error') }
  }

  const handleUnmute = async (userId) => {
    try {
      await api.post(`/api/mod/unmute/${userId}`)
      showToast('User unmuted', 'success')
      loadData()
      if (expandedUser === userId) loadUserDetail(userId)
    } catch (err) { showToast(errMsg(err), 'error') }
  }

  const handleWarn = (userId) => {
    showPrompt(
      'Warn User',
      'Warning reason:',
      'Enter reason...',
      async (reason) => {
        if (!reason) return
        try {
          await api.post(`/api/mod/warn/${userId}`, null, { params: { reason } })
          showToast('User warned', 'success')
        } catch (err) { showToast(errMsg(err), 'error') }
      }
    )
  }

  const handleForceLogout = (userId) => {
    showConfirm('Revoke all sessions for this user? They will be logged out everywhere.', async () => {
      try {
        await api.post(`/api/admin/users/${userId}/force-logout`)
        showToast('User logged out of all sessions', 'success')
      } catch (err) { showToast(errMsg(err), 'error') }
    })
  }

  const handleImpersonate = (userId) => {
    const currentToken = localStorage.getItem('token')
    if (currentToken) sessionStorage.setItem('admin_token', currentToken)
    api.post(`/api/admin/users/${userId}/impersonate`).then(res => {
      localStorage.setItem('token', res.data.token)
      window.location.href = '/app'
    }).catch(() => showToast('Impersonation not available', 'error'))
  }

  if (loading) {
    return <LoadingState label="loading users" />
  }

  return (
    <div className="space-y-4">
      {/* Stats bar */}
      {stats && (
        <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
          <StatTile label="Users" value={stats.total_users} />
          <StatTile label="Threads" value={stats.total_threads} />
          <StatTile label="Posts" value={stats.total_posts} />
          <StatTile label="Reports" value={stats.total_reports_pending} accent="red" />
          <StatTile label="Deposits" value={`$${stats.total_deposits.toFixed(0)}`} accent="emerald" />
          <StatTile label="Today" value={stats.users_today} accent="cyan" />
        </div>
      )}

      {/* Search + filters */}
      <div className="flex gap-2 items-center flex-wrap">
        <FormInput
          type="text"
          placeholder="Search users..."
          value={userSearch}
          onChange={e => setUserSearch(e.target.value)}
          className="flex-1 min-w-[160px]"
        />
        {['all', 'banned', 'muted', 'trial', 'user', 'moderator', 'admin'].map(f => (
          <Button
            key={f}
            size="xs"
            variant={userFilterRole === f ? 'primary' : 'ghost'}
            className="capitalize"
            onClick={() => setUserFilterRole(f)}
          >{f}</Button>
        ))}
        <Button variant="primary" size="sm" className="ml-auto" onClick={() => setShowCreateUser(true)}>
          + Create User
        </Button>
      </div>

      {/* Create User Modal */}
      <Modal open={showCreateUser} onClose={() => setShowCreateUser(false)} title="create_user" maxWidth="max-w-md">
        <div className="space-y-3">
          <FormInput
            label="Telegram ID"
            type="text"
            placeholder="Telegram ID"
            value={newUser.telegram_id}
            onChange={e => setNewUser({ ...newUser, telegram_id: e.target.value })}
          />
          <FormInput
            label="Username"
            type="text"
            placeholder="Username"
            value={newUser.username}
            onChange={e => setNewUser({ ...newUser, username: e.target.value })}
          />
          <FormInput
            label="Display Name"
            type="text"
            placeholder="Display Name"
            value={newUser.first_name}
            onChange={e => setNewUser({ ...newUser, first_name: e.target.value })}
          />
          <FormSelect
            label="Role"
            value={newUser.role}
            onChange={e => setNewUser({ ...newUser, role: e.target.value })}
          >
            <option value="USER">User</option>
            <option value="TRIAL">Trial</option>
            <option value="MODERATOR">Moderator</option>
            <option value="ADMIN">Admin</option>
          </FormSelect>
          <div className="flex gap-2">
            <Button variant="ghost" size="md" className="flex-1" onClick={() => setShowCreateUser(false)}>Cancel</Button>
            <Button variant="primary" size="md" className="flex-1" onClick={async () => {
              try {
                await api.post('/api/admin/users', newUser)
                showToast('User created', 'success')
                setShowCreateUser(false)
                setNewUser({ telegram_id: '', username: '', first_name: '', role: 'USER' })
                loadData()
              } catch (e) { showToast(e.response?.data?.detail || 'Failed', 'error') }
            }}>Create</Button>
          </div>
        </div>
      </Modal>

      {/* Mute Modal */}
      <Modal open={muteUserId !== null} onClose={() => setMuteUserId(null)} title="mute_user" maxWidth="max-w-md">
        <div className="space-y-3">
          <FormInput
            label="Mute reason"
            type="text"
            placeholder="Enter reason..."
            value={muteReason}
            onChange={e => setMuteReason(e.target.value)}
          />
          <div>
            <p className="text-[10px] text-dark-500 mb-1 uppercase">Duration</p>
            <div className="flex flex-wrap gap-1.5">
              {MUTE_PRESETS.map(p => (
                <Button
                  key={p.label}
                  size="sm"
                  variant={p.minutes === null ? 'danger' : 'warn'}
                  onClick={() => handleMute(muteUserId, muteReason, p.minutes)}
                >{p.label}</Button>
              ))}
            </div>
          </div>
          <Button variant="ghost" size="md" className="w-full" onClick={() => setMuteUserId(null)}>Cancel</Button>
        </div>
      </Modal>

      {/* User list */}
      <div className="space-y-1">
        {users.filter(u => {
          if (userSearch && !(u.username || '').toLowerCase().includes(userSearch.toLowerCase()) && !(u.first_name || '').toLowerCase().includes(userSearch.toLowerCase())) return false
          if (userFilterRole === 'banned' && !u.is_banned) return false
          if (userFilterRole === 'muted' && !u.is_muted) return false
          if (userFilterRole === 'trial' && String(u.role || '').toLowerCase().replace('userrole.', '') !== 'trial') return false
          if (userFilterRole === 'user' && String(u.role || '').toLowerCase().replace('userrole.', '') !== 'user') return false
          if (userFilterRole === 'moderator' && String(u.role || '').toLowerCase().replace('userrole.', '') !== 'moderator') return false
          if (userFilterRole === 'admin' && String(u.role || '').toLowerCase().replace('userrole.', '') !== 'admin') return false
          return true
        }).map(u => {
          const roleStr = String(u.role || '').toLowerCase().replace('userrole.', '')
          const isExpanded = expandedUser === u.id
          return (
            <Card key={u.id} className={`!p-3 ${isExpanded ? 'border-primary-500/30' : ''}`}>
              <div className="flex items-center gap-2 cursor-pointer" onClick={() => loadUserDetail(u.id)}>
                {u.avatar_url ? <img src={u.avatar_url} className="w-7 h-7 rounded-lg shrink-0" /> : <div className="w-7 h-7 rounded-lg bg-dark-600 flex items-center justify-center text-[10px] font-bold shrink-0">{(u.username || '?')[0]?.toUpperCase()}</div>}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{u.username || u.first_name}</p>
                  <p className="text-[10px] text-dark-500">ID: {u.id}</p>
                </div>
                {u.is_banned && <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-red-500/20 text-red-400">BANNED</span>}
                {u.is_muted && <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-orange-500/20 text-orange-400">MUTED</span>}
                {u.is_premium && <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-yellow-500/20 text-yellow-400">PREMIUM</span>}
                <span className="text-xs font-medium w-14 text-right">${(u.balance || 0).toFixed(2)}</span>
                <select value={roleStr} onChange={e => { e.stopPropagation(); handleRoleChange(u.id, e.target.value.toUpperCase()) }} onClick={e => e.stopPropagation()} className="bg-dark-950/60 border border-primary-500/15 text-white px-1.5 py-1 rounded text-[10px] focus:border-primary-500/50 focus:outline-none">
                  <option value="trial">Trial</option>
                  <option value="user">User</option>
                  <option value="moderator">Mod</option>
                  <option value="admin">Admin</option>
                </select>
                <span className="text-dark-500 text-[10px]">{isExpanded ? '▲' : '▼'}</span>
              </div>

              {isExpanded && expandedUserData && (
                <div className="mt-3 pt-3 border-t border-primary-500/15 space-y-3">
                  <div className="grid grid-cols-3 md:grid-cols-6 gap-2 text-xs">
                    <div className="bg-dark-700/50 rounded-lg p-2 text-center">
                      <p className="text-dark-400 text-[10px] uppercase">Posts</p>
                      <p className="font-bold">{expandedUserData.post_count}</p>
                    </div>
                    <div className="bg-dark-700/50 rounded-lg p-2 text-center">
                      <p className="text-dark-400 text-[10px] uppercase">Threads</p>
                      <p className="font-bold">{expandedUserData.thread_count}</p>
                    </div>
                    <div className="bg-dark-700/50 rounded-lg p-2 text-center">
                      <p className="text-dark-400 text-[10px] uppercase">Rep</p>
                      <p className="font-bold"><span className="text-green-400">+{expandedUserData.rep_positive}</span> <span className="text-red-400">-{expandedUserData.rep_negative}</span></p>
                    </div>
                    <div className="bg-dark-700/50 rounded-lg p-2 text-center">
                      <p className="text-dark-400 text-[10px] uppercase">Likes</p>
                      <p className="font-bold">{expandedUserData.like_count}</p>
                    </div>
                    <div className="bg-dark-700/50 rounded-lg p-2 text-center">
                      <p className="text-dark-400 text-[10px] uppercase">Joined</p>
                      <p className="font-bold text-[10px]">{parseDate(expandedUserData.created_at).toLocaleDateString()}</p>
                    </div>
                    <div className="bg-dark-700/50 rounded-lg p-2 text-center">
                      <p className="text-dark-400 text-[10px] uppercase">Last Seen</p>
                      <p className="font-bold text-[10px]">{expandedUserData.last_seen_at ? parseDate(expandedUserData.last_seen_at).toLocaleDateString() : '—'}</p>
                    </div>
                  </div>

                  {expandedUserData.ban_reason && <p className="text-xs text-red-400 bg-red-500/10 rounded-lg px-2 py-1">Ban: {expandedUserData.ban_reason}</p>}
                  {expandedUserData.is_muted && (
                    <p className="text-xs text-orange-400 bg-orange-500/10 rounded-lg px-2 py-1">
                      Muted{expandedUserData.mute_reason ? `: ${expandedUserData.mute_reason}` : ''}
                      {expandedUserData.mute_expires_at ? ` (until ${parseDate(expandedUserData.mute_expires_at).toLocaleString()})` : ' (permanent)'}
                    </p>
                  )}
                  {expandedUserData.profile_bio && <p className="text-xs text-dark-400 bg-dark-700/50 rounded-lg px-2 py-1">{expandedUserData.profile_bio}</p>}

                  <div className="flex items-center gap-2">
                    <span className={`text-xs ${expandedUserData.is_premium ? 'text-yellow-400' : 'text-dark-500'}`}>
                      {expandedUserData.is_premium ? 'Premium (permanent)' : 'Not premium'}
                    </span>
                    <Button
                      size="xs"
                      variant={expandedUserData.is_premium ? 'danger' : 'warn'}
                      onClick={() => handlePremiumToggle(u.id, expandedUserData.is_premium)}
                    >
                      {expandedUserData.is_premium ? 'Revoke' : 'Grant Premium'}
                    </Button>
                  </div>

                  <div className="flex flex-wrap gap-1.5">
                    {expandedUserData.is_banned ? (
                      <Button size="sm" variant="neon" onClick={() => handleUnbanUser(u.id)}>Unban</Button>
                    ) : (
                      <Button size="sm" variant="danger" onClick={() => handleBanUser(u.id)}>Ban</Button>
                    )}
                    {expandedUserData.is_muted ? (
                      <Button size="sm" variant="neon" onClick={() => handleUnmute(u.id)}>Unmute</Button>
                    ) : (
                      <Button size="sm" variant="warn" onClick={() => { setMuteReason(''); setMuteUserId(u.id) }}>Mute</Button>
                    )}
                    <Button size="sm" variant="warn" onClick={() => handleWarn(u.id)}>Warn</Button>
                    <Button size="sm" variant="secondary" onClick={() => handleAdjustBalance(u.id)}>Balance +/-</Button>
                    <Button size="sm" variant="secondary" onClick={() => handleImpersonate(u.id)}>Impersonate</Button>
                    <Button size="sm" variant="danger" onClick={() => handleForceLogout(u.id)}>Force logout</Button>
                  </div>

                  <div className="pt-2 border-t border-primary-500/15">
                    <p className="text-[10px] text-dark-500 mb-1">Award badge:</p>
                    <div className="flex flex-wrap gap-1">
                      {(allBadges.length > 0 ? allBadges : []).slice(0, 10).map(b => (
                        <button key={b.id} onClick={() => handleAwardBadge(u.id, b.id)}
                          className="text-[10px] px-2 py-1 rounded bg-dark-700 hover:bg-dark-600 text-dark-300 flex items-center gap-1"
                          title={b.description}>
                          <span className="w-2 h-2 rounded" style={{ backgroundColor: b.color }} />
                          {b.name}
                        </button>
                      ))}
                      {allBadges.length === 0 && (
                        <button onClick={loadAllBadges} className="text-[10px] text-primary-400 hover:underline">Load badges...</button>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </Card>
          )
        })}
        {users.length === 0 && <EmptyState>no_users_found</EmptyState>}
        {users.length > 0 && users.length < usersTotal && (
          <div className="text-center pt-2">
            <Button variant="secondary" size="sm" disabled={loadingMore} onClick={() => loadData(page + 1, true)}>
              {loadingMore ? 'Loading…' : `Load more (${users.length}/${usersTotal})`}
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
