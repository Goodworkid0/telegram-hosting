import { useState, useEffect } from 'react'
import api from '../../lib/api'
import { parseDate } from '../../lib/utils'
import { Card, SectionHeader, StatusBadge, EmptyState, LoadingState, Button, FormInput, FormSelect } from '../../components/admin/ui'

const PER_PAGE = 20

// Filter key -> query params sent to /api/admin/deposits
const FILTERS = {
  all: {},
  credited: { credited: true },
  pending: { credited: false },
  needs_review: { status: 'needs_review' },
}

export default function AdminDeposits({ showToast }) {
  const [deposits, setDeposits] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')

  const loadDeposits = async () => {
    setLoading(true)
    try {
      const params = { page, per_page: PER_PAGE, ...FILTERS[filter] }
      if (search.trim()) params.search = search.trim()
      const res = await api.get('/api/admin/deposits', { params })
      setDeposits(res.data)
    } catch (err) {
      import.meta.env.DEV && console.error(err)
      showToast?.('Failed to load deposits', 'error')
    } finally { setLoading(false) }
  }

  // Reset to page 1 whenever the filter or search term changes.
  useEffect(() => { setPage(1) }, [filter, search])

  // Debounce so typing in the search box doesn't fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(loadDeposits, 300)
    return () => clearTimeout(t)
  }, [page, filter, search])

  const total = deposits.total || 0
  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE))

  return (
    <div className="space-y-4">
      <SectionHeader right={<span className="font-mono text-xs text-dark-400">{total} total</span>}>
        DEPOSITS
      </SectionHeader>

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3">
        <FormInput
          label="Search user"
          type="text"
          placeholder="username or id"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="flex-1 min-w-[180px]"
        />
        <FormSelect label="Status" value={filter} onChange={e => setFilter(e.target.value)} className="min-w-[150px]">
          <option value="all">All</option>
          <option value="credited">Credited</option>
          <option value="pending">Pending</option>
          <option value="needs_review">Needs review</option>
        </FormSelect>
      </div>

      {loading ? (
        <LoadingState label="loading deposits" />
      ) : deposits.items?.length === 0 ? (
        <EmptyState>no_deposits</EmptyState>
      ) : (
        <>
          <Card className="!p-0 overflow-x-auto">
            <table className="w-full">
              <thead className="bg-dark-800/60 font-mono text-[10px] uppercase tracking-wider text-primary-400/70">
                <tr>
                  <th className="px-4 py-3 text-left">User</th>
                  <th className="px-4 py-3 text-left">Coin</th>
                  <th className="px-4 py-3 text-left">Amount</th>
                  <th className="px-4 py-3 text-left">Status</th>
                  <th className="px-4 py-3 text-left">Date</th>
                </tr>
              </thead>
              <tbody>
                {deposits.items.map(d => (
                  <tr key={d.id} className="border-t border-primary-500/10">
                    <td className="px-4 py-3 text-sm">
                      <span className="font-medium">{d.username || 'unknown'}</span>
                      <span className="ml-1 text-xs text-dark-500 font-mono">#{d.user_id}</span>
                    </td>
                    <td className="px-4 py-3 text-xs font-mono uppercase">{d.pay_currency || '-'}</td>
                    <td className="px-4 py-3 text-sm font-mono font-medium">${(d.price_amount_usd || 0).toFixed(2)}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={d.is_credited ? 'completed' : (d.payment_status || 'pending')} />
                    </td>
                    <td className="px-4 py-3 text-xs text-dark-400">
                      {d.created_at ? parseDate(d.created_at).toLocaleString() : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))}>
                Prev
              </Button>
              <span className="font-mono text-xs text-dark-400">Page {page} / {totalPages}</span>
              <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))}>
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
