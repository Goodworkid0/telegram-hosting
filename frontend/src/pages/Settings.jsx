import { useState, useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  User, Shield, Moon, Camera, Save, ArrowLeft, Bell, Palette, Settings as SettingsIcon, LogOut, Star
} from 'lucide-react'
import { useAuthStore } from '../store/authStore'
import { globalConfirm } from '../components/ConfirmModal'
import api from '../lib/api'
import { useToast } from '../components/Toast'
import { Card, SectionHeader, PageHeading, Button, Toggle, FormInput, FormSelect, tabClass } from '../components/ui'
import { roleStyle } from '../components/admin/ui'
import { useT, getDateLocale } from '../lib/i18n'
import { parseDate } from '../lib/utils'

export default function Settings() {
  const t = useT()
  const { user, setUser, logout } = useAuthStore()
  const { showToast } = useToast()
  const navigate = useNavigate()
  // Backend sends roles uppercase ('ADMIN'); normalize for display/compare
  const role = String(user?.role || 'user').toLowerCase()
  // Handle visibility is chosen at setup; changing it later is premium/staff-only
  // (mirrors the backend guard in PUT /api/auth/profile).
  const canToggleHandle = user?.is_premium || role === 'admin' || role === 'moderator'

  const [pwCurrent, setPwCurrent] = useState('')
  const [pwNew, setPwNew] = useState('')
  const [pwConfirm, setPwConfirm] = useState('')
  const [pwSaving, setPwSaving] = useState(false)

  const handleChangePassword = async () => {
    if (pwNew !== pwConfirm) {
      showToast(t('settings.pw_mismatch'), 'error')
      return
    }
    setPwSaving(true)
    try {
      const { data } = await api.put('/api/auth/password', {
        current_password: pwCurrent,
        new_password: pwNew,
      })
      // The backend rotates all sessions; adopt the fresh token pair so this
      // session stays signed in.
      if (data.access_token) {
        localStorage.setItem('token', data.access_token)
        if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token)
        api.defaults.headers.common['Authorization'] = `Bearer ${data.access_token}`
        useAuthStore.setState({ token: data.access_token })
      }
      setPwCurrent('')
      setPwNew('')
      setPwConfirm('')
      showToast(t('settings.pw_changed'), 'success')
    } catch (err) {
      showToast(err.response?.data?.detail || t('settings.pw_change_failed'), 'error')
    } finally {
      setPwSaving(false)
    }
  }
  const fileInputRef = useRef(null)
  const notifSaveRef = useRef(null)

  const [activeTab, setActiveTab] = useState('profile')
  const [loading, setLoading] = useState(false)
  const [avatarUploading, setAvatarUploading] = useState(false)
  const [bannerUploading, setBannerUploading] = useState(false)
  const bannerInputRef = useRef(null)
  
  const [notifPrefs, setNotifPrefs] = useState({
    reputation: true,
    followers: true,
  })
  const [notifSaving, setNotifSaving] = useState(false)

  useEffect(() => {
    if (user?.notification_preferences) {
      try {
        const prefs = typeof user.notification_preferences === 'string' ? JSON.parse(user.notification_preferences) : user.notification_preferences
        setNotifPrefs(prev => ({ ...prev, ...prefs }))
      } catch { showToast(t('common.load_failed'), 'error') }
    }
  }, [user])
  
  // Profile form (display-name changes go through the paid Shop flow)
  const [profileForm, setProfileForm] = useState({
    profile_bio: '',
    show_telegram: true,
  })
  const [profileTheme, setProfileTheme] = useState({
    avatar_border: '#6366f1',
    name_color: '',
    avatar_glow: false,
  })
  
  // Load user data into form
  useEffect(() => {
    if (user) {
      setProfileForm({
        profile_bio: user.profile_bio || '',
        show_telegram: user.show_telegram !== false,
      })
      try {
        const theme = typeof user.profile_theme === 'string' ? JSON.parse(user.profile_theme) : (user.profile_theme || {})
        setProfileTheme({
          avatar_border: theme.avatar_border || '#6366f1',
          name_color: theme.name_color || '',
          avatar_glow: theme.avatar_glow || false,
        })
      } catch { showToast(t('common.load_failed'), 'error') }
    }
  }, [user])

  const handleProfileChange = (e) => {
    const { name, value } = e.target
    setProfileForm(prev => ({ ...prev, [name]: value }))
  }

  const handleSaveProfile = async () => {
    setLoading(true)
    try {
      const payload = { ...profileForm }
      if (user?.is_premium) {
        payload.profile_theme = JSON.stringify(profileTheme)
      }
      const { data } = await api.put('/api/auth/profile', payload)
      setUser(data)
      showToast(t('settings.profile_updated'), 'success')
    } catch (err) {
      const msg = err.response?.data?.detail || t('settings.profile_save_failed')
      showToast(msg, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleAvatarClick = () => {
    fileInputRef.current?.click()
  }

  const handleAvatarUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    
    // Validate file
    if (!file.type.startsWith('image/')) {
      showToast(t('settings.select_image'), 'error')
      return
    }
    if (file.size > 5 * 1024 * 1024) {
      showToast(t('settings.image_too_large'), 'error')
      return
    }
    
    setAvatarUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const { data } = await api.post('/api/users/me/avatar', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setUser(data)
      if (fileInputRef.current) fileInputRef.current.value = ''
      showToast(t('settings.avatar_updated'), 'success')
    } catch (err) {
      showToast(t('settings.avatar_upload_failed'), 'error')
    } finally {
      setAvatarUploading(false)
    }
  }

  const handleBannerUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.type.startsWith('image/')) { showToast(t('settings.select_image'), 'error'); return }
    if (file.size > 5 * 1024 * 1024) { showToast(t('settings.image_too_large'), 'error'); return }
    setBannerUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const { data } = await api.post('/api/users/me/banner', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setUser(data)
      if (bannerInputRef.current) bannerInputRef.current.value = ''
      showToast(t('settings.banner_updated'), 'success')
    } catch (err) {
      showToast(t('settings.banner_upload_failed'), 'error')
    } finally {
      setBannerUploading(false)
    }
  }

  const handleLogout = async () => {
    if (!(await globalConfirm(t('settings.logout_confirm')))) return
    logout()
    navigate('/')
  }

  const handleNotifToggle = async (key) => {
    const previous = notifPrefs[key]
    const updated = { ...notifPrefs, [key]: !previous }
    setNotifPrefs(updated)
    setNotifSaving(true)
    try {
      if (notifSaveRef.current) notifSaveRef.current.abort?.()
      const controller = new AbortController()
      notifSaveRef.current = controller
      const { data } = await api.put('/api/auth/profile', { notification_preferences: updated }, {
        signal: controller.signal
      })
      setUser(data)
      showToast(t('settings.saved'), 'success')
    } catch (err) {
      if (err?.name !== 'CanceledError') {
        setNotifPrefs(prev => ({ ...prev, [key]: previous }))
        showToast(t('settings.prefs_save_failed'), 'error')
      }
    } finally {
      setNotifSaving(false)
    }
  }

  const tabs = [
    { id: 'profile', label: t('settings.tab_profile'), icon: User },
    { id: 'notifications', label: t('settings.tab_notifications'), icon: Bell },
    { id: 'security', label: t('settings.tab_security'), icon: Shield },
    { id: 'appearance', label: t('settings.tab_appearance'), icon: Moon },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link to={`/profile/${user?.id}`} className="p-2 rounded-lg bg-dark-800 hover:bg-dark-700 transition-colors">
          <ArrowLeft size={20} />
        </Link>
        <PageHeading icon={SettingsIcon} title={t('settings.title')} subtitle={t('settings.subtitle')} />
      </div>

      {/* Profile Card */}
      <Card className="!p-0 overflow-hidden">
        {/* Banner */}
        <div 
          onClick={() => bannerInputRef.current?.click()}
          className="h-24 bg-dark-700 relative cursor-pointer group overflow-hidden"
        >
          {bannerUploading ? (
            <div className="absolute inset-0 flex items-center justify-center bg-dark-800/50">
              <div className="w-6 h-6 border-2 border-primary-400 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : user?.profile_banner_url ? (
            <>
              <img src={user.profile_banner_url} alt="" className="w-full h-full object-cover" />
              <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                <Camera size={20} className="text-white" />
                <span className="text-white text-xs ml-2">{t('settings.change_banner')}</span>
              </div>
            </>
          ) : (
            <div className="absolute inset-0 flex items-center justify-center">
              <Camera size={16} className="text-dark-400" />
              <span className="text-dark-400 text-xs ml-1">{t('settings.add_banner')}</span>
              <div className="absolute inset-0 bg-white/5 opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
          )}
          <input ref={bannerInputRef} type="file" accept="image/*" onChange={handleBannerUpload} className="hidden" />
        </div>

        <div className="p-6">
        <div className="flex items-center gap-4">
          {/* Avatar */}
          <div className="relative">
            <div 
              onClick={handleAvatarClick}
              className="w-20 h-20 rounded-xl bg-dark-700 flex items-center justify-center overflow-hidden cursor-pointer group"
            >
              {avatarUploading ? (
                <div className="w-6 h-6 border-2 border-primary-400 border-t-transparent rounded-full animate-spin" />
              ) : user?.avatar_url ? (
                <>
                  <img src={user.avatar_url} alt="" className="w-full h-full object-cover" />
                  <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                    <Camera size={20} className="text-white" />
                  </div>
                </>
              ) : (
                <span className="text-2xl font-bold text-dark-400">
                  {user?.username?.[0]?.toUpperCase() || 'U'}
                </span>
              )}
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleAvatarUpload}
              className="hidden"
            />
          </div>
          
          {/* Info */}
          <div className="flex-1">
            <h2 className="font-semibold text-lg">@{user?.username || 'guest'}</h2>
            <p className="text-dark-400 text-sm">{user?.first_name || t('settings.no_name')}</p>
            <div className="flex items-center gap-2 mt-1">
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                role === 'admin' ? 'bg-red-500/20 text-red-400' :
                role === 'moderator' ? 'bg-blue-500/20 text-blue-400' :
                role === 'trial' ? 'bg-yellow-500/20 text-yellow-400' :
                'bg-green-500/20 text-green-400'
              }`}>
                {role}
              </span>
            </div>
          </div>
        </div>
        </div>
      </Card>

      {/* Tabs */}
      <div className="flex gap-1 bg-dark-800/50 rounded-xl p-1 border border-dark-700/50">
        {tabs.map(tab => {
          const Icon = tab.icon
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 flex items-center justify-center gap-2 ${tabClass(activeTab === tab.id)}`}
            >
              <Icon size={16} />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Tab Content */}
      <motion.div
        key={activeTab}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="space-y-4"
      >
        {/* Profile Tab */}
        {activeTab === 'profile' && (
          <Card>
            <SectionHeader>{t('settings.account')}</SectionHeader>
            <div className="space-y-4">
              {/* Username (read-only — use paid endpoint to change) */}
              <div>
                <label className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-primary-400/70">{t('settings.username')}</label>
                <div className="w-full bg-dark-950/60 border border-primary-500/15 rounded-lg px-3 py-2.5 text-sm text-white font-mono">
                  @{user?.username || 'guest'}
                </div>
                <p className="text-xs text-dark-400 mt-1">{t('settings.username_note')}</p>
              </div>

              {/* Display Name (read-only — change is a paid Shop item) */}
              <div>
                <label className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-primary-400/70">{t('settings.display_name')}</label>
                <div className="flex items-center justify-between gap-3 rounded-lg border border-primary-500/15 bg-dark-950/40 px-3 py-2.5">
                  <span className="text-sm text-white truncate">{user?.first_name || '—'}</span>
                </div>
              </div>

              {/* Bio */}
              <div>
                <label className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-primary-400/70">{t('settings.bio')}</label>
                <textarea
                  name="profile_bio"
                  value={profileForm.profile_bio}
                  onChange={handleProfileChange}
                  rows={3}
                  className="w-full bg-dark-950/60 border border-primary-500/15 rounded-lg px-3 py-2.5 text-sm text-white font-mono placeholder:text-dark-500 focus:border-primary-500/50 focus:outline-none focus:shadow-[0_0_0_1px_rgba(0,200,230,0.35)] transition-all resize-none"
                  placeholder={t('settings.bio_placeholder')}
                  maxLength={500}
                />
                <p className="text-xs text-dark-400 mt-1">{t('settings.chars_count', { n: profileForm.profile_bio.length, max: 500 })}</p>
              </div>

              {/* Show Telegram Handle — set once at onboarding; changing it later is a premium perk */}
              <div className="flex items-center justify-between gap-4">
                <div>
                  <h3 className="font-semibold text-sm">{t('settings.show_telegram')}</h3>
                  <p className="text-xs text-dark-400">
                    {canToggleHandle ? t('settings.show_telegram_desc') : t('settings.show_telegram_premium')}
                  </p>
                </div>
                <Toggle
                  checked={profileForm.show_telegram}
                  onChange={() => {
                    if (!canToggleHandle) return
                    const next = !profileForm.show_telegram
                    setProfileForm(prev => ({ ...prev, show_telegram: next }))
                  }}
                  className={canToggleHandle ? '' : 'opacity-40 pointer-events-none'}
                />
              </div>

              {/* Save Button */}
              <Button
                variant="primary"
                onClick={handleSaveProfile}
                disabled={loading}
                icon={loading ? undefined : Save}
                className="w-full"
              >
                {loading ? (
                  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  t('settings.save_changes')
                )}
              </Button>
            </div>
          </Card>
        )}

        {/* Notifications Tab */}
        {activeTab === 'notifications' && (
          <Card>
            <SectionHeader
              right={notifSaving && (
                <div className="flex items-center gap-2 text-dark-400 text-xs">
                  <div className="w-3 h-3 border border-primary-400 border-t-transparent rounded-full animate-spin" />
                  {t('common.saving')}
                </div>
              )}
            >
              {t('settings.notifications')}
            </SectionHeader>
            <p className="text-dark-400 text-sm mb-4">{t('settings.notifications_desc')}</p>
            <div className="divide-y divide-dark-700/50">
              {[
                { key: 'reputation', label: t('settings.notif_reputation'), desc: t('settings.notif_reputation_desc') },
                { key: 'followers', label: t('settings.notif_followers'), desc: t('settings.notif_followers_desc') },
              ].map(item => (
                <div key={item.key} className="py-4 first:pt-0 last:pb-0 flex items-center justify-between">
                  <div className="flex-1 mr-4">
                    <h3 className="font-semibold text-sm">{item.label}</h3>
                    <p className="text-xs text-dark-400">{item.desc}</p>
                  </div>
                  <Toggle
                    checked={notifPrefs[item.key]}
                    onChange={() => handleNotifToggle(item.key)}
                    className={`flex-shrink-0 ${notifSaving ? 'opacity-50 pointer-events-none' : ''}`}
                  />
                </div>
              ))}
            </div>
          </Card>
        )}

        {/* Security Tab */}
        {activeTab === 'security' && (
          <Card>
            <SectionHeader>{t('settings.security')}</SectionHeader>
            <div className="divide-y divide-dark-700/50">
              <div className="pb-4">
                <h3 className="font-semibold mb-1">{t('settings.telegram_account')}</h3>
                <p className="text-sm text-dark-400">{t('settings.telegram_linked')} <span className="text-white">{user?.telegram_id}</span></p>
              </div>

              <div className="py-4">
                <h3 className="font-semibold mb-1">{t('settings.account_created')}</h3>
                <p className="text-sm text-dark-400">
                  {user?.created_at ? parseDate(user.created_at).toLocaleDateString(getDateLocale(), {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric'
                  }) : t('settings.unknown')}
                </p>
              </div>

              <div className="py-4 space-y-3">
                <h3 className="font-semibold">{t('settings.change_password')}</h3>
                <p className="text-xs text-dark-400">
                  {t('settings.password_rules')}
                </p>
                <FormInput
                  label={t('settings.current_password')} type="password" autoComplete="current-password"
                  value={pwCurrent} onChange={e => setPwCurrent(e.target.value)}
                />
                <FormInput
                  label={t('settings.new_password')} type="password" autoComplete="new-password"
                  value={pwNew} onChange={e => setPwNew(e.target.value)}
                />
                <FormInput
                  label={t('settings.confirm_new_password')} type="password" autoComplete="new-password"
                  value={pwConfirm} onChange={e => setPwConfirm(e.target.value)}
                />
                <Button
                  variant="secondary" className="w-full"
                  onClick={handleChangePassword}
                  disabled={pwSaving || !pwCurrent || pwNew.length < 6 || !pwConfirm}
                >
                  {pwSaving ? t('settings.changing') : t('settings.change_password')}
                </Button>
              </div>

              <div className="pt-4">
                <Button variant="danger" onClick={handleLogout} icon={LogOut} className="w-full">
                  {t('settings.log_out')}
                </Button>
              </div>
            </div>
          </Card>
        )}

        {/* Appearance Tab */}
        {activeTab === 'appearance' && (
          <Card>
            <SectionHeader>{t('settings.appearance')}</SectionHeader>
            <div className="divide-y divide-dark-700/50">
              {user?.is_premium ? (
                <div className="pb-4 space-y-4">
                  <div className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-4 space-y-2">
                    <div className="flex items-center gap-2">
                      <Star size={15} className="text-amber-400" />
                      <h3 className="font-semibold text-amber-200 text-sm">{t('settings.premium_heading')}</h3>
                    </div>
                    <ul className="text-xs text-dark-300 space-y-1 list-disc pl-5">
                      <li><span className="text-white">{t('settings.premium_li1_title')}</span> — {t('settings.premium_li1_text')}</li>
                      <li><span className="text-white">{t('settings.premium_li2_title')}</span> — {t('settings.premium_li2_text_pre')} <span className="text-primary-300">{t('settings.tab_profile')}</span>{t('settings.premium_li2_text_post')}</li>
                      <li><span className="text-white">{t('settings.premium_li3_title')}</span> — {t('settings.premium_li3_text')}</li>
                      <li><span className="text-white">{t('settings.premium_li4_title')}</span> — {t('settings.premium_li4_text')}</li>
                    </ul>
                  </div>

                  <div className="flex items-center gap-2">
                    <Palette size={16} className="text-primary-400" />
                    <h3 className="font-semibold">{t('settings.avatar_name_custom')}</h3>
                    <span className="text-[10px] bg-primary-500/20 text-primary-400 px-2 py-0.5 rounded-full font-medium">{t('settings.premium_tag')}</span>
                  </div>
                  <p className="text-xs text-dark-400">{t('settings.customize_desc')}</p>

                  <div className="space-y-3">
                    <div>
                      <label className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-primary-400/70">{t('settings.avatar_border_color')}</label>
                      <div className="flex items-center gap-2">
                        <input type="color" value={profileTheme.avatar_border}
                          onChange={e => setProfileTheme(p => ({ ...p, avatar_border: e.target.value }))}
                          className="w-10 h-10 rounded-lg border border-dark-700 cursor-pointer bg-transparent" />
                        <FormInput type="text" value={profileTheme.avatar_border}
                          onChange={e => setProfileTheme(p => ({ ...p, avatar_border: e.target.value }))}
                          className="flex-1" />
                      </div>
                    </div>

                    <div>
                      <label className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-primary-400/70">{t('settings.name_color')}</label>
                      <div className="flex items-center gap-2">
                        <input type="color" value={profileTheme.name_color || '#ffffff'}
                          onChange={e => setProfileTheme(p => ({ ...p, name_color: e.target.value }))}
                          className="w-10 h-10 rounded-lg border border-dark-700 cursor-pointer bg-transparent" />
                        <FormInput type="text" value={profileTheme.name_color || ''}
                          onChange={e => setProfileTheme(p => ({ ...p, name_color: e.target.value }))}
                          placeholder={t('settings.name_color_placeholder')}
                          className="flex-1" />
                      </div>
                    </div>

                    <Toggle
                      checked={profileTheme.avatar_glow}
                      onChange={e => setProfileTheme(p => ({ ...p, avatar_glow: e.target.checked }))}
                      label={t('settings.avatar_glow')}
                    />
                  </div>

                  {/* Preview */}
                  <div className="bg-dark-900 rounded-xl p-4 flex items-center gap-4">
                    <div className="w-14 h-14 rounded-full bg-dark-700 flex items-center justify-center overflow-hidden flex-shrink-0"
                      style={{
                        borderColor: profileTheme.avatar_border,
                        borderWidth: '2px',
                        borderStyle: 'solid',
                        boxShadow: profileTheme.avatar_glow ? `0 0 12px ${profileTheme.avatar_border}` : undefined,
                      }}>
                      <span className={`text-lg font-bold ${profileTheme.name_color ? '' : roleStyle(user?.role).text}`} style={profileTheme.name_color ? { color: profileTheme.name_color } : undefined}>
                        {user?.username?.[0]?.toUpperCase() || 'U'}
                      </span>
                    </div>
                    <div>
                      <p className={`font-semibold text-sm ${profileTheme.name_color ? '' : roleStyle(user?.role).text}`} style={profileTheme.name_color ? { color: profileTheme.name_color } : undefined}>
                        {user?.username || 'username'}
                      </p>
                      <p className="text-[10px] text-dark-500">{t('settings.preview')}</p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="pb-4 text-center">
                  <Palette size={28} className="mx-auto text-dark-500 mb-2" />
                  <p className="text-dark-400 text-sm font-medium">{t('settings.premium_locked')}</p>
                  <p className="text-dark-500 text-xs mt-1">
                    {t('settings.premium_unlock_pre')}{' '}
                    <Link to="/shop" className="text-primary-400 hover:underline">{t('settings.premium_unlock_link')}</Link>.
                  </p>
                </div>
              )}

              <div className="py-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-semibold">{t('settings.dark_mode')}</h3>
                    <p className="text-sm text-dark-400">{t('settings.dark_mode_desc')}</p>
                  </div>
                  <Toggle checked={true} onChange={() => {}} />
                </div>
              </div>

            </div>
          </Card>
        )}
      </motion.div>
    </div>
  )
}
