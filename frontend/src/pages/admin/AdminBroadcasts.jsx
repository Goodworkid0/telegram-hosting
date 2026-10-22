import { useState, useEffect } from 'react'
import api from '../../lib/api'
import { Card, SectionHeader, StatusBadge, EmptyState, LoadingState } from '../../components/admin/ui'
import { Button, FormInput, FormTextarea, FormSelect } from '../../components/ui'
import { Megaphone, Send, Inbox, MessageCircle } from 'lucide-react'

const AUDIENCES = [
  { value: '', label: 'All users' },
  { value: 'TRIAL', label: 'Trial only' },
  { value: 'USER', label: 'Members (USER)' },
  { value: 'MODERATOR', label: 'Moderators' },
  { value: 'ADMIN', label: 'Admins' },
]

const EMPTY = { title: '', body: '', link: '', send_inbox: true, send_bot: false, target_role: '' }

export default function AdminBroadcasts({ showToast, showConfirm }) {
  const [form, setForm] = useState(EMPTY)
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [sending, setSending] = useState(false)
  const PER_PAGE = 30

  const load = async (pageVal = 1, append = false) => {
    if (append) setLoadingMore(true)
    else setLoading(true)
    try {
      const res = await api.get('/api/admin/broadcasts', { params: { page: pageVal, per_page: PER_PAGE } })
      const list = res.data.items || []
      setItems(prev => append ? [...prev, ...list] : list)
      setTotal(res.data.total || 0)
      setPage(pageVal)
    } catch {
      if (!append) showToast?.('Failed to load broadcasts', 'error')
    } finally {
      setLoading(false)
      setLoadingMore(false)
    }
  }

  useEffect(() => { load(1, false) }, [])

  const submit = () => {
    if (!form.title.trim()) return showToast?.('Title is required', 'error')
    if (!form.send_inbox && !form.send_bot) return showToast?.('Pick at least one channel', 'error')
    const audienceLabel = AUDIENCES.find(a => a.value === form.target_role)?.label || 'All users'
    const channels = [form.send_inbox && 'inbox', form.send_bot && 'Telegram DM'].filter(Boolean).join(' + ')
    showConfirm?.(
      `Send "${form.title.trim()}" to ${audienceLabel} via ${channels}? This cannot be undone.`,
      async () => {
        setSending(true)
        try {
          await api.post('/api/admin/broadcasts', {
            ...form,
            title: form.title.trim(),
            body: form.body.trim() || null,
            link: form.link.trim() || null,
            target_role: form.target_role || null,
          })
          showToast?.('Broadcast queued — delivering in the background', 'success')
          setForm(EMPTY)
          await load()
        } catch (err) {
          showToast?.(err.response?.data?.detail || 'Failed to queue broadcast', 'error')
        } finally {
          setSending(false)
        }
      },
    )
  }

  return (
    <div className="space-y-4">
      <SectionHeader icon={Megaphone} title="Broadcasts" subtitle="Send an announcement / ad to users' inbox and Telegram DM" />

      <Card className="space-y-3">
        <FormInput label="Title" placeholder="Headline" value={form.title} maxLength={200}
          onChange={e => setForm({ ...form, title: e.target.value })} />
        <FormTextarea label="Message" placeholder="Body text (optional)" rows={4} value={form.body}
          onChange={e => setForm({ ...form, body: e.target.value })} />
        <FormInput label="Link (optional)" placeholder="/shop or https://…" value={form.link}
          onChange={e => setForm({ ...form, link: e.target.value })} />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <FormSelect label="Audience" value={form.target_role}
            onChange={e => setForm({ ...form, target_role: e.target.value })}>
            {AUDIENCES.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
          </FormSelect>
          <div>
            <label className="block text-xs font-medium text-dark-400 mb-1.5 uppercase tracking-wider">Channels</label>
            <div className="flex gap-2">
              <button type="button" onClick={() => setForm({ ...form, send_inbox: !form.send_inbox })}
                className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-lg text-xs font-medium border transition-colors ${form.send_inbox ? 'bg-primary-500/15 border-primary-500/40 text-primary-300' : 'bg-dark-800 border-dark-700 text-dark-400'}`}>
                <Inbox size={14} /> Inbox
              </button>
              <button type="button" onClick={() => setForm({ ...form, send_bot: !form.send_bot })}
                className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-lg text-xs font-medium border transition-colors ${form.send_bot ? 'bg-primary-500/15 border-primary-500/40 text-primary-300' : 'bg-dark-800 border-dark-700 text-dark-400'}`}>
                <MessageCircle size={14} /> Telegram DM
              </button>
            </div>
          </div>
        </div>

        <Button variant="primary" icon={Send} disabled={sending} onClick={submit} className="w-full">
          {sending ? 'Queuing…' : 'Send broadcast'}
        </Button>
      </Card>

      <div>
        <div className="text-xs font-semibold text-dark-400 uppercase tracking-wider mb-2">Recent</div>
        {loading ? (
          <LoadingState />
        ) : items.length === 0 ? (
          <Card><EmptyState icon={Megaphone}>No broadcasts yet</EmptyState></Card>
        ) : (
          <div className="space-y-2">
            {items.map(b => (
              <Card key={b.id} className="!p-3">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-white truncate flex-1">{b.title}</span>
                  <StatusBadge status={b.status} />
                </div>
                <div className="text-[11px] font-mono text-dark-500 mt-1 flex flex-wrap gap-2">
                  <span>{b.target_role || 'ALL'}</span>
                  {b.send_inbox && <><span>·</span><span>inbox</span></>}
                  {b.send_bot && <><span>·</span><span>DM</span></>}
                  <span>·</span><span>{b.sent_count}/{b.total_recipients} sent</span>
                  {b.failed_count > 0 && <><span>·</span><span className="text-red-400">{b.failed_count} failed</span></>}
                </div>
              </Card>
            ))}
            {items.length < total && (
              <div className="text-center pt-1">
                <Button variant="secondary" size="sm" disabled={loadingMore} onClick={() => load(page + 1, true)}>
                  {loadingMore ? 'Loading…' : `Load more (${items.length}/${total})`}
                </Button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
