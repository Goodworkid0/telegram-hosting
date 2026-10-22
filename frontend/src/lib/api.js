import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json'
  }
})

let refreshInFlight = null

const setAccessToken = (token) => {
  if (token) {
    localStorage.setItem('token', token)
    api.defaults.headers.common['Authorization'] = `Bearer ${token}`
    return
  }
  localStorage.removeItem('token')
  delete api.defaults.headers.common['Authorization']
}

const clearStoredAuth = () => {
  localStorage.removeItem('token')
  localStorage.removeItem('refresh_token')
  delete api.defaults.headers.common['Authorization']
}

const refreshAccessToken = async () => {
  if (refreshInFlight) return refreshInFlight

  const refreshToken = localStorage.getItem('refresh_token')
  if (!refreshToken) throw new Error('No refresh token')

  refreshInFlight = axios
    .post(`${api.defaults.baseURL || ''}/api/auth/refresh`, { refresh_token: refreshToken }, {
      headers: { 'Content-Type': 'application/json' }
    })
    .then((res) => {
      const newAccess = res?.data?.access_token
      const newRefresh = res?.data?.refresh_token
      if (!newAccess) throw new Error('Refresh response missing access token')
      setAccessToken(newAccess)
      if (newRefresh) localStorage.setItem('refresh_token', newRefresh)
      return newAccess
    })
    .finally(() => {
      refreshInFlight = null
    })

  return refreshInFlight
}

// Add token from localStorage
const token = localStorage.getItem('token')
if (token) {
  setAccessToken(token)
}

// Response interceptor for error handling
api.interceptors.response.use(
  response => response,
  async error => {
    const status = error?.response?.status
    const originalRequest = error?.config

    if (status === 401 && originalRequest) {
      const isRefreshCall = String(originalRequest.url || '').includes('/api/auth/refresh')
      const hasRefresh = !!localStorage.getItem('refresh_token')

      if (isRefreshCall || originalRequest._retryCount || !hasRefresh) {
        clearStoredAuth()
        return Promise.reject(error)
      }

      originalRequest._retryCount = 1
      try {
        const newAccess = await refreshAccessToken()
        originalRequest.headers = {
          ...(originalRequest.headers || {}),
          Authorization: `Bearer ${newAccess}`
        }
        return api(originalRequest)
      } catch (refreshError) {
        clearStoredAuth()
        return Promise.reject(refreshError)
      }
    }

    // Retry logic for 5xx errors and network errors
    if (originalRequest) {
      const retryCount = originalRequest._retryCount || 0
      const isNetworkError = !error.response
      const isServerError = error.response && error.response.status >= 500

      if (retryCount < 2 && (isNetworkError || isServerError)) {
        const method = (originalRequest.method || 'get').toLowerCase()
        const isIdempotent = ['get', 'head', 'options'].includes(method)

        if (isIdempotent || isNetworkError) {
          originalRequest._retryCount = retryCount + 1
          const delay = originalRequest._retryCount === 1 ? 1000 : 2000

          await new Promise(resolve => setTimeout(resolve, delay))
          return api(originalRequest)
        }
      }
    }

    return Promise.reject(error)
  }
)

export { refreshAccessToken, clearStoredAuth }
export default api
