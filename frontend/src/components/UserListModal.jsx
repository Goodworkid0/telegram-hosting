import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Modal, RoleBadge, EmptyState } from './ui'
import Spinner from './Spinner'
import { displayName } from '../lib/utils'
import api from '../lib/api'
import { useT } from '../lib/i18n'

// Reusable modal that fetches a list of users from `url` and links each to their
// profile. Tolerates both server shapes:
//   - [UserMinimal]                 (followers / following)
//   - [{ user: UserMinimal, ... }]  (post / thread likers)
// Fetches lazily when opened; refetches if the url changes.
const PER_PAGE = 20

export default function UserListModal({ open, onClose, title, url }) {
  const t = useT()
  const [users, setUsers] = useState(null) // null = loading
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)

  const fetchPage = (pageVal, append) => {
    const sep = url.includes('?') ? '&' : '?'
    return api.get(`${url}${sep}page=${pageVal}&per_page=${PER_PAGE}`)
      .then((res) => {
        const list = (res.data || []).map((item) => item?.user ?? item).filter(Boolean)
        setUsers(prev => (append && prev ? [...prev, ...list] : list))
        // Bare-array endpoints have no total; infer "more" from a full page.
        setHasMore(list.length === PER_PAGE)
      })
  }

  useEffect(() => {
    if (!open || !url) return
    let cancelled = false
    setUsers(null)
    setPage(1)
    fetchPage(1, false).catch(() => { if (!cancelled) { setUsers([]); setHasMore(false) } })
    return () => { cancelled = true }
  }, [open, url])

  const loadMore = async () => {
    const next = page + 1
    setLoadingMore(true)
    try {
      await fetchPage(next, true)
      setPage(next)
    } catch { setHasMore(false) } finally { setLoadingMore(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title={title}>
      {users === null ? (
        <div className="py-8 flex justify-center"><Spinner /></div>
      ) : users.length === 0 ? (
        <EmptyState>{t('modals.userlist.empty')}</EmptyState>
      ) : (
        <div className="max-h-[60vh] overflow-y-auto -mx-2 px-2 space-y-1.5">
          {users.map((u) => (
            <Link
              key={u.id}
              to={`/profile/${u.id}`}
              onClick={onClose}
              className="flex items-center gap-3 rounded-xl p-2.5 border bg-dark-900/80 border-primary-500/10 hover:border-primary-500/25 transition-colors"
            >
              <div className="w-9 h-9 rounded-full bg-dark-800 flex items-center justify-center overflow-hidden flex-shrink-0">
                {u.avatar_url ? (
                  <img src={u.avatar_url} alt="" className="w-full h-full object-cover" />
                ) : (
                  <span className="text-sm font-bold text-dark-400">
                    {(displayName(u, false)[0] || '?').toUpperCase()}
                  </span>
                )}
              </div>
              <span className="flex-1 min-w-0 font-semibold text-sm truncate">{displayName(u)}</span>
              <RoleBadge role={u.role} />
            </Link>
          ))}
          {hasMore && (
            <button
              onClick={loadMore}
              disabled={loadingMore}
              className="w-full py-2 text-xs font-mono text-primary-400 hover:text-primary-300 disabled:opacity-50 transition-colors"
            >
              {loadingMore ? '…' : t('common.load_more')}
            </button>
          )}
        </div>
      )}
    </Modal>
  )
}
