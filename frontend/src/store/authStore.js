import { create } from 'zustand'
import api, { refreshAccessToken, clearStoredAuth } from '../lib/api'
import { getTokenExpiryMs } from '../lib/utils'
import { triggerSessionExpiryModal } from '../components/SessionExpiryModal'

const SESSION_WARNING_BEFORE_MS = 5 * 60 * 1000 // 5 minutes before expiry

// Roles: user, moderator, admin
const normalizeRole = (role) => String(role || 'user').toLowerCase()

const persistTokens = (authData) => {
  localStorage.setItem('token', authData.access_token)
  if (authData.refresh_token) {
    localStorage.setItem('refresh_token', authData.refresh_token)
  }
}

export const useAuthStore = create((set, get) => ({
  user: null,
  token: null,
  isLoading: false,
  isInitialized: false,
  tg: null,
  _sessionTimer: null,
  _sseSource: null,

  initTelegram: async () => {
    const restored = await get().restoreSession()
    if (restored) return

    const tg = window.Telegram?.WebApp
    
    if (tg && tg.initDataUnsafe?.user) {
      tg.ready()
      tg.expand()
      tg.enableClosingConfirmation()
      document.documentElement.style.setProperty('--tg-theme-bg-color', tg.themeParams?.bg_color || '#0f172a')
      set({ tg })
      if (import.meta.env.DEV) console.log('Telegram user detected:', tg.initDataUnsafe.user)
      await get().loginWithTelegram(tg.initData, tg.initDataUnsafe)
    } else {
      if (tg?.initData) {
        try {
          const params = new URLSearchParams(tg.initData)
          const userRaw = params.get('user')
          const authDate = params.get('auth_date')
          const hash = params.get('hash')
          if (userRaw && authDate && hash) {
            const parsedUser = JSON.parse(userRaw)
            const fallback = { user: parsedUser, auth_date: parseInt(authDate), hash }
            await get().loginWithTelegram(tg.initData, fallback)
            return
          }
        } catch (error) {
          if (import.meta.env.DEV) console.warn('Failed to parse Telegram initData:', error)
        }
      }
      const urlParams = new URLSearchParams(window.location.search)
      const telegramId = urlParams.get('id')
      const authHash = urlParams.get('hash')
      
      if (telegramId && authHash) {
        await get().loginWithUrlParams(urlParams)
        window.history.replaceState({}, '', window.location.pathname)
      } else {
        if (import.meta.env.DEV) console.log('Development mode - no Telegram WebApp')
        set({ isInitialized: true })
      }
    }
  },

  loginWithUrlParams: async (urlParams) => {
    set({ isLoading: true })
    try {
      const userData = {
        id: parseInt(urlParams.get('id')),
        first_name: urlParams.get('first_name') || '',
        last_name: urlParams.get('last_name') || '',
        username: urlParams.get('username') || '',
        auth_date: parseInt(urlParams.get('auth_date')),
        hash: urlParams.get('hash')
      }
      
      const { data } = await api.post('/api/auth/telegram', { ...userData, photo_url: '', init_data: '' })
      persistTokens(data)
      api.defaults.headers.common['Authorization'] = `Bearer ${data.access_token}`
      
      const userRes = await api.get('/api/auth/me')
      set({ user: userRes.data, token: data.access_token, isInitialized: true })
      get().startBalancePoll()
      get().startSessionTimer()
    } catch (error) {
      if (import.meta.env.DEV) console.error('URL params login error:', error)
      set({ isInitialized: true })
    } finally {
      set({ isLoading: false })
    }
  },

  loginWithTelegram: async (initData, initDataUnsafe) => {
    set({ isLoading: true })
    try {
      const user = initDataUnsafe.user
      const { data } = await api.post('/api/auth/telegram', {
        id: user.id,
        first_name: user.first_name,
        last_name: user.last_name || '',
        username: user.username || '',
        photo_url: user.photo_url || '',
        auth_date: initDataUnsafe.auth_date,
        hash: initDataUnsafe.hash || 'dev',
        init_data: initData
      })
      
      persistTokens(data)
      api.defaults.headers.common['Authorization'] = `Bearer ${data.access_token}`
      
      const userRes = await api.get('/api/auth/me')
      set({ user: userRes.data, token: data.access_token, isInitialized: true })
      get().haptic('success')
      get().startBalancePoll()
      get().startSessionTimer()
    } catch (error) {
      console.error('Telegram login error:', error?.response?.data || error)
      set({ isInitialized: true, user: null, token: null })
    } finally {
      set({ isLoading: false })
    }
  },

  devLogin: async (telegramId = '123456789') => {
    set({ isLoading: true })
    try {
      const { data } = await api.post(`/api/auth/dev-login?telegram_id=${telegramId}`)
      persistTokens(data)
      api.defaults.headers.common['Authorization'] = `Bearer ${data.access_token}`
      
      const userRes = await api.get('/api/auth/me')
      set({ user: userRes.data, token: data.access_token, isInitialized: true })
      get().startBalancePoll()
      get().startSessionTimer()
    } catch (error) {
      if (import.meta.env.DEV) console.error('Dev login error:', error)
      set({ isInitialized: true })
    } finally {
      set({ isLoading: false })
    }
  },

  restoreSession: async () => {
    const token = localStorage.getItem('token')
    const refreshToken = localStorage.getItem('refresh_token')
    if (token) {
      api.defaults.headers.common['Authorization'] = `Bearer ${token}`
      try {
        const userRes = await api.get('/api/auth/me')
        set({ user: userRes.data, token, isInitialized: true })
        get().startBalancePoll()
        get().startSessionTimer()
        return true
      } catch {
        if (refreshToken) {
          try {
            const { data: refreshed } = await api.post('/api/auth/refresh', { refresh_token: refreshToken })
            persistTokens(refreshed)
            api.defaults.headers.common['Authorization'] = `Bearer ${refreshed.access_token}`
            const userRes = await api.get('/api/auth/me')
            set({ user: userRes.data, token: refreshed.access_token, isInitialized: true })
            get().startBalancePoll()
            get().startSessionTimer()
            return true
          } catch {
            clearStoredAuth()
          }
        } else {
          clearStoredAuth()
        }
      }
    }
    set({ isInitialized: true })
    return false
  },

  stopSessionTimer: () => {
    const timer = get()._sessionTimer
    if (timer) {
      clearTimeout(timer)
      set({ _sessionTimer: null })
    }
  },

  startSessionTimer: () => {
    get().stopSessionTimer()

    const token = localStorage.getItem('token')
    if (!token) return

    const expiryMs = getTokenExpiryMs(token)
    if (!expiryMs) return

    const now = Date.now()
    const msUntilWarning = expiryMs - now - SESSION_WARNING_BEFORE_MS

    if (msUntilWarning <= 0) {
      get()._promptSessionExtend()
      return
    }

    const timer = setTimeout(() => {
      get()._promptSessionExtend()
    }, msUntilWarning)

    set({ _sessionTimer: timer })
  },

  _promptSessionExtend: async () => {
    set({ _sessionTimer: null })

    const token = localStorage.getItem('token')
    if (!token) return

    const expiryMs = getTokenExpiryMs(token)
    if (!expiryMs) return

    const secondsLeft = Math.max(0, Math.floor((expiryMs - Date.now()) / 1000))
    if (secondsLeft <= 0) {
      get().logout()
      return
    }

    const shouldExtend = await triggerSessionExpiryModal(secondsLeft)

    if (shouldExtend) {
      try {
        await refreshAccessToken()
        get().startSessionTimer()
      } catch {
        get().logout()
      }
    } else {
      get().logout()
    }
  },

  logout: () => {
    get().stopBalancePoll()
    get().stopSessionTimer()
    api.post('/api/auth/logout').catch(() => {})
    clearStoredAuth()
    set({ user: null, token: null })
    const { tg } = get()
    if (tg) tg.close()
  },

  startBalancePoll: () => {
    get().stopBalancePoll()
    const authHeader = api.defaults.headers.common['Authorization']
    if (!authHeader) return

    const baseUrl = api.defaults.baseURL || ''
    const url = `${baseUrl}/api/sse`

    let aborted = false
    const controller = new AbortController()
    set({ _sseSource: controller })

    const connect = async () => {
      try {
        const headers = { signal: controller.signal }
        const currentAuth = api.defaults.headers.common['Authorization']
        if (currentAuth) {
          headers.headers = { Authorization: currentAuth }
        }
        const response = await fetch(url, headers)
        if (!response.ok || !response.body) return

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (!aborted) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          let eventType = ''
          for (const line of lines) {
            if (line.startsWith('event: ')) eventType = line.slice(7).trim()
            else if (line.startsWith('data: ') && eventType) {
              try {
                const data = JSON.parse(line.slice(6))
                if (eventType === 'balance' && data.balance !== undefined) {
                  set(state => ({ user: state.user ? { ...state.user, balance: data.balance } : null }))
                } else if (eventType === 'notification' && data.type) {
                  set(state => ({
                    user: state.user ? {
                      ...state.user,
                      _lastNotification: { type: data.type, title: data.title, body: data.body, link: data.link }
                    } : null
                  }))
                }
              } catch {}
              eventType = ''
            }
          }
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          // Retry after 5 seconds
          if (!aborted) setTimeout(connect, 5000)
        }
      }
    }

    connect()
  },

  stopBalancePoll: () => {
    const source = get()._sseSource
    if (source) {
      if (source.abort) source.abort()
      set({ _sseSource: null })
    }
  },

  setUser: (user) => set({ user }),

  // Role helpers
  ROLE_ORDER: { user: 1, moderator: 2, admin: 3 },
  getRole: () => normalizeRole(get().user?.role),
  getUserLevel: () => get().ROLE_ORDER[get().getRole()] ?? 1,
  isAdmin: () => get().getRole() === 'admin',
  isModerator: () => ['moderator', 'admin'].includes(get().getRole()),

  // Subscription (unlimited downloads): active while premium_until is in the
  // future, or indefinitely for an admin lifetime grant (premium_until null).
  subscriptionActive: () => {
    const u = get().user
    if (!u?.is_premium) return false
    return !u.premium_until || new Date(u.premium_until + 'Z') > new Date()
  },

  haptic: (type = 'light') => {
    const { tg } = get()
    if (tg?.HapticFeedback) {
      if (type === 'light') tg.HapticFeedback.impactOccurred('light')
      else if (type === 'medium') tg.HapticFeedback.impactOccurred('medium')
      else if (type === 'heavy') tg.HapticFeedback.impactOccurred('heavy')
      else if (type === 'success') tg.HapticFeedback.notificationOccurred('success')
      else if (type === 'warning') tg.HapticFeedback.notificationOccurred('warning')
      else if (type === 'error') tg.HapticFeedback.notificationOccurred('error')
    }
  }
}))
