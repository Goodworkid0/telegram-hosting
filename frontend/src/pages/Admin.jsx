import { useState, useEffect, useRef, useCallback } from 'react'
import { useAuthStore } from '../store/authStore'
import api from '../lib/api'
import { useToast } from '../components/Toast'
import {
  RefreshCw, ChevronDown,
  LayoutDashboard, Users, FolderTree, Award, FileText, Flag,
  ArrowDownToLine, ArrowUpFromLine, Gift, Image as ImageIcon, CalendarDays, Settings as SettingsIcon,
  ShieldCheck, FolderArchive, Megaphone,
} from 'lucide-react'

import {
  Button, FormInput, Toggle, StatTile, LoadingState, Modal,
} from '../components/admin/ui'

import AdminUsers from './admin/AdminUsers'
import AdminStructure from './admin/AdminStructure'
import AdminBadges from './admin/AdminBadges'
import AdminContent from './admin/AdminContent'
import AdminReports from './admin/AdminReports'
import AdminBanners from './admin/AdminBanners'
import AdminGiveaways from './admin/AdminGiveaways'
import AdminWithdrawals from './admin/AdminWithdrawals'
import AdminSettings from './admin/AdminSettings'
import AdminDailyRewards from './admin/AdminDailyRewards'
import AdminDeposits from './admin/AdminDeposits'
import AdminEscrow from './admin/AdminEscrow'
import AdminFiles from './admin/AdminFiles'
import AdminBroadcasts from './admin/AdminBroadcasts'

const cx = (...parts) => parts.filter(Boolean).join(' ')

const NAV_GROUPS = [
  { label: 'Overview', items: [
    { id: 'stats', label: 'Stats', icon: LayoutDashboard },
  ]},
  { label: 'Community', items: [
    { id: 'users', label: 'Users', icon: Users },
    { id: 'structure', label: 'Structure', icon: FolderTree },
    { id: 'achievements', label: 'Badges', icon: Award },
    { id: 'content', label: 'Content', icon: FileText },
    { id: 'reports', label: 'Reports', icon: Flag },
    { id: 'files', label: 'Files', icon: FolderArchive },
  ]},
  { label: 'Economy', items: [
    { id: 'deposits', label: 'Deposits', icon: ArrowDownToLine },
    { id: 'withdrawals', label: 'Withdrawals', icon: ArrowUpFromLine },
    { id: 'escrow', label: 'Escrow', icon: ShieldCheck },
    { id: 'giveaways', label: 'Giveaways', icon: Gift },
  ]},
  { label: 'Config', items: [
    { id: 'banners', label: 'Banners', icon: ImageIcon },
    { id: 'broadcasts', label: 'Broadcasts', icon: Megaphone },
    { id: 'daily-rewards', label: 'Daily Rewards', icon: CalendarDays },
    { id: 'settings', label: 'Settings', icon: SettingsIcon },
  ]},
]
const ALL_ITEMS = NAV_GROUPS.flatMap(g => g.items)

export default function Admin() {
  const { isAdmin } = useAuthStore()
  const { showToast } = useToast()
  const [activeTab, setActiveTab] = useState('stats')
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [lastRefresh, setLastRefresh] = useState(null)
  const refreshIntervalRef = useRef(null)

  const [confirmDelete, setConfirmDelete] = useState(null)
  const [promptModal, setPromptModal] = useState(null)
  const [promptValue, setPromptValue] = useState('')

  const showConfirm = (message, onConfirm) => setConfirmDelete({ message, onConfirm })
  const showPrompt = (title, label, placeholder, onSubmit) => setPromptModal({ title, label, placeholder, onSubmit })

  const loadData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const statsRes = await api.get('/api/admin/stats')
      setStats(statsRes.data)
      setLastRefresh(new Date())
    } catch (err) {
      if (!silent) showToast('Failed to load admin data', 'error')
    } finally {
      setLoading(false)
    }
  }, [showToast])

  useEffect(() => {
    if (isAdmin()) loadData()
  }, [isAdmin, loadData])

  useEffect(() => {
    if (autoRefresh && isAdmin()) {
      refreshIntervalRef.current = setInterval(() => loadData(true), 10000)
    }
    return () => {
      if (refreshIntervalRef.current) clearInterval(refreshIntervalRef.current)
    }
  }, [autoRefresh, isAdmin, loadData])

  if (!isAdmin()) {
    return (
      <div className="p-6 text-center">
        <p className="font-mono text-red-400">// access_denied — admins only</p>
      </div>
    )
  }

  if (loading) {
    return <LoadingState label="booting admin console" />
  }

  const activeMeta = ALL_ITEMS.find(i => i.id === activeTab) || ALL_ITEMS[0]
  const ActiveIcon = activeMeta.icon

  const tabProps = { showToast, showConfirm, showPrompt }

  return (
    <div className="p-4 max-w-6xl mx-auto">
      {/* ---- Header ---- */}
      <div className="flex items-center justify-between gap-3 mb-5">
        <div>
          <h1 className="font-mono text-2xl font-bold gradient-text tracking-tight">Admin Console</h1>
          {lastRefresh && (
            <p className="font-mono text-[11px] text-dark-500 mt-0.5">
              synced {lastRefresh.toLocaleTimeString()}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => loadData()}
            className="p-2 rounded-lg bg-dark-800/80 border border-primary-500/15 text-dark-300 hover:text-primary-300 hover:border-primary-500/40 transition-all"
            title="Refresh now"
          >
            <RefreshCw className={cx('w-4 h-4', loading && 'animate-spin')} />
          </button>
          <Toggle checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} label="Auto" />
        </div>
      </div>

      {/* ---- Mobile nav (dropdown) ---- */}
      <div className="md:hidden mb-4 relative">
        <select
          value={activeTab}
          onChange={e => setActiveTab(e.target.value)}
          className="w-full appearance-none bg-dark-900/80 border border-primary-500/20 rounded-lg pl-3 pr-9 py-2.5 font-mono text-sm text-primary-200 focus:border-primary-500/50 focus:outline-none"
        >
          {NAV_GROUPS.map(g => (
            <optgroup key={g.label} label={g.label}>
              {g.items.map(i => <option key={i.id} value={i.id}>{i.label}</option>)}
            </optgroup>
          ))}
        </select>
        <ChevronDown size={16} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-primary-400" />
      </div>

      <div className="flex gap-6">
        {/* ---- Sidebar nav (desktop) ---- */}
        <aside className="hidden md:block w-52 shrink-0">
          <nav className="sticky top-20 space-y-4">
            {NAV_GROUPS.map(group => (
              <div key={group.label}>
                <p className="px-3 mb-1.5 font-mono text-[10px] uppercase tracking-widest text-primary-500/50">{group.label}</p>
                <div className="space-y-0.5">
                  {group.items.map(item => {
                    const Icon = item.icon
                    const active = activeTab === item.id
                    return (
                      <button
                        key={item.id}
                        onClick={() => setActiveTab(item.id)}
                        className={cx(
                          'group relative w-full flex items-center gap-2.5 px-3 py-2 rounded-lg font-mono text-sm transition-all',
                          active
                            ? 'bg-primary-500/10 text-primary-200 border border-primary-500/30'
                            : 'text-dark-400 border border-transparent hover:text-dark-100 hover:bg-dark-800/50'
                        )}
                      >
                        {active && (
                          <span className="absolute left-0 top-1/2 -translate-y-1/2 h-4 w-0.5 rounded-full bg-primary-400 shadow-neon-cyan" />
                        )}
                        <Icon size={16} className={active ? 'text-primary-400' : ''} />
                        <span className="truncate">{item.label}</span>
                      </button>
                    )
                  })}
                </div>
              </div>
            ))}
          </nav>
        </aside>

        {/* ---- Content ---- */}
        <div className="flex-1 min-w-0">
          <div className="mb-4 flex items-center gap-2 font-mono text-sm font-bold uppercase tracking-widest text-primary-300">
            <span className="text-primary-500/60">&gt;</span>
            <ActiveIcon size={16} className="text-primary-400" />
            {activeMeta.label}
            <span className="text-primary-500/25 animate-pulse">_</span>
          </div>

          {activeTab === 'stats' && stats && (
            <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
              <StatTile label="Users" value={stats.total_users} />
              <StatTile label="Threads" value={stats.total_threads} />
              <StatTile label="Posts" value={stats.total_posts} />
              <StatTile label="Reports" value={stats.total_reports_pending} accent="red" />
              <StatTile label="Deposits" value={`$${stats.total_deposits.toFixed(0)}`} accent="emerald" />
              <StatTile label="Today" value={stats.users_today} accent="cyan" />
            </div>
          )}

          {activeTab === 'users' && <AdminUsers {...tabProps} />}
          {activeTab === 'structure' && <AdminStructure {...tabProps} />}
          {activeTab === 'achievements' && <AdminBadges {...tabProps} />}
          {activeTab === 'content' && <AdminContent {...tabProps} />}
          {activeTab === 'reports' && <AdminReports {...tabProps} />}
          {activeTab === 'banners' && <AdminBanners {...tabProps} />}
          {activeTab === 'giveaways' && <AdminGiveaways {...tabProps} />}
          {activeTab === 'withdrawals' && <AdminWithdrawals {...tabProps} />}
          {activeTab === 'escrow' && <AdminEscrow {...tabProps} />}
          {activeTab === 'files' && <AdminFiles {...tabProps} />}
          {activeTab === 'broadcasts' && <AdminBroadcasts {...tabProps} />}
          {activeTab === 'settings' && <AdminSettings {...tabProps} />}
          {activeTab === 'daily-rewards' && <AdminDailyRewards {...tabProps} />}
          {activeTab === 'deposits' && <AdminDeposits {...tabProps} />}
        </div>
      </div>

      {/* ---- Confirm modal ---- */}
      <Modal open={!!confirmDelete} onClose={() => setConfirmDelete(null)} title="Confirm Delete" maxWidth="max-w-sm">
        <p className="text-dark-300 text-sm mb-5">{confirmDelete?.message}</p>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(null)}>Cancel</Button>
          <Button
            variant="danger"
            size="sm"
            onClick={() => { const fn = confirmDelete?.onConfirm; setConfirmDelete(null); fn && fn() }}
          >
            Delete
          </Button>
        </div>
      </Modal>

      {/* ---- Prompt modal ---- */}
      <Modal
        open={!!promptModal}
        onClose={() => { setPromptModal(null); setPromptValue('') }}
        title={promptModal?.title}
        maxWidth="max-w-sm"
      >
        <FormInput
          label={promptModal?.label}
          placeholder={promptModal?.placeholder}
          value={promptValue}
          onChange={e => setPromptValue(e.target.value)}
          autoFocus
          onKeyDown={e => {
            if (e.key === 'Enter') {
              const fn = promptModal?.onSubmit
              setPromptModal(null); setPromptValue(''); fn && fn(promptValue)
            }
          }}
          className="mb-5"
        />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => { setPromptModal(null); setPromptValue('') }}>Cancel</Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => { const fn = promptModal?.onSubmit; setPromptModal(null); setPromptValue(''); fn && fn(promptValue) }}
          >
            Submit
          </Button>
        </div>
      </Modal>
    </div>
  )
}
