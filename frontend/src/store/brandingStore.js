import { create } from 'zustand'
import api from '../lib/api'

const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

const makeAbsoluteUrl = (path) => {
  if (!path) return null
  if (/^https?:\/\//i.test(path)) return path
  if (API_BASE) return `${API_BASE}${path}`
  return path
}

export const useBrandingStore = create((set, get) => ({
  appName: 'Forum',
  logoUrl: null,
  showLogo: true,
  botUsername: 'ForumMarketBot',
  maintenanceMode: false,
  announcementsUrl: null,
  officialGroupUrl: null,
  supportUsername: null,
  supportDisplayName: null,
  loaded: false,

  load: async () => {
    try {
      const { data } = await api.get('/api/branding')
      set({
        appName: data.app_name || 'Forum',
        logoUrl: makeAbsoluteUrl(data.logo_url),
        showLogo: data.show_logo !== false,
        botUsername: data.bot_username || 'ForumMarketBot',
        maintenanceMode: data.maintenance_mode || false,
        announcementsUrl: data.announcements_url,
        officialGroupUrl: data.official_group_url,
        supportUsername: data.support_username,
        supportDisplayName: data.support_display_name,
        loaded: true,
      })
    } catch (e) {
      console.error('Failed to load branding', e)
      set({ loaded: true })
    }
  },
}))
