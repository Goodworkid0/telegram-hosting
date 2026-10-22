import { useEffect, useRef, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'

export default function useTelegramBackButton() {
  const navigate = useNavigate()
  const location = useLocation()
  const handlerRef = useRef(null)

  const goBack = useCallback(() => {
    if (window.history.length > 1 && location.key !== 'default') {
      navigate(-1)
    }
  }, [navigate, location.key])

  // Keep the handler ref stable so offClick always removes the same reference
  useEffect(() => {
    handlerRef.current = goBack
  }, [goBack])

  useEffect(() => {
    const tg = window.Telegram?.WebApp
    if (!tg?.BackButton) return

    const bb = tg.BackButton

    const handleBack = () => {
      handlerRef.current?.()
    }

    bb.onClick(handleBack)

    if (location.pathname !== '/' && location.pathname !== '') {
      bb.show()
    } else {
      bb.hide()
    }

    return () => {
      bb.offClick(handleBack)
      // Only hide on final unmount, not on StrictMode remounts
      if (!tg.BackButton) return
      try { bb.hide() } catch (_) {}
    }
  }, [location.pathname])
}
