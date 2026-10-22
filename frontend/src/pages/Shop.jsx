import { useState, useEffect, useCallback, useRef } from 'react'
import { motion } from 'framer-motion'
import QRCode from 'qrcode'
import { Wallet as WalletIcon, Copy, Check, AlertCircle, QrCode, Star, Plus, ArrowDownToLine, ArrowUpFromLine, ChevronLeft } from 'lucide-react'
import { useAuthStore } from '../store/authStore'
import api from '../lib/api'
import { useT, getDateLocale } from '../lib/i18n'
import { useToast } from '../components/Toast'
import { globalConfirm } from '../components/ConfirmModal'
import { formatDate, parseDate } from '../lib/utils'
import { Card, SectionHeader, PageHeading, Button, Tag, StatusBadge, FormInput, EmptyState, LoadingState, Modal } from '../components/ui'

// Gradient per coin symbol; anything unmapped falls back to a neutral gradient.
const COIN_COLORS = {
  BTC: 'from-orange-400 to-orange-600',
  LTC: 'from-gray-400 to-gray-600',
  ETH: 'from-blue-400 to-purple-600',
  XMR: 'from-orange-500 to-gray-600',
  USDT: 'from-emerald-400 to-emerald-600',
  USDC: 'from-blue-400 to-blue-600',
  SOL: 'from-purple-400 to-fuchsia-600',
  TRX: 'from-red-400 to-red-600',
  BNB: 'from-yellow-400 to-yellow-600',
  DOGE: 'from-amber-300 to-amber-500',
  TON: 'from-sky-400 to-sky-600',
  XRP: 'from-slate-400 to-slate-600',
}
const coinColor = (symbol) => COIN_COLORS[symbol?.toUpperCase()] || 'from-primary-400 to-primary-600'

const sanitizeAmount = (value) => {
  const normalized = value.replace(',', '.')
  const stripped = normalized.replace(/[^0-9.]/g, '')
  const [whole, ...rest] = stripped.split('.')
  if (rest.length === 0) return whole
  return `${whole}.${rest.join('')}`
}

const formatAmount = (value) => {
  if (!value) return ''
  const num = Number(value)
  if (!Number.isFinite(num)) return ''
  return num.toFixed(2)
}

export default function Shop() {
  const t = useT()
  const { user, setUser, subscriptionActive } = useAuthStore()
  const { addToast, showToast } = useToast()

  // Hub navigation: 'hub' landing + one view per category.
  const [view, setView] = useState('hub')
  const [coins, setCoins] = useState([])
  const [coinsLoading, setCoinsLoading] = useState(true)
  const [selectedCoin, setSelectedCoin] = useState(null)
  const [amount, setAmount] = useState('')
  const [depositStatus, setDepositStatus] = useState({ status: 'idle', message: '' })
  const [depositInfo, setDepositInfo] = useState(null)
  const [qrDataUrl, setQrDataUrl] = useState('')
  const [copied, setCopied] = useState(false)
  const [balanceRefreshed, setBalanceRefreshed] = useState(false)

  const [withdrawAmount, setWithdrawAmount] = useState('')
  const [withdrawAddress, setWithdrawAddress] = useState('')
  const [withdrawPin, setWithdrawPin] = useState('')
  const [withdrawStatus, setWithdrawStatus] = useState({ status: 'idle', message: '' })
  // Idempotency key for the current withdrawal intent — kept stable across
  // retries of the same submission (so a network retry / double-tap dedupes on
  // the server), regenerated whenever the amount/address change.
  const withdrawIdemKeyRef = useRef(null)

  const [walletOverview, setWalletOverview] = useState(null)
  const [depositHistory, setDepositHistory] = useState([])
  const [withdrawals, setWithdrawals] = useState([])
  const [ledger, setLedger] = useState(null)

  // Admin-configurable prices (fetched from /api/branding; defaults as fallback).
  const [prices, setPrices] = useState({ subscription_price: 15 })
  useEffect(() => {
    api.get('/api/branding').then(({ data }) => { if (data?.prices) setPrices(p => ({ ...p, ...data.prices })) }).catch(() => {})
  }, [])

  const SUB_PRICE = prices.subscription_price
  const [buyingSub, setBuyingSub] = useState(false)
  const subActive = subscriptionActive()

  const loadWalletOverview = useCallback(async () => {
    try {
      const { data } = await api.get('/api/wallet/overview')
      setWalletOverview(data)
    } catch { setWalletOverview(null) }
  }, [])

  const handleBuySubscription = async () => {
    if ((user?.balance || 0) < SUB_PRICE) {
      showToast(t('shop.sub_insufficient', { price: SUB_PRICE.toFixed(2) }), 'error')
      return
    }
    const ok = await globalConfirm(t(subActive ? 'shop.sub_confirm_extend' : 'shop.sub_confirm', { price: SUB_PRICE.toFixed(2) }))
    if (!ok) return
    setBuyingSub(true)
    try {
      await api.post('/api/payments/subscription/purchase')
      // Refresh the canonical user so is_premium / premium_until / balance
      // update everywhere (incl. is_setup_complete so onboarding isn't retriggered).
      const { data: me } = await api.get('/api/auth/me')
      setUser(me)
      loadWalletOverview()
      addToast(t('shop.sub_activated'), { type: 'success', title: t('shop.sub_title') })
    } catch (err) {
      showToast(err.response?.data?.detail || t('shop.sub_failed'), 'error')
    } finally {
      setBuyingSub(false)
    }
  }

  const loadDepositHistory = async () => {
    try {
      const { data } = await api.get('/api/payments/nowpayments/deposits')
      setDepositHistory(data)
    } catch { setDepositHistory([]); showToast(t('common.load_failed'), 'error') }
  }

  const loadWithdrawals = async () => {
    try {
      const { data } = await api.get('/api/wallet/withdrawals')
      setWithdrawals(data)
    } catch { setWithdrawals([]); showToast(t('common.load_failed'), 'error') }
  }

  const loadLedger = async () => {
    try {
      const { data } = await api.get('/api/wallet/ledger', { params: { limit: 50 } })
      setLedger(data)
    } catch { setLedger([]); showToast(t('common.load_failed'), 'error') }
  }

  const cancelWithdrawal = async (wr) => {
    const ok = await globalConfirm(t('shop.cancel_withdrawal_confirm', { amount: wr.amount?.toFixed(2) }))
    if (!ok) return
    try {
      await api.delete(`/api/wallet/withdrawals/${wr.id}`)
      showToast(t('shop.withdrawal_cancelled'), 'success')
      loadWithdrawals()
      loadWalletOverview()
      loadLedger()
    } catch (err) {
      showToast(err.response?.data?.detail || t('shop.withdrawal_cancel_failed'), 'error')
    }
  }

  useEffect(() => {
    loadWalletOverview()
    loadDepositHistory()
    loadWithdrawals()
  }, [loadWalletOverview])

  useEffect(() => {
    if (view === 'withdraw') loadLedger()
  }, [view])

  // Load the admin-curated deposit coin list from the backend.
  useEffect(() => {
    let isActive = true
    ;(async () => {
      try {
        const { data } = await api.get('/api/payments/nowpayments/currencies')
        if (!isActive) return
        const list = (data || []).map(c => ({ ...c, color: coinColor(c.symbol) }))
        setCoins(list)
        setSelectedCoin(prev => prev || list[0] || null)
      } catch {
        if (isActive) setCoins([])
      } finally {
        if (isActive) setCoinsLoading(false)
      }
    })()
    return () => { isActive = false }
  }, [])

  useEffect(() => {
    if (!depositInfo?.pay_address) { setQrDataUrl(''); return }
    let isActive = true
    QRCode.toDataURL(depositInfo.pay_address, { width: 160, margin: 1 })
      .then(url => { if (isActive) setQrDataUrl(url) })
      .catch(() => { if (isActive) setQrDataUrl('') })
    return () => { isActive = false }
  }, [depositInfo?.pay_address])

  useEffect(() => {
    if (!depositInfo?.deposit_id) return
    let isActive = true
    const poll = async () => {
      try {
        const { data } = await api.get(`/api/payments/nowpayments/deposits/${depositInfo.deposit_id}`)
        if (!isActive) return
        setDepositInfo(prev => ({ ...prev, ...data }))
        if (data.is_credited && !balanceRefreshed) {
          const userRes = await api.get('/api/auth/me')
          setUser(userRes.data)
          setBalanceRefreshed(true)
          loadWalletOverview()
          loadDepositHistory()
        }
      } catch {}
    }
    poll()
    const timer = setInterval(poll, 10000)
    return () => { isActive = false; clearInterval(timer) }
  }, [depositInfo?.deposit_id, balanceRefreshed, setUser, loadWalletOverview])

  const handleCopy = () => {
    if (!depositInfo?.pay_address) return
    navigator.clipboard.writeText(depositInfo.pay_address)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleDeposit = async () => {
    if (!selectedCoin) {
      setDepositStatus({ status: 'error', message: t('shop.select_coin_first') })
      return
    }
    const value = parseFloat(amount)
    const minDeposit = Math.max(walletOverview?.min_deposit || 10, selectedCoin.min_usd || 0)
    if (!value || value < minDeposit) {
      setDepositStatus({ status: 'error', message: t('shop.min_deposit_error', { symbol: selectedCoin.symbol, min: minDeposit.toFixed(2) }) })
      return
    }
    setDepositStatus({ status: 'loading', message: '' })
    setDepositInfo(null)
    try {
      const { data } = await api.post('/api/payments/nowpayments/create', {
        amount: value,
        pay_currency: selectedCoin.currency
      })
      setDepositInfo(data)
      setDepositStatus({ status: 'success', message: t('shop.send_crypto_below') })
      loadDepositHistory()
    } catch (error) {
      const detail = error?.response?.data?.detail || t('shop.deposit_failed')
      setDepositStatus({ status: 'error', message: detail })
    }
  }

  const handleWithdraw = async () => {
    const value = parseFloat(withdrawAmount)
    if (!value || value <= 0) {
      setWithdrawStatus({ status: 'error', message: t('shop.enter_valid_amount') })
      return
    }
    setWithdrawStatus({ status: 'loading', message: '' })
    // Generate the idempotency key lazily so a retry of the same submission
    // reuses it (server returns the original withdrawal instead of double-paying).
    if (!withdrawIdemKeyRef.current) {
      withdrawIdemKeyRef.current =
        (typeof crypto !== 'undefined' && crypto.randomUUID)
          ? crypto.randomUUID()
          : `wd_${Date.now()}_${Math.random().toString(36).slice(2)}`
    }
    try {
      await api.post('/api/wallet/withdraw', {
        amount: value,
        address: withdrawAddress.trim(),
        pin: withdrawPin || undefined,
        idempotency_key: withdrawIdemKeyRef.current,
      })
      const userRes = await api.get('/api/auth/me')
      setUser(userRes.data)
      loadWalletOverview()
      setWithdrawStatus({ status: 'success', message: t('shop.withdraw_submitted') })
      setWithdrawAmount('')
      setWithdrawAddress('')
      setWithdrawPin('')
      withdrawIdemKeyRef.current = null  // next withdrawal gets a fresh key
      loadWithdrawals()
    } catch (error) {
      const detail = error?.response?.data?.detail || t('shop.withdraw_failed')
      setWithdrawStatus({ status: 'error', message: detail })
    }
  }

  const premiumUntil = user?.premium_until ? parseDate(user.premium_until) : null

  return (
    <div className="space-y-4">
      <PageHeading icon={WalletIcon} title={t('shop.title')} subtitle={t('shop.subtitle')} />

      {/* Balance Card */}
      <Card
        as={motion.div}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="overflow-hidden"
      >
        <div className="absolute top-0 right-0 w-32 h-32 bg-primary-500/20 blur-3xl rounded-full" />
        <div className="absolute bottom-0 left-0 w-24 h-24 bg-accent-purple/20 blur-3xl rounded-full" />
        <div className="relative">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2 text-dark-400">
              <WalletIcon size={18} />
              <span className="text-sm">{t('shop.available_balance')}</span>
            </div>
            {view !== 'deposit' && (
              <Button variant="primary" size="sm" icon={Plus} onClick={() => setView('deposit')}>{t('shop.deposit')}</Button>
            )}
          </div>
          <h2 className="font-display text-3xl font-bold font-mono mb-1">
            ${user?.balance?.toFixed(2) || '0.00'}
          </h2>
          {walletOverview?.xmr_price > 0 && (
            <p className="text-dark-400 text-sm font-mono">
              ~ {(walletOverview.xmr_equivalent || 0).toFixed(6)} XMR (1 XMR = ${(walletOverview.xmr_price || 0).toFixed(2)})
            </p>
          )}

          {walletOverview?.pending_withdrawal_amount > 0 && (
            <div className="mt-3 pt-3 border-t border-white/10">
              <div className="flex items-center justify-between">
                <span className="text-xs text-dark-400">{t('shop.pending_withdraw')}</span>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold font-mono text-orange-400">${walletOverview.pending_withdrawal_amount.toFixed(2)}</span>
                  <Tag tone="amber">{t('shop.awaiting')}</Tag>
                </div>
              </div>
              <p className="text-[10px] text-dark-500 mt-1">{t('shop.pending_withdraw_note')}</p>
            </div>
          )}
        </div>
      </Card>

      {/* Hub — category tiles */}
      {view === 'hub' && (
        <div className="grid grid-cols-2 gap-3">
          {[
            { key: 'deposit',      label: t('shop.deposit'),       hint: t('shop.tile_deposit_hint'),  Icon: ArrowDownToLine, accent: 'bg-green-500/15 text-green-400' },
            { key: 'withdraw',     label: t('shop.tile_withdraw'), hint: t('shop.tile_withdraw_hint'), Icon: ArrowUpFromLine, accent: 'bg-orange-500/15 text-orange-400' },
            { key: 'subscription', label: t('shop.sub_title'),     hint: subActive ? t('shop.sub_active_short') : `$${SUB_PRICE.toFixed(0)} / 30d`, Icon: Star, accent: 'bg-amber-500/15 text-amber-400' },
          ].map(({ key, label, hint, Icon, accent }) => (
            <button
              key={key}
              onClick={() => setView(key)}
              className="flex flex-col items-start gap-3 p-4 rounded-xl bg-dark-800/40 border border-primary-500/10 hover:border-primary-500/30 hover:bg-dark-800/70 active:scale-[0.98] transition-all text-left"
            >
              <div className={`w-11 h-11 rounded-xl flex items-center justify-center ${accent}`}>
                <Icon size={20} />
              </div>
              <div>
                <h3 className="font-semibold text-white text-sm">{label}</h3>
                <p className="text-[11px] text-dark-400 mt-0.5">{hint}</p>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Back to hub */}
      {view !== 'hub' && (
        <button
          onClick={() => setView('hub')}
          className="flex items-center gap-1.5 text-sm text-dark-400 hover:text-primary-400 transition-colors"
        >
          <ChevronLeft size={16} /> {t('shop.title')}
        </button>
      )}

      {/* ============ SUBSCRIPTION ============ */}
      {view === 'subscription' && (
        <div className="space-y-4">
          <SectionHeader>{t('shop.sub_title')}</SectionHeader>
          <Card className="p-5 space-y-4 !border-amber-500/25">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-amber-500/15 border border-amber-500/25 flex items-center justify-center shrink-0">
                <Star size={18} className="text-amber-400" />
              </div>
              <div className="min-w-0">
                <h3 className="font-semibold text-white flex items-center gap-2">
                  {t('shop.sub_title')}
                  {subActive && <Tag tone="green" icon={Check}>{t('shop.active')}</Tag>}
                </h3>
                <p className="text-xs text-dark-400 mt-0.5">{t('shop.sub_desc')}</p>
              </div>
            </div>

            {subActive && (
              <p className="text-xs text-green-400">
                {premiumUntil
                  ? t('shop.sub_until', { date: premiumUntil.toLocaleDateString(getDateLocale()) })
                  : t('shop.sub_lifetime')}
              </p>
            )}

            <ul className="text-sm text-dark-300 space-y-1.5 list-disc pl-5">
              <li>{t('shop.sub_perk_unlimited')}</li>
              <li>{t('shop.sub_perk_stack')}</li>
              <li>{t('shop.sub_perk_paywall_note')}</li>
            </ul>

            <div className="flex items-center justify-between pt-3 border-t border-primary-500/15">
              <span className="text-xl font-bold font-mono text-amber-300">${SUB_PRICE.toFixed(2)}<span className="text-xs text-dark-400 font-normal"> / 30d</span></span>
              <Button
                variant="primary"
                onClick={handleBuySubscription}
                disabled={buyingSub || (user?.balance || 0) < SUB_PRICE || (subActive && !user?.premium_until)}
              >
                {buyingSub
                  ? t('shop.processing')
                  : (user?.balance || 0) < SUB_PRICE
                    ? t('shop.insufficient_funds')
                    : subActive
                      ? (user?.premium_until ? t('shop.sub_extend') : t('shop.sub_lifetime_short'))
                      : t('shop.sub_buy')}
              </Button>
            </div>
            <p className="text-xs text-dark-500">{t('shop.your_balance')} <span className="font-mono text-dark-300">${(user?.balance || 0).toFixed(2)}</span></p>
          </Card>
        </div>
      )}

      {/* ============ DEPOSIT ============ */}
      {view === 'deposit' && (
        <>
          {/* Coin Selection */}
          {coinsLoading ? (
            <LoadingState />
          ) : coins.length === 0 ? (
            <EmptyState icon={AlertCircle}>{t('shop.deposits_unavailable')}</EmptyState>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              {coins.map(coin => (
                <Card
                  as="button"
                  key={coin.currency}
                  onClick={() => { setSelectedCoin(coin); setDepositInfo(null); setDepositStatus({ status: 'idle', message: '' }) }}
                  className={`text-left ${
                    selectedCoin?.currency === coin.currency
                      ? '!border-primary-500/60 ring-1 ring-primary-500/40 bg-primary-500/5'
                      : ''
                  }`}
                >
                  <div className={`w-10 h-10 rounded-full bg-gradient-to-br ${coin.color} flex items-center justify-center text-white text-lg font-bold mb-2`}>
                    {coin.symbol.charAt(0)}
                  </div>
                  <p className="font-semibold text-sm">{coin.symbol}</p>
                  <p className="text-xs text-dark-400">{coin.network}</p>
                </Card>
              ))}
            </div>
          )}

          {/* Amount Input */}
          <div className="space-y-2">
            <FormInput
              label={t('shop.amount_usd')}
              type="text"
              inputMode="decimal"
              autoComplete="off"
              value={amount}
              onChange={(e) => setAmount(sanitizeAmount(e.target.value))}
              onBlur={() => setAmount(formatAmount(amount))}
              placeholder="0.00"
            />

            {/* Quick Amounts */}
            <div className="flex gap-2">
              {[50, 100, 250, 500].map(amt => (
                <Button
                  key={amt}
                  variant="secondary"
                  size="sm"
                  className="flex-1"
                  onClick={() => {
                    const current = parseFloat(amount || '0')
                    setAmount(String(Number.isFinite(current) ? current + amt : amt))
                    setDepositStatus({ status: 'idle', message: '' })
                  }}
                >
                  ${amt}
                </Button>
              ))}
            </div>

            <Button
              variant="primary"
              size="lg"
              className="w-full"
              onClick={handleDeposit}
              disabled={depositStatus.status === 'loading' || !selectedCoin}
            >
              {depositStatus.status === 'loading' ? t('shop.creating') : selectedCoin ? t('shop.generate_address', { symbol: selectedCoin.symbol }) : t('shop.select_coin')}
            </Button>

            {depositStatus.message && (
              <p className={`text-sm ${depositStatus.status === 'error' ? 'text-red-400' : 'text-primary-400'}`}>
                {depositStatus.message}
              </p>
            )}
          </div>

          {/* Deposit Address Display */}
          {depositInfo && (
            <Card as={motion.div} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-semibold">{t('shop.deposit_address')}</h3>
                  <p className="text-xs text-dark-400">{selectedCoin.network}</p>
                </div>
                {depositInfo.payment_status && (
                  <StatusBadge status={depositInfo.payment_status} />
                )}
              </div>

              {/* QR Code */}
              <div className="flex justify-center py-2">
                <div className="w-28 h-28 bg-white rounded-xl p-2">
                  {qrDataUrl ? (
                    <img src={qrDataUrl} alt="QR" className="w-full h-full rounded-lg" />
                  ) : (
                    <div className="w-full h-full bg-gray-200 rounded-lg flex items-center justify-center">
                      <QrCode size={24} className="text-gray-400" />
                    </div>
                  )}
                </div>
              </div>

              {/* Address Copy */}
              <div className="flex items-center gap-2 p-3 bg-dark-950/60 rounded-lg border border-primary-500/15">
                <code className="flex-1 text-xs break-all text-dark-200 font-mono">
                  {depositInfo.pay_address}
                </code>
                <button onClick={handleCopy} className="p-2 hover:bg-dark-700 rounded-lg transition-colors flex-shrink-0">
                  {copied ? <Check size={18} className="text-primary-400" /> : <Copy size={18} className="text-dark-400" />}
                </button>
              </div>
              {copied && <p className="text-primary-400 text-xs text-center">{t('shop.address_copied')}</p>}

              {/* Warning */}
              <div className="flex gap-2 p-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
                <AlertCircle size={18} className="text-yellow-500 flex-shrink-0" />
                <div className="text-xs">
                  <p className="text-yellow-400 font-medium">{t('shop.important')}</p>
                  <p className="text-dark-400">{t('shop.send_exactly', { amount: depositInfo.pay_amount, currency: depositInfo.pay_currency?.toUpperCase() })}</p>
                </div>
              </div>

              {depositInfo.is_credited && (
                <p className="text-xs text-primary-400 text-center">{t('shop.balance_credited')}</p>
              )}
            </Card>
          )}

          {/* Deposit Info Card */}
          <Card className="!p-3 space-y-2">
            <div className="flex justify-between text-xs">
              <span className="text-dark-400">{t('shop.min_deposit')}</span>
              <span className="font-mono">${Math.max(walletOverview?.min_deposit || 10, selectedCoin?.min_usd || 0).toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-dark-400">{t('shop.network')}</span>
              <span>{selectedCoin?.network || '-'}</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-dark-400">{t('shop.estimated_time')}</span>
              <span>{t('shop.eta_min', { n: selectedCoin?.currency === 'btc' ? 30 : selectedCoin?.currency === 'xmr' ? 20 : 5 })}</span>
            </div>
          </Card>

          {/* Deposit History */}
          <Card className="space-y-3">
            <SectionHeader right={<Button variant="ghost" size="xs" onClick={loadDepositHistory}>{t('common.refresh')}</Button>}>
              {t('shop.deposit_history')}
            </SectionHeader>
            {depositHistory.length === 0 ? (
              <EmptyState>{t('shop.no_deposits')}</EmptyState>
            ) : (
              <div className="space-y-2">
                {depositHistory.map(dep => (
                  <div key={dep.deposit_id} className="flex items-center justify-between gap-2 p-2.5 rounded-lg bg-dark-950/40 border border-primary-500/10">
                    <div>
                      <p className="text-xs font-medium font-mono">
                        ${dep.price_amount_usd?.toFixed(2)} - {dep.pay_currency?.toUpperCase() || '-'}
                      </p>
                      <p className="text-[11px] text-dark-400">{formatDate(dep.created_at, { time: true })}</p>
                    </div>
                    <div className="text-right">
                      <StatusBadge status={dep.payment_status} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </>
      )}

      {/* ============ WITHDRAW ============ */}
      {view === 'withdraw' && (
        <>
          <Card className="space-y-3">
            <FormInput
              label={t('shop.amount_usd')}
              type="number"
              value={withdrawAmount}
              onChange={(e) => { setWithdrawAmount(e.target.value); withdrawIdemKeyRef.current = null }}
              placeholder="0.00"
            />

            {/* XMR Equivalent */}
            {withdrawAmount && parseFloat(withdrawAmount) > 0 && walletOverview?.xmr_price > 0 && (
              <div className="p-2.5 bg-dark-950/60 rounded-lg space-y-1.5 border border-primary-500/15">
                <div className="flex justify-between text-xs">
                  <span className="text-dark-400">{t('shop.xmr_price')}</span>
                  <span className="font-mono">${walletOverview.xmr_price.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-dark-400">{t('shop.youll_receive')}</span>
                  <span className="text-primary-400 font-medium font-mono">
                    ~ {(parseFloat(withdrawAmount) / walletOverview.xmr_price).toFixed(6)} XMR
                  </span>
                </div>
                {walletOverview.withdrawal_fee_percent > 0 && (
                  <div className="flex justify-between text-xs">
                    <span className="text-dark-400">{t('shop.fee_pct', { pct: walletOverview.withdrawal_fee_percent })}</span>
                    <span className="text-red-400 font-mono">
                      -${((parseFloat(withdrawAmount) * walletOverview.withdrawal_fee_percent) / 100).toFixed(2)}
                    </span>
                  </div>
                )}
              </div>
            )}

            <div>
              <FormInput
                label={t('shop.xmr_address')}
                value={withdrawAddress}
                onChange={(e) => { setWithdrawAddress(e.target.value); withdrawIdemKeyRef.current = null }}
                placeholder="4..."
                maxLength={106}
              />
              <p className="text-[10px] text-dark-500 mt-1">{t('shop.xmr_address_hint')}</p>
            </div>

            <div>
              <FormInput
                label={t('shop.password_if_set')}
                type="password"
                value={withdrawPin}
                onChange={(e) => setWithdrawPin(e.target.value)}
                placeholder={t('shop.password_placeholder')}
              />
              <p className="text-[10px] text-dark-500 mt-1">{t('shop.password_hint')}</p>
            </div>

            <Button
              variant="primary"
              size="lg"
              className="w-full"
              onClick={handleWithdraw}
              disabled={withdrawStatus.status === 'loading'}
            >
              {withdrawStatus.status === 'loading' ? t('shop.submitting') : t('shop.request_withdrawal')}
            </Button>

            {withdrawStatus.message && (
              <p className={`text-sm ${withdrawStatus.status === 'error' ? 'text-red-400' : 'text-primary-400'}`}>
                {withdrawStatus.message}
              </p>
            )}

            <div className="flex gap-2 p-2.5 bg-dark-950/60 rounded-lg border border-primary-500/15">
              <AlertCircle size={14} className="text-dark-400 flex-shrink-0 mt-0.5" />
              <div className="text-[11px] text-dark-400">
                <p>{t('shop.withdraw_note_pre')} <span className="text-white font-medium">XMR</span> {t('shop.withdraw_note_post')}</p>
                <p className="mt-0.5">{t('shop.minimum')} <span className="text-white">${(walletOverview?.min_withdrawal || 10).toFixed(2)}</span>{walletOverview?.withdrawal_fee_percent > 0 ? ` - ${t('shop.fee_label', { pct: walletOverview.withdrawal_fee_percent })}` : ''}</p>
              </div>
            </div>
          </Card>

          {/* Withdrawal History */}
          <Card className="space-y-3">
            <SectionHeader right={<Button variant="ghost" size="xs" onClick={loadWithdrawals}>{t('common.refresh')}</Button>}>
              {t('shop.withdrawal_history')}
            </SectionHeader>
            {withdrawals.length === 0 ? (
              <EmptyState>{t('shop.no_withdrawals')}</EmptyState>
            ) : (
              <div className="space-y-2">
                {withdrawals.map(wr => (
                  <div key={wr.id} className="p-3 rounded-lg bg-dark-950/40 border border-primary-500/10 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-xs font-medium font-mono">${wr.amount?.toFixed(2)}</p>
                        {(wr.fee_amount > 0) && (
                          <p className="text-[10px] text-dark-500 font-mono">{t('shop.fee_net', { fee: wr.fee_amount?.toFixed(2), net: wr.net_amount?.toFixed(2) })}</p>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <StatusBadge status={wr.status} />
                        {String(wr.status).toLowerCase() === 'pending' && (
                          <Button variant="ghost" size="xs" onClick={() => cancelWithdrawal(wr)}>{t('common.cancel')}</Button>
                        )}
                      </div>
                    </div>
                    <p className="text-[11px] text-dark-400 font-mono truncate">{wr.destination || '-'}</p>
                    <p className="text-[11px] text-dark-500">{formatDate(wr.created_at, { time: true })}</p>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Transaction History (append-only balance ledger) */}
          <Card className="space-y-3">
            <SectionHeader right={<Button variant="ghost" size="xs" onClick={loadLedger}>{t('common.refresh')}</Button>}>
              {t('shop.transaction_history')}
            </SectionHeader>
            {ledger === null ? (
              <LoadingState label={t('shop.loading_transactions')} />
            ) : ledger.length === 0 ? (
              <EmptyState>{t('shop.no_transactions')}</EmptyState>
            ) : (
              <div className="space-y-1.5 max-h-96 overflow-y-auto">
                {ledger.map(e => (
                  <div key={e.id} className="flex items-center justify-between gap-3 p-2.5 rounded-lg bg-dark-950/40 border border-primary-500/10">
                    <div className="min-w-0">
                      <p className="text-xs font-medium truncate">
                        {e.description || e.entry_type?.replace(/_/g, ' ')}
                      </p>
                      <p className="text-[10px] text-dark-500">{formatDate(e.created_at, { time: true })}</p>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className={`text-xs font-mono font-semibold ${e.amount >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {e.amount >= 0 ? '+' : ''}{Number(e.amount).toFixed(2)}
                      </p>
                      <p className="text-[10px] text-dark-500 font-mono">{t('shop.bal_after', { bal: Number(e.balance_after).toFixed(2) })}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  )
}
