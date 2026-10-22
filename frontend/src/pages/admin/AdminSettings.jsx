import { useState, useEffect } from 'react'
import api from '../../lib/api'
import { useBrandingStore } from '../../store/brandingStore'
import { Card, SectionHeader, Button, FormInput, Toggle, LoadingState } from '../../components/admin/ui'

export default function AdminSettings({ showToast }) {
  const [settings, setSettings] = useState(null)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const [availableCoins, setAvailableCoins] = useState(null)
  const [coinsFallback, setCoinsFallback] = useState(false)

  const load = async () => {
    try {
      const res = await api.get('/api/admin/settings')
      const s = res.data || {}
      // Live NOWPayments coin list for the deposit-coin toggles.
      const coinRes = await api.get('/api/admin/payment-coins').catch(() => null)
      if (coinRes) {
        const list = coinRes.data?.coins || []
        setAvailableCoins(list)
        setCoinsFallback(!!coinRes.data?.fallback)
        // Seed the curated CSV from currently-enabled coins if never set, so the
        // toggles reflect the live state and a save persists an explicit list.
        if (s.enabled_deposit_coins == null) {
          s.enabled_deposit_coins = list.filter(c => c.enabled).map(c => c.currency).join(',')
        }
      } else {
        setAvailableCoins([])
      }
      setSettings(s)
      setLoadError(false)
    } catch (err) {
      console.error(err)
      setLoadError(true)
      setSettings({})
    }
  }

  useEffect(() => { load() }, [])

  const save = async () => {
    setSaving(true)
    try {
      await api.put('/api/admin/settings', settings)
      useBrandingStore.getState().load()
      showToast('Settings saved', 'success')
    } catch (err) { showToast(err.response?.data?.detail || 'Failed', 'error') }
    finally { setSaving(false) }
  }

  const set = (key, value) => setSettings(prev => ({ ...prev, [key]: value }))

  const selectedCoins = (settings?.enabled_deposit_coins || '').split(',').map(s => s.trim()).filter(Boolean)
  const toggleCoin = (currency) => {
    const next = new Set(selectedCoins)
    if (next.has(currency)) next.delete(currency)
    else next.add(currency)
    set('enabled_deposit_coins', Array.from(next).join(','))
  }

  if (!settings) return <LoadingState label="loading settings" />
  if (loadError) return (
    <div className="p-6 text-center">
      <p className="text-red-400 mb-3">Failed to load settings</p>
      <Button variant="secondary" onClick={load}>Retry</Button>
    </div>
  )

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Branding */}
      <Card>
        <SectionHeader>BRANDING</SectionHeader>
        <div className="space-y-3">
          <FormInput label="App Name" type="text" value={settings.app_name || ''} onChange={e => set('app_name', e.target.value)} />
          <FormInput label="Bot Username" type="text" value={settings.bot_username || ''} onChange={e => set('bot_username', e.target.value)} placeholder="ForumMarketBot" />
          <FormInput label="Logo URL" type="text" value={settings.logo_url || ''} onChange={e => set('logo_url', e.target.value)} />
          <Toggle checked={settings.show_logo !== false} onChange={e => set('show_logo', e.target.checked)} label="Show Logo" />
        </div>
      </Card>

      {/* Links */}
      <Card>
        <SectionHeader>EXTERNAL LINKS</SectionHeader>
        <div className="space-y-3">
          <FormInput label="Announcements URL" type="text" value={settings.announcements_url || ''} onChange={e => set('announcements_url', e.target.value)} placeholder="https://t.me/..." />
          <FormInput label="Official Group URL" type="text" value={settings.official_group_url || ''} onChange={e => set('official_group_url', e.target.value)} placeholder="https://t.me/..." />
          <FormInput label="Support Username" type="text" value={settings.support_username || ''} onChange={e => set('support_username', e.target.value)} />
        </div>
      </Card>

      {/* Forum Settings */}
      <Card>
        <SectionHeader>FORUM LIMITS</SectionHeader>
        <div className="grid grid-cols-2 gap-3">
          <FormInput label="Min Posts for DM" type="number" value={settings.min_posts_for_dm || 5} onChange={e => set('min_posts_for_dm', parseInt(e.target.value) || 0)} />
          <FormInput label="Max Posts/Hour" type="number" value={settings.max_posts_per_hour || 30} onChange={e => set('max_posts_per_hour', parseInt(e.target.value) || 0)} />
          <FormInput label="Max Threads/Day" type="number" value={settings.max_threads_per_day || 10} onChange={e => set('max_threads_per_day', parseInt(e.target.value) || 0)} />
          <FormInput label="Max PM/Minute" type="number" value={settings.max_pm_per_minute || 1} onChange={e => set('max_pm_per_minute', parseInt(e.target.value) || 0)} />
        </div>
      </Card>

      {/* Referral & Fees */}
      <Card>
        <SectionHeader>REFERRALS &amp; FEES</SectionHeader>
        <div className="grid grid-cols-2 gap-3">
          <FormInput label="L1 Commission %" type="number" step="0.1" value={settings.referral_level1_percent || 3} onChange={e => set('referral_level1_percent', parseFloat(e.target.value) || 0)} />
          <FormInput label="L2 Commission %" type="number" step="0.1" value={settings.referral_level2_percent || 5} onChange={e => set('referral_level2_percent', parseFloat(e.target.value) || 0)} />
          <FormInput label="Withdrawal Fee %" type="number" step="0.1" value={settings.withdrawal_fee_percent || 0} onChange={e => set('withdrawal_fee_percent', parseFloat(e.target.value) || 0)} />
          <FormInput label="Escrow Fee %" type="number" step="0.1" value={settings.escrow_fee_percent || 0} onChange={e => set('escrow_fee_percent', parseFloat(e.target.value) || 0)} />
        </div>
        <Toggle className="mt-3" checked={settings.referral_enabled !== false} onChange={e => set('referral_enabled', e.target.checked)} label="Referral System Enabled" />
      </Card>

      {/* Registration / Trial */}
      <Card>
        <SectionHeader>REGISTRATION</SectionHeader>
        <Toggle
          checked={settings.trial_mode_enabled !== false}
          onChange={e => set('trial_mode_enabled', e.target.checked)}
          label="Trial mode — new users start as Trial (turn off to give the User role immediately)"
        />
        <p className="text-xs text-dark-400 mt-2">
          Trial has no time limit — users are upgraded by purchasing Premium or manually by an admin after earning +rep.
        </p>
      </Card>

      {/* Shop Prices */}
      <Card>
        <SectionHeader>SHOP PRICES ($)</SectionHeader>
        <div className="grid grid-cols-2 gap-3">
          <FormInput label="Premium" type="number" step="0.01" value={settings.premium_price ?? 80} onChange={e => set('premium_price', parseFloat(e.target.value) || 0)} />
          <FormInput label="Display Name Change" type="number" step="0.01" value={settings.name_change_price ?? 20} onChange={e => set('name_change_price', parseFloat(e.target.value) || 0)} />
          <FormInput label="Thread Title Style" type="number" step="0.01" value={settings.thread_title_price ?? 20} onChange={e => set('thread_title_price', parseFloat(e.target.value) || 0)} />
          <FormInput label="Thread Auto-bump" type="number" step="0.01" value={settings.thread_autobump_price ?? 60} onChange={e => set('thread_autobump_price', parseFloat(e.target.value) || 0)} />
        </div>
      </Card>

      {/* Deposit Coins */}
      <Card>
        <SectionHeader>DEPOSIT COINS</SectionHeader>
        {coinsFallback && (
          <p className="text-xs text-amber-400 mb-2">
            Live coin list unavailable — showing defaults. Check NOWPAYMENTS_API_KEY / account coin selection.
          </p>
        )}
        {availableCoins === null ? (
          <LoadingState label="loading coins" />
        ) : availableCoins.length === 0 ? (
          <p className="text-xs text-dark-400">No coins available from NOWPayments.</p>
        ) : (
          <>
            <p className="text-xs text-dark-400 mb-3">
              Pick which coins users can deposit with. Each coin still respects its NOWPayments network minimum.
            </p>
            <div className="grid grid-cols-2 gap-2 max-h-72 overflow-y-auto">
              {availableCoins.map(c => (
                <Toggle
                  key={c.currency}
                  checked={selectedCoins.includes(c.currency)}
                  onChange={() => toggleCoin(c.currency)}
                  label={`${c.symbol} · ${c.network}`}
                />
              ))}
            </div>
            <p className="text-xs text-dark-400 mt-3">{selectedCoins.length} coin(s) enabled for deposits.</p>
          </>
        )}
      </Card>

      {/* Maintenance */}
      <Card>
        <SectionHeader>SYSTEM</SectionHeader>
        <Toggle checked={settings.maintenance_mode || false} onChange={e => set('maintenance_mode', e.target.checked)} label="Maintenance Mode" />
      </Card>

      <Button variant="primary" size="lg" className="w-full" onClick={save} disabled={saving}>
        {saving ? 'Saving...' : 'Save Settings'}
      </Button>
    </div>
  )
}
