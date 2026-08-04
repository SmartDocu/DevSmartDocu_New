import { useEffect, useRef, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Spin } from 'antd'
import QRCode from 'qrcode'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useMfaEnroll, useMfaEnrollVerify } from '@/hooks/useMfa'

export default function LoginModal({ open, onClose }) {
  const navigate = useNavigate()
  const location = useLocation()
  const setAuth = useAuthStore((s) => s.setAuth)
  const updateTokens = useAuthStore((s) => s.updateTokens)
  const clearAuth = useAuthStore((s) => s.clearAuth)
  useLangStore((s) => s.translations)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [showReset, setShowReset] = useState(false)
  const [resetEmail, setResetEmail] = useState('')
  const [resetMsg, setResetMsg] = useState('')
  const [errorMsg, setErrorMsg] = useState('')

  // 로그인 진행 단계: 'login' | 'mfa'(TOTP 챌린지) | 'tenant'(테넌트 선택) | 'mfaSetup'(강제 MFA 등록)
  const [step, setStep] = useState('login')
  const [mfaCode, setMfaCode] = useState('')
  // pending: 단계 사이에 들고 다니는 값들 — tenants, 임시 토큰, 선택된 tenantid, TOTP factor_id
  const [pending, setPending] = useState(null)
  const mfaInputRef = useRef(null)

  // 강제 MFA 설정용 상태
  const mfaSetupEnroll = useMfaEnroll()
  const mfaSetupVerify = useMfaEnrollVerify()
  const [mfaSetupData, setMfaSetupData] = useState(null) // { factor_id, totp_uri, secret }
  const [mfaSetupQr, setMfaSetupQr] = useState('')
  const [mfaSetupCode, setMfaSetupCode] = useState('')

  // 모달 열릴 때 초기화
  useEffect(() => {
    if (!open) return
    setEmail('')
    setPassword('')
    setLoading(false)
    setShowReset(false)
    setResetEmail('')
    setResetMsg('')
    setErrorMsg('')
    setStep('login')
    setMfaCode('')
    setPending(null)
    setMfaSetupData(null)
    setMfaSetupQr('')
    setMfaSetupCode('')
  }, [open])

  // MFA 단계 전환 시 입력 필드 포커스
  useEffect(() => {
    if (step === 'mfa' && mfaInputRef.current) {
      setTimeout(() => mfaInputRef.current?.focus(), 50)
    }
  }, [step])

  // 강제 MFA 설정 단계 진입 시 자동으로 enroll 시작
  useEffect(() => {
    if (step !== 'mfaSetup' || mfaSetupData) return
    mfaSetupEnroll.mutate(undefined, {
      onSuccess: (data) => setMfaSetupData(data),
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step])

  // 강제 MFA 설정 QR 코드 렌더링
  useEffect(() => {
    if (!mfaSetupData?.totp_uri) { setMfaSetupQr(''); return }
    QRCode.toDataURL(mfaSetupData.totp_uri, { width: 160, margin: 2 })
      .then(setMfaSetupQr)
      .catch(() => setMfaSetupQr(''))
  }, [mfaSetupData])

  // ESC 닫기
  useEffect(() => {
    if (!open) return
    const handler = (e) => { if (e.key === 'Escape') handleClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, step])

  const submitDisabled = !email.trim() || !password.trim() || loading

  // 로그인 백엔드 응답을 단계별로 분기 처리 (login / select-tenant / mfa-enroll-verify 재개 지점에서 공용 사용)
  const _handleLoginStageResult = (data) => {
    if (data.tenant_selection_required) {
      setPending({
        tenants: data.tenants || [],
        access_token_temp: data.access_token_temp,
        refresh_token_temp: data.refresh_token_temp,
      })
      setStep('tenant')
      return
    }
    if (data.mfa_setup_required) {
      setPending((p) => ({
        ...(p || {}),
        access_token_temp: data.access_token_temp,
        refresh_token_temp: data.refresh_token_temp,
        tenantid: data.tenantid,
      }))
      // 강제 설정 화면에서 useMfaEnroll/useMfaEnrollVerify가 정상 동작하도록 임시 토큰을 우선 세팅
      setAuth({ accessToken: data.access_token_temp, refreshToken: data.refresh_token_temp, user: null })
      setMfaSetupData(null)
      setMfaSetupCode('')
      setStep('mfaSetup')
      return
    }
    if (data.mfa_required) {
      setPending((p) => ({
        ...(p || {}),
        access_token_temp: data.access_token_temp,
        refresh_token_temp: data.refresh_token_temp,
        tenantid: data.tenantid,
        factor_id: data.factor_id,
      }))
      setStep('mfa')
      return
    }
    _finalizeLogin(data)
  }

  const handleLogin = async () => {
    setErrorMsg('')
    if (!email.trim()) { setErrorMsg(t('msg.email.required')); return }
    if (!password.trim()) { setErrorMsg(t('msg.password.required')); return }

    setLoading(true)
    try {
      const res = await apiClient.post('/auth/login', { email, password })
      _handleLoginStageResult(res.data)
    } catch (err) {
      const detail = err.response?.data?.detail || t('msg.login.failed')
      setErrorMsg(detail)
    } finally {
      setLoading(false)
    }
  }

  const handleSelectTenant = async (tenantid) => {
    setErrorMsg('')
    setLoading(true)
    try {
      const res = await apiClient.post('/auth/select-tenant', {
        tenantid,
        access_token_temp: pending.access_token_temp,
        refresh_token_temp: pending.refresh_token_temp,
      })
      _handleLoginStageResult(res.data)
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || t('msg.login.failed'))
    } finally {
      setLoading(false)
    }
  }

  const handleMfaVerify = async () => {
    setErrorMsg('')
    if (mfaCode.length !== 6) { setErrorMsg(t('val.mfa.code_length')); return }

    setLoading(true)
    try {
      const res = await apiClient.post('/auth/mfa-verify', {
        factor_id: pending.factor_id,
        code: mfaCode,
        access_token: pending.access_token_temp,
        refresh_token: pending.refresh_token_temp,
        tenantid: pending.tenantid || null,
      })
      _finalizeLogin(res.data)
    } catch (err) {
      const detail = err.response?.data?.detail || t('msg.mfa.code_invalid')
      setErrorMsg(detail)
      setMfaCode('')
      mfaInputRef.current?.focus()
    } finally {
      setLoading(false)
    }
  }

  const handleMfaSetupVerify = () => {
    setErrorMsg('')
    if (mfaSetupCode.length !== 6 || !mfaSetupData) { setErrorMsg(t('val.mfa.code_length')); return }
    mfaSetupVerify.mutate(
      { factor_id: mfaSetupData.factor_id, code: mfaSetupCode },
      {
        onSuccess: async (data) => {
          const accessTokenTemp = data.access_token || pending.access_token_temp
          const refreshTokenTemp = data.refresh_token || pending.refresh_token_temp
          if (data.access_token) {
            updateTokens({ accessToken: data.access_token, refreshToken: data.refresh_token || pending.refresh_token_temp })
          }
          setLoading(true)
          try {
            const res = await apiClient.post('/auth/select-tenant', {
              tenantid: pending.tenantid,
              access_token_temp: accessTokenTemp,
              refresh_token_temp: refreshTokenTemp,
            })
            _handleLoginStageResult(res.data)
          } catch (err) {
            setErrorMsg(err.response?.data?.detail || t('msg.login.failed'))
          } finally {
            setLoading(false)
          }
        },
        onError: (err) => { setMfaSetupCode(''); setErrorMsg(err.response?.data?.detail || t('msg.mfa.code_invalid')) },
      },
    )
  }

  const _finalizeLogin = (data) => {
    setAuth({
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      user: data.user,
    })
    onClose()
    setTimeout(() => {
      const from = location.state?.from?.pathname
      if (from && from !== '/login') navigate(from, { replace: true })
    }, 100)
  }

  const handleClose = () => {
    // 강제 MFA 설정 중 이탈 시, authStore에 임시로 세팅해둔 미완성 세션을 남기지 않는다
    if (step === 'mfaSetup') {
      clearAuth()
    }
    setStep('login')
    onClose()
  }

  const handleResetSubmit = async (e) => {
    e.preventDefault()
    if (!resetEmail.trim()) { setResetMsg(t('msg.email.required')); return }
    try {
      const res = await apiClient.post('/auth/send-reset-email', { email: resetEmail })
      setResetMsg(res.data?.message || t('msg.reset.sent'))
      setTimeout(() => {
        setResetMsg('')
        handleClose()
      }, 2000)
    } catch (err) {
      setResetMsg(err.response?.data?.detail || t('msg.server.error'))
    }
  }

  if (!open) return null

  const modalTitle = () => {
    if (step === 'mfa') return t('ttl.mfa.verify')
    if (step === 'tenant') return t('ttl.tenant.select')
    if (step === 'mfaSetup') return t('ttl.mfa.setup')
    return t('ttl.login_ttl')
  }

  return (
    <div
      style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 9999,
      }}
    >
      <div style={{
        background: '#fff', padding: '30px 25px', borderRadius: 12,
        width: step === 'mfaSetup' ? 400 : 360,
        boxShadow: '0 8px 24px rgba(0,0,0,0.2)',
        textAlign: 'center', position: 'relative',
      }}>
        {/* 닫기 버튼 */}
        <button
          onClick={handleClose}
          style={{ position: 'absolute', top: 10, right: 10, background: 'transparent', border: 'none', fontSize: 20, cursor: 'pointer', lineHeight: 1 }}
        >
          &times;
        </button>

        <h2 style={{ fontWeight: 'bold', marginBottom: 20 }}>
          {modalTitle()}
        </h2>

        {errorMsg && (
          <div style={{
            marginBottom: 16, padding: '8px 12px', borderRadius: 6,
            background: '#fff1f0', border: '1px solid #ffccc7',
            color: '#cf1322', fontSize: 13, textAlign: 'left',
          }}>
            {errorMsg}
          </div>
        )}

        {/* ── 테넌트 선택 단계 ─────────────────────────────────────── */}
        {step === 'tenant' && (
          <>
            <div style={{ maxHeight: 260, overflowY: 'auto', marginBottom: 16, textAlign: 'left' }}>
              {(pending?.tenants || []).map((tn) => (
                <div
                  key={tn.tenantid}
                  onClick={() => !loading && handleSelectTenant(tn.tenantid)}
                  style={{
                    padding: '10px 14px', marginBottom: 8, border: '1px solid #e0e0e0', borderRadius: 6,
                    cursor: loading ? 'default' : 'pointer', fontSize: 14,
                  }}
                >
                  {tn.tenantnm}
                </div>
              ))}
            </div>
          </>
        )}

        {/* ── 강제 MFA 설정 단계 ───────────────────────────────────── */}
        {step === 'mfaSetup' && (
          <>
            <div style={{ fontSize: 13, color: '#888', marginBottom: 16, textAlign: 'left' }}>
              {t('msg.mfa.setup_required')}
            </div>
            {mfaSetupQr && (
              <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 12 }}>
                <img src={mfaSetupQr} alt="QR Code" style={{ width: 160, height: 160, border: '1px solid #f0f0f0', borderRadius: 8 }} />
              </div>
            )}
            {mfaSetupData?.secret && (
              <div style={{ fontFamily: 'monospace', fontSize: 12, color: '#666', marginBottom: 16, wordBreak: 'break-all' }}>
                {mfaSetupData.secret}
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                value={mfaSetupCode}
                onChange={(e) => setMfaSetupCode(e.target.value.replace(/\D/g, ''))}
                onKeyDown={(e) => { if (e.key === 'Enter' && mfaSetupCode.length === 6) handleMfaSetupVerify() }}
                placeholder="000000"
                style={{
                  width: 160, height: 44, textAlign: 'center',
                  letterSpacing: 8, fontFamily: 'monospace', fontSize: 22,
                  borderRadius: 6, border: '1px solid #ccc', padding: '4px 8px',
                }}
              />
            </div>
            <button
              onClick={handleMfaSetupVerify}
              disabled={mfaSetupCode.length !== 6 || loading || !mfaSetupData}
              className="btn btn-primary"
              style={{ fontSize: 13 }}
            >
              {loading ? t('btn.login.ing') : t('btn.mfa.activate')}
            </button>
          </>
        )}

        {/* ── MFA 2단계: TOTP 코드 입력 ─────────────────────────────── */}
        {step === 'mfa' && (
          <>
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 20 }}>
              <input
                ref={mfaInputRef}
                type="text"
                inputMode="numeric"
                maxLength={6}
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, ''))}
                onKeyDown={(e) => { if (e.key === 'Enter' && mfaCode.length === 6) handleMfaVerify() }}
                placeholder="000000"
                style={{
                  width: 160, height: 44, textAlign: 'center',
                  letterSpacing: 8, fontFamily: 'monospace', fontSize: 22,
                  borderRadius: 6, border: '1px solid #ccc', padding: '4px 8px',
                }}
              />
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
              <button
                onClick={() => { setStep('login'); setMfaCode(''); setPending(null) }}
                className="btn btn-secondary"
                style={{ fontSize: 13 }}
                disabled={loading}
              >
                {t('btn.cancel')}
              </button>
              <button
                onClick={handleMfaVerify}
                disabled={mfaCode.length !== 6 || loading}
                className="btn btn-primary"
                style={{ fontSize: 13 }}
              >
                {loading ? t('btn.login.ing') : t('ttl.mfa.verify')}
              </button>
            </div>
          </>
        )}

        {step === 'login' && (
          <>
            {/* ── 1단계: 이메일 + 비밀번호 ─────────────────────────────── */}
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
          </>
        )}
      </div>

      {/* 테넌트 선택 후 처리 중 안내 — 잠시 멈춘 것처럼 보이지 않도록 */}
      {loading && step === 'tenant' && (
        <div style={{
          position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
          background: 'rgba(0,0,0,0.5)',
          display: 'flex', justifyContent: 'center', alignItems: 'center',
          zIndex: 10000,
        }}>
          <div style={{
            background: '#fafae5', padding: '20px 30px', borderRadius: 8,
            fontSize: 16, fontWeight: 'bold', color: '#6c757d',
            boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
            display: 'flex', alignItems: 'center', gap: 12,
          }}>
            <Spin />
            <span>{t('msg.tenant.switching')}</span>
          </div>
        </div>
      )}
    </div>
  )
}
