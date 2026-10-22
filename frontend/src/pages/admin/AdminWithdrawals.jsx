import { useState, useEffect } from 'react'
import api from '../../lib/api'
import { Card, SectionHeader, Button, StatusBadge, EmptyState, LoadingState } from '../../components/admin/ui'

export default function AdminWithdrawals({ showToast, showPrompt }) {
  const [withdrawals, setWithdrawals] = useState({ items: [], total: 0, pending_count: 0 })
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const PER_PAGE = 20

  const loadWithdrawals = async (pageVal = 1, append = false) => {
    if (append) setLoadingMore(true)
    else setLoading(true)
    try {
      const res = await api.get('/api/admin/withdrawals', { params: { page: pageVal, per_page: PER_PAGE } })
      setWithdrawals(prev => append
        ? { ...res.data, items: [...prev.items, ...(res.data.items || [])] }
        : res.data)
      setPage(pageVal)
    } catch (err) { import.meta.env.DEV && console.error(err) }
    finally { setLoading(false); setLoadingMore(false) }
  }

  useEffect(() => { loadWithdrawals(1, false) }, [])

  const handleApproveWithdrawal = (id) => {
    showPrompt(
      'Approve Withdrawal',
      'Enter transaction hash (optional):',
      'tx hash...',
      async (txHash) => {
        try {
          await api.put(`/api/admin/withdrawals/${id}/approve`, null, { params: txHash ? { tx_hash: txHash } : {} })
          showToast('Withdrawal approved', 'success')
          loadWithdrawals()
        } catch (err) { showToast(err.response?.data?.detail || 'Failed', 'error') }
      }
    )
  }

  const handleRejectWithdrawal = (id) => {
    showPrompt(
      'Reject Withdrawal',
      'Rejection reason (optional):',
      'Enter reason...',
      async (reason) => {
        try {
          await api.put(`/api/admin/withdrawals/${id}/reject`, null, { params: reason ? { reason } : {} })
          showToast('Withdrawal rejected & refunded', 'success')
          loadWithdrawals()
        } catch (err) { showToast(err.response?.data?.detail || 'Failed', 'error') }
      }
    )
  }

  return (
    <div className="space-y-4">
      <SectionHeader
        right={withdrawals.pending_count > 0 && (
          <span className="bg-amber-500/15 text-amber-300 border border-amber-500/30 text-xs font-mono font-semibold px-2 py-0.5 rounded">{withdrawals.pending_count} pending</span>
        )}
      >
        WITHDRAWAL_REQUESTS
      </SectionHeader>
      {loading ? (
        <LoadingState label="loading withdrawals" />
      ) : withdrawals.items?.length === 0 ? (
        <EmptyState>no_withdrawal_requests</EmptyState>
      ) : (
        <Card className="!p-0 overflow-x-auto">
          <table className="w-full">
            <thead className="bg-dark-800/60 font-mono text-[10px] uppercase tracking-wider text-primary-400/70">
              <tr>
                <th className="px-4 py-3 text-left">User</th>
                <th className="px-4 py-3 text-left">Amount</th>
                <th className="px-4 py-3 text-left">Address</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {withdrawals.items.map(w => (
                <tr key={w.id} className="border-t border-primary-500/10">
                  <td className="px-4 py-3 text-sm">{w.username || w.user_id}</td>
                  <td className="px-4 py-3 text-sm font-mono font-medium">${(w.amount || 0).toFixed(2)}</td>
                  <td className="px-4 py-3 text-xs text-dark-400 font-mono max-w-[200px] truncate">{w.crypto_address || '-'}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={w.status} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    {w.status === 'pending' && (
                      <div className="flex gap-2 justify-end">
                        <Button variant="neon" size="xs" onClick={() => handleApproveWithdrawal(w.id)}>Approve</Button>
                        <Button variant="danger" size="xs" onClick={() => handleRejectWithdrawal(w.id)}>Reject</Button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      {!loading && withdrawals.items?.length > 0 && withdrawals.items.length < (withdrawals.total || 0) && (
        <div className="text-center pt-1">
          <Button variant="secondary" size="sm" disabled={loadingMore} onClick={() => loadWithdrawals(page + 1, true)}>
            {loadingMore ? 'Loading…' : `Load more (${withdrawals.items.length}/${withdrawals.total})`}
          </Button>
        </div>
      )}
    </div>
  )
}
