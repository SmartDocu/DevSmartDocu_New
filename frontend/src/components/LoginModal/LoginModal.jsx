import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'

export default function LoginModal({ open, onClose }) {
  const navigate = useNavigate()
  const location = useLocation()
  const setAuth = useAuthStore((s) => s.setAuth)
  useLangStore((s) => s.translations)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [showReset, setShowReset] = useState(false)
  const [resetEmail, setResetEmail] = useState('')
  const [resetMsg, setResetMsg] = useState('')

  // 모달 열릴 때 초기화
  useEffect(() => {
    if (!open) return
    setEmail('')
    setPassword('')
    setLoading(false)
    setShowReset(false)
    setResetEmail('')
    setResetMsg('')
  }, [open])

  // ESC 닫기
  useEffect(() => {
    if (!open) return
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  const submitDisabled = !email.trim() || !password.trim() || loading

  const handleLogin = async () => {
    if (!email.trim()) { alert(t('msg.email.required')); return }
    if (!password.trim()) { alert(t('msg.password.required')); return }

    setLoading(true)
    try {
      const res = await apiClient.post('/auth/login', { email, password })
      const data = res.data
      setAuth({
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
        user: data.user,
      })
      onClose()
      // 1초 뒤 페이지 새로고침 효과 (로그인 완료 알림 후)
      setTimeout(() => {
        const from = location.state?.from?.pathname
        if (from && from !== '/login') navigate(from, { replace: true })
      }, 100)
    } catch (err) {
      const detail = err.response?.data?.detail || t('msg.login.failed')
      alert(detail)
    } finally {
      setLoading(false)
    }
  }

  const handleResetSubmit = async (e) => {
    e.preventDefault()
    if (!resetEmail.trim()) { setResetMsg(t('msg.email.required')); return }
    try {
      const res = await apiClient.post('/auth/send-reset-email', { email: resetEmail })
      setResetMsg(res.data?.message || t('msg.reset.sent'))
      setTimeout(() => {
        setResetMsg('')
        onClose()
      }, 2000)
    } catch (err) {
      setResetMsg(err.response?.data?.detail || t('msg.server.error'))
    }
  }

  if (!open) return null

  return (
    <div
      style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 9999,
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div style={{
        background: '#fff', padding: '30px 25px', borderRadius: 12,
        width: 360,
        boxShadow: '0 8px 24px rgba(0,0,0,0.2)',
        textAlign: 'center', position: 'relative',
      }}>
        {/* 닫기 버튼 */}
        <button
          onClick={onClose}
          style={{ position: 'absolute', top: 10, right: 10, background: 'transparent', border: 'none', fontSize: 20, cursor: 'pointer', lineHeight: 1 }}
        >
          &times;
        </button>

        <h2 style={{ fontWeight: 'bold', marginBottom: 20 }}>{t('ttl.login_ttl')}</h2>

        {/* 이메일 */}
        <label style={{ display: 'flex', alignItems: 'center', marginBottom: 12, gap: 8 }}>
          <span style={{ width: 70, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>{t('lbl.email')}</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t('lbl.email')}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); document.getElementById('login-pw-input').focus() } }}
            style={{ flex: 1, height: 36, padding: '4px 8px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }}
          />
        </label>

        {/* 비밀번호 */}
        <label style={{ display: 'flex', alignItems: 'center', marginBottom: 20, gap: 8 }}>
          <span style={{ width: 70, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>{t('lbl.password')}</span>
          <input
            id="login-pw-input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t('lbl.password')}
            onKeyDown={(e) => { if (e.key === 'Enter' && !submitDisabled) handleLogin() }}
            style={{ flex: 1, height: 36, padding: '4px 8px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }}
          />
        </label>

        {/* 버튼 영역 */}
        <div style={{ display: 'flex', gap: 10, justifyContent: 'center', marginBottom: 16 }}>
          <button
            onClick={() => setShowReset(!showReset)}
            className="btn btn-secondary"
            style={{ fontSize: 13 }}
          >
            {showReset ? t('btn.reset.close') : t('btn.reset.password')}
          </button>
          <button
            onClick={handleLogin}
            disabled={submitDisabled}
            className="btn btn-primary"
            style={{ fontSize: 13 }}
          >
            {loading ? t('btn.login.ing') : t('btn.login_btn')}
          </button>
        </div>

        {/* 비밀번호 재설정 폼 */}
        {showReset && (
          <form onSubmit={handleResetSubmit} style={{ marginTop: 16, textAlign: 'left' }}>
            <label style={{ fontSize: 14, display: 'block', marginBottom: 6 }}>{t('lbl.reset.email')}</label>
            <input
              type="email"
              value={resetEmail}
              onChange={(e) => setResetEmail(e.target.value)}
              placeholder={t('msg.ph.email')}
              required
              style={{ width: '100%', height: 36, padding: '4px 8px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14, boxSizing: 'border-box' }}
            />
            <button type="submit" className="btn btn-secondary" style={{ marginTop: 8, width: '100%' }}>
              {t('btn.reset.send')}
            </button>
            {resetMsg && (
              <div style={{ marginTop: 8, fontSize: 13, color: '#245F97', textAlign: 'center' }}>{resetMsg}</div>
            )}
          </form>
        )}
      </div>
    </div>
  )
}
