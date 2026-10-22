import { useState, useEffect } from 'react'
import api from '../../lib/api'
import { Card, SectionHeader, StatusBadge, EmptyState, LoadingState } from '../../components/admin/ui'
import { Button, FormInput } from '../../components/ui'
import { Check, X, Trash2, FileText, FolderPlus, Plus } from 'lucide-react'

const cx = (...p) => p.filter(Boolean).join(' ')

// Temporarily hidden — flip to true to bring back the per-file delete button.
const SHOW_DELETE = false

const FILTERS = [
  { value: 'pending', label: 'Pending' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'all', label: 'All' },
]

function humanSize(bytes) {
  if (bytes == null) return ''
  const u = ['B', 'KB', 'MB', 'GB']
  let n = bytes, i = 0
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++ }
  return `${n.toFixed(n < 10 && i > 0 ? 1 : 0)} ${u[i]}`
}

export default function AdminFiles({ showToast, showConfirm }) {
  const [status, setStatus] = useState('pending')
  const [data, setData] = useState({ items: [], total: 0 })
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [busy, setBusy] = useState(null)
  const [categories, setCategories] = useState([])
  // Per-row category selection (drives the Approve button's target category).
  const [pick, setPick] = useState({})
  const [newCat, setNewCat] = useState('')
  const [catBusy, setCatBusy] = useState(false)
  const PER_PAGE = 50

  const load = async (pageVal = 1, append = false) => {
    if (append) setLoadingMore(true)
    else setLoading(true)
    try {
      const res = await api.get('/api/admin/files', { params: { status, page: pageVal, per_page: PER_PAGE } })
      setData(prev => append
        ? { ...res.data, items: [...prev.items, ...(res.data.items || [])] }
        : res.data)
      setPage(pageVal)
    } catch {
      if (!append) showToast?.('Failed to load files', 'error')
    } finally {
      setLoading(false)
      setLoadingMore(false)
    }
  }

  const loadCategories = async () => {
    try {
      const res = await api.get('/api/admin/file-categories')
      setCategories(res.data || [])
    } catch { /* non-fatal */ }
  }

  useEffect(() => { load(1, false) }, [status])
  useEffect(() => { loadCategories() }, [])

  const run = async (id, fn, okMsg) => {
    setBusy(id)
    try {
      await fn()
      if (okMsg) showToast?.(okMsg, 'success')
      await load()
    } catch (err) {
      showToast?.(err.response?.data?.detail || 'Action failed', 'error')
    } finally {
      setBusy(null)
    }
  }

  // Untouched dropdown falls back to the uploader's suggestion; an explicit
  // pick (including "Uncategorized" = '') overrides it.
  const pendingValue = (f) => (pick[f.id] !== undefined ? pick[f.id] : (f.suggested_category_id ?? ''))

  const approve = (f) => {
    const raw = pendingValue(f)
    const category_id = raw ? Number(raw) : null
    return run(f.id, () => api.post(`/api/admin/files/${f.id}/approve`, { category_id }), 'Approved')
  }

  const reject = (f) =>
    run(f.id, () => api.post(`/api/admin/files/${f.id}/reject`, { reason: null }), 'Rejected')

  const remove = (f) =>
    showConfirm?.('Remove this file from the board? The channel archive copies are kept.', () =>
      run(f.id, () => api.delete(`/api/admin/files/${f.id}`), 'Deleted'))

  const setCategory = (f, category_id) =>
    run(f.id, () => api.post(`/api/admin/files/${f.id}/category`, { category_id: category_id ? Number(category_id) : null }), 'Category updated')

  const createCategory = async () => {
    const name = newCat.trim()
    if (!name) return
    setCatBusy(true)
    try {
      await api.post('/api/admin/file-categories', { name })
      setNewCat('')
      await loadCategories()
      showToast?.('Category created', 'success')
    } catch (err) {
      showToast?.(err.response?.data?.detail || 'Failed to create category', 'error')
    } finally {
      setCatBusy(false)
    }
  }

  const deleteCategory = (c) =>
    showConfirm?.(`Delete category "${c.name}"? Its files become uncategorized.`, async () => {
      try {
        await api.delete(`/api/admin/file-categories/${c.id}`)
        await loadCategories()
        await load()
        showToast?.('Category deleted', 'success')
      } catch (err) {
        showToast?.(err.response?.data?.detail || 'Failed to delete', 'error')
      }
    })

  return (
    <div className="space-y-4">
      <SectionHeader icon={FileText} title="File Share" subtitle="Approve user-dropped files and sort them into categories" />

      {/* Category management */}
      <Card className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-white">
          <FolderPlus size={16} className="text-primary-400" /> Categories
        </div>
        <div className="flex gap-2">
          <FormInput
            className="flex-1"
            placeholder="New category name"
            value={newCat}
            onChange={e => setNewCat(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') createCategory() }}
          />
          <Button variant="primary" icon={Plus} disabled={catBusy || !newCat.trim()} onClick={createCategory}>Add</Button>
        </div>
        {categories.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {categories.map(c => (
              <span key={c.id} className="inline-flex items-center gap-1.5 text-xs bg-dark-800 border border-dark-700 rounded-lg pl-2.5 pr-1.5 py-1">
                <span className="text-dark-200">{c.name}</span>
                <span className="text-dark-500">{c.file_count ?? 0}</span>
                <button onClick={() => deleteCategory(c)} className="text-dark-500 hover:text-red-400 transition-colors">
                  <X size={13} />
                </button>
              </span>
            ))}
          </div>
        )}
      </Card>

      <div className="flex gap-2 flex-wrap">
        {FILTERS.map(f => (
          <button
            key={f.value}
            onClick={() => setStatus(f.value)}
            className={cx('px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
              status === f.value ? 'bg-primary-500 text-dark-950' : 'bg-dark-800 text-dark-300 hover:bg-dark-700')}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <LoadingState />
      ) : data.items.length === 0 ? (
        <Card><EmptyState icon={FileText}>No files</EmptyState></Card>
      ) : (
        <div className="space-y-2">
          {data.items.map(f => (
            <Card key={f.id} className="group !p-3">
              <div className="flex items-center gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-white truncate" title={f.file_name}>{f.file_name}</span>
                  <StatusBadge status={f.status} />
                  {f.category_name && (
                    <span className="text-[10px] font-medium text-primary-300 bg-primary-500/10 border border-primary-500/20 px-1.5 py-0.5 rounded flex-shrink-0">{f.category_name}</span>
                  )}
                </div>
                <div className="text-[11px] font-mono text-dark-500 mt-0.5 flex flex-wrap gap-2">
                  <span>{f.kind}</span>
                  {f.file_size != null && <><span>·</span><span>{humanSize(f.file_size)}</span></>}
                  {f.uploader && <><span>·</span><span>@{f.uploader.username || f.uploader.first_name || f.uploader.id}</span></>}
                  {f.download_count > 0 && <><span>·</span><span>{f.download_count} dl</span></>}
                  {f.status === 'PENDING' && f.suggested_category_name && (
                    <><span>·</span><span className="text-amber-400">suggested: {f.suggested_category_name}</span></>
                  )}
                  {f.reject_reason && <><span>·</span><span className="text-red-400">{f.reject_reason}</span></>}
                </div>
                {f.caption && <div className="text-xs text-dark-400 mt-1 line-clamp-2">{f.caption}</div>}
              </div>
              <div className="flex items-center gap-1.5 flex-shrink-0">
                {/* Pending: pick a category, then Approve uses it. Approved: change category inline. */}
                <select
                  value={f.status === 'APPROVED' ? (f.category_id ?? '') : pendingValue(f)}
                  onChange={e => {
                    const v = e.target.value
                    if (f.status === 'APPROVED') setCategory(f, v)
                    else setPick(p => ({ ...p, [f.id]: v }))
                  }}
                  disabled={busy === f.id}
                  className="bg-dark-800 border border-dark-700 rounded-lg text-xs text-dark-200 px-2 py-1.5 max-w-[9rem]"
                >
                  <option value="">Uncategorized</option>
                  {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
                {f.status !== 'APPROVED' && (
                  <Button variant="primary" size="sm" icon={Check} disabled={busy === f.id} onClick={() => approve(f)}>Approve</Button>
                )}
                {f.status !== 'REJECTED' && (
                  <Button variant="ghost" size="sm" icon={X} disabled={busy === f.id} onClick={() => reject(f)}>Reject</Button>
                )}
                {SHOW_DELETE && (
                  <Button variant="ghost" size="sm" icon={Trash2} disabled={busy === f.id} onClick={() => remove(f)} />
                )}
              </div>
              </div>
              {/* Hover reveals the full (untruncated) name + caption before deciding. */}
              <div className="overflow-hidden max-h-0 opacity-0 group-hover:max-h-48 group-hover:opacity-100 transition-all duration-200">
                <div className="pt-2 mt-2 border-t border-dark-800 text-[11px] font-mono text-dark-300 break-all">
                  {f.file_name}
                  {f.caption && <div className="text-dark-500 mt-1 whitespace-pre-wrap break-words">{f.caption}</div>}
                </div>
              </div>
            </Card>
          ))}
          {data.items.length < (data.total || 0) && (
            <div className="text-center pt-1">
              <Button variant="secondary" size="sm" disabled={loadingMore} onClick={() => load(page + 1, true)}>
                {loadingMore ? 'Loading…' : `Load more (${data.items.length}/${data.total})`}
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
