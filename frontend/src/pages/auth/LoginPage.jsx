import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { Spin } from 'antd'
import QRCode from 'qrcode'
import apiClient from '@/api/client'
import { useAuthStore, setKeepLogin } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useMfaEnroll, useMfaEnrollVerify } from '@/hooks/useMfa'
import { getErrorMessage } from '@/utils/apiError'
import { clearClosedPopups } from '@/utils/popupSession'
import FindEmailModal from '@/components/FindEmailModal/FindEmailModal'

const RegisterModal = lazy(() => import('@/components/RegisterModal/RegisterModal'))

const LEGAL_BASE = 'https://d1y3pyhkb7jr6k.cloudfront.net'
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

const NAVY = '#0B2A6B'
const FOCUS_CSS = `
.lg-input{height:46px;padding:0 14px;font-family:inherit;font-size:15px;color:#14161a;background:#fff;border:1px solid #d9d5cd;border-radius:10px;outline:none;width:100%;box-sizing:border-box}
.lg-input:focus{border-color:oklch(.52 .17 264);box-shadow:0 0 0 3px oklch(.93 .04 264)}
.lg-btn{width:100%;height:48px;border:none;border-radius:11px;background:${NAVY};color:#fff;font-family:inherit;font-size:16px;font-weight:700;cursor:pointer}
.lg-btn:hover:not(:disabled){background:#123a8f}
.lg-btn:disabled{opacity:.55;cursor:default}
.lg-btn-sub{background:#fff;color:#4b5058;border:1px solid #d9d5cd}
.lg-btn-sub:hover:not(:disabled){background:#f4f2ee}
.lg-link{color:#4b5058;text-decoration:none;background:none;border:none;padding:0;font-family:inherit;font-size:14px;cursor:pointer}
.lg-link:hover{color:oklch(.4 .17 264)}
`

const labelStyle = { display: 'flex', flexDirection: 'column', gap: 7 }
const labelTextStyle = { fontSize: 13, fontWeight: 600, color: '#4b5058' }
const otpInputStyle = {
  width: 180, height: 50, textAlign: 'center', letterSpacing: 8, fontFamily: 'monospace',
  fontSize: 22, borderRadius: 10, border: '1px solid #d9d5cd', padding: '4px 8px',
}

export default function LoginPage() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const updateTokens = useAuthStore((s) => s.updateTokens)
  const clearAuth = useAuthStore((s) => s.clearAuth)
  // 로그인 완료(사용자 정보까지 있음) 상태에서 접근하면 홈으로. 강제 MFA 등록 중엔 user가 null이라 해당 없음
  const alreadyLoggedIn = useAuthStore((s) => !!s.accessToken && !!s.user)
  const languageCd = useLangStore((s) => s.languageCd)
  useLangStore((s) => s.translations)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [keep, setKeep] = useState(false)
  const [loading, setLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [showReset, setShowReset] = useState(false)
  const [resetEmail, setResetEmail] = useState('')
  const [resetMsg, setResetMsg] = useState('')
  const [registerOpen, setRegisterOpen] = useState(false)
  const [findOpen, setFindOpen] = useState(false)

  // 로그인 진행 단계: 'login' | 'mfa'(TOTP 챌린지) | 'tenant'(테넌트 선택) | 'mfaSetup'(강제 MFA 등록)
  const [step, setStep] = useState('login')
  const [mfaCode, setMfaCode] = useState('')
  // pending: 단계 사이에 들고 다니는 값들 — tenants, 임시 토큰, 선택된 tenantid, TOTP factor_id
  const [pending, setPending] = useState(null)
  const mfaInputRef = useRef(null)
  const stepRef = useRef('login')
  const finalizedRef = useRef(false)
  stepRef.current = step

  // 강제 MFA 설정용 상태
  const mfaSetupEnroll = useMfaEnroll()
  const mfaSetupVerify = useMfaEnrollVerify()
  const [mfaSetupData, setMfaSetupData] = useState(null) // { factor_id, totp_uri, secret }
  const [mfaSetupQr, setMfaSetupQr] = useState('')
  const [mfaSetupCode, setMfaSetupCode] = useState('')

  // 강제 MFA 설정 중 페이지를 벗어나면, authStore에 임시로 세팅해둔 미완성 세션을 남기지 않는다
  useEffect(() => () => {
    if (stepRef.current === 'mfaSetup' && !finalizedRef.current) clearAuth()
  }, [clearAuth])

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
      onSuccess: (data) => { setMfaSetupData(data) },
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

  if (alreadyLoggedIn) return <Navigate to="/" replace />

  const legalLang = languageCd === 'ko' ? 'ko' : 'en'
  const submitDisabled = loading || !email.trim() || !password.trim()

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

  // 로그인 후에는 항상 "/"로 이동 — 거기서 HomeOrLauncher가 accessToken 유무를 보고 /launcher로 보낸다.
  const _finalizeLogin = (data) => {
    finalizedRef.current = true
    clearClosedPopups() // 새 로그인 세션 — 로그인 후 팝업을 다시 보여준다
    setAuth({
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      user: data.user,
    })
    navigate('/', { replace: true })
  }

  const handleLogin = async (e) => {
    e?.preventDefault()
    setErrorMsg('')
    if (!EMAIL_REGEX.test(email.trim())) { setErrorMsg(t('msg.email.invalid')); return }
    if (!password.trim()) { setErrorMsg(t('msg.password.required')); return }

    setKeepLogin(keep) // 이후 setAuth가 저장될 위치(localStorage/sessionStorage)를 결정
    setLoading(true)
    try {
      const res = await apiClient.post('/auth/login', { email: email.trim(), password })
      _handleLoginStageResult(res.data)
    } catch (err) {
      setErrorMsg(getErrorMessage(err, 'msg.login.failed'))
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
      setErrorMsg(getErrorMessage(err, 'msg.login.failed'))
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
      setErrorMsg(getErrorMessage(err, 'msg.mfa.code_invalid'))
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
            setErrorMsg(getErrorMessage(err, 'msg.login.failed'))
          } finally {
            setLoading(false)
          }
        },
        onError: (err) => { setMfaSetupCode(''); setErrorMsg(getErrorMessage(err, 'msg.mfa.code_invalid')) },
      },
    )
  }

  const handleResetSubmit = async (e) => {
    e.preventDefault()
    if (!resetEmail.trim()) { setResetMsg(t('msg.email.required')); return }
    try {
      const res = await apiClient.post('/auth/send-reset-email', { email: resetEmail })
      setResetMsg(t('msg.reset.sent'))
      setTimeout(() => {
        setResetMsg('')
        setShowReset(false)
      }, 2000)
    } catch (err) {
      setResetMsg(getErrorMessage(err, 'msg.server.error'))
    }
  }

  const backToLogin = () => {
    setStep('login')
    setMfaCode('')
    setPending(null)
    setErrorMsg('')
  }

  const cardTitle = () => {
    if (step === 'mfa') return t('ttl.mfa.verify')
    if (step === 'tenant') return t('ttl.tenant.select')
    if (step === 'mfaSetup') return t('ttl.mfa.setup')
    return t('ttl.login.page')
  }

  return (
    <div style={{
      // AppLayout Content의 좌우·하단 padding(24px)을 상쇄해 푸터가 화면 좌우 끝·바닥에 붙도록 한다(헤더 60px 제외 전체 높이)
      minHeight: 'calc(100vh - 60px)', margin: '0 -24px -24px', display: 'flex', flexDirection: 'column',
      background: '#f4f2ee', color: '#14161a', overflow: 'hidden',
      fontFamily: "Pretendard, system-ui, sans-serif",
    }}>
      <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css" precedence="default" />
      <style>{FOCUS_CSS}</style>

      {/* 본문 */}
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{
          width: '100%', maxWidth: step === 'mfaSetup' ? 460 : 420, background: '#fff', border: '1px solid #e6e2da',
          borderRadius: 18, padding: '40px 36px 32px', boxShadow: '0 24px 60px -40px rgba(11,42,107,.35)',
        }}>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
            <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800, letterSpacing: '-.03em' }}>{cardTitle()}</h1>
            {step === 'login' && (
              <p style={{ margin: 0, fontSize: 14.5, color: '#6b707a' }}>{t('inf.login.subtitle')}</p>
            )}
          </div>

          {errorMsg && (
            <div style={{
              marginTop: 20, padding: '10px 12px', borderRadius: 9,
              background: 'oklch(.97 .02 25)', border: '1px solid oklch(.9 .05 25)',
              fontSize: 13.5, color: 'oklch(.45 .15 25)',
            }}>
              {errorMsg}
            </div>
          )}

          {/* ── 테넌트 선택 단계 ───────────────────────────────────── */}
          {step === 'tenant' && (
            <div style={{ maxHeight: 280, overflowY: 'auto', marginTop: 24, textAlign: 'left' }}>
              {[...(pending?.tenants || [])]
                .sort((a, b) => Number(!!a.issystemtenant) - Number(!!b.issystemtenant))
                .map((tn) => (
                  <div
                    key={tn.tenantid}
                    onClick={() => !loading && handleSelectTenant(tn.tenantid)}
                    style={{
                      padding: '12px 14px', marginBottom: 8, border: '1px solid #d9d5cd', borderRadius: 10,
                      cursor: loading ? 'default' : 'pointer', fontSize: 15,
                    }}
                  >
                    {tn.issystemtenant ? `${tn.tenantnm} (${t('lbl.tenant.personal')})` : (tn.disptenantnm || tn.tenantnm)}
                  </div>
                ))}
            </div>
          )}

          {/* ── 강제 MFA 설정 단계 ─────────────────────────────────── */}
          {step === 'mfaSetup' && (
            <div style={{ marginTop: 20, textAlign: 'center' }}>
              <div style={{ fontSize: 13.5, color: '#6b707a', marginBottom: 16, textAlign: 'left' }}>
                {t('msg.mfa.setup_required')}
              </div>
              {mfaSetupQr && (
                <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 12 }}>
                  <img src={mfaSetupQr} alt="QR Code" style={{ width: 160, height: 160, border: '1px solid #eae7e1', borderRadius: 8 }} />
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
                  style={otpInputStyle}
                />
              </div>
              <button
                type="button"
                className="lg-btn"
                onClick={handleMfaSetupVerify}
                disabled={mfaSetupCode.length !== 6 || loading || !mfaSetupData}
              >
                {loading ? t('btn.login.ing') : t('btn.mfa.activate')}
              </button>
            </div>
          )}

          {/* ── MFA 2단계: TOTP 코드 입력 ───────────────────────────── */}
          {step === 'mfa' && (
            <div style={{ marginTop: 24 }}>
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
                  style={otpInputStyle}
                />
              </div>
              <div style={{ display: 'flex', gap: 10 }}>
                <button type="button" className="lg-btn lg-btn-sub" onClick={backToLogin} disabled={loading}>
                  {t('btn.cancel')}
                </button>
                <button type="button" className="lg-btn" onClick={handleMfaVerify} disabled={mfaCode.length !== 6 || loading}>
                  {loading ? t('btn.login.ing') : t('ttl.mfa.verify')}
                </button>
              </div>
            </div>
          )}

          {/* ── 1단계: 이메일 + 비밀번호 ────────────────────────────── */}
          {step === 'login' && (
            <>
              <form onSubmit={handleLogin} noValidate>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 28 }}>
                  <label style={labelStyle}>
                    <span style={labelTextStyle}>{t('lbl.email')}</span>
                    <input
                      className="lg-input"
                      type="email"
                      autoComplete="username"
                      placeholder="name@company.com"
                      value={email}
                      onChange={(e) => { setEmail(e.target.value); setErrorMsg('') }}
                    />
                  </label>
                  <label style={labelStyle}>
                    <span style={labelTextStyle}>{t('lbl.password')}</span>
                    <div style={{ position: 'relative' }}>
                      <input
                        className="lg-input"
                        style={{ paddingRight: 46 }}
                        type={showPw ? 'text' : 'password'}
                        autoComplete="current-password"
                        placeholder={t('msg.ph.password')}
                        value={password}
                        onChange={(e) => { setPassword(e.target.value); setErrorMsg('') }}
                      />
                      <button
                        type="button"
                        onClick={() => setShowPw((v) => !v)}
                        title={showPw ? t('lbl.login.pw_hide') : t('lbl.login.pw_show')}
                        style={{
                          position: 'absolute', right: 6, top: 6, width: 34, height: 34, border: 'none',
                          background: 'transparent', borderRadius: 8, color: '#7b8088', cursor: 'pointer',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                        }}
                      >
                        {showPw ? (
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M3 3l18 18"></path><path d="M10.6 6.1A9.8 9.8 0 0 1 12 6c5.5 0 9 6 9 6a15.6 15.6 0 0 1-3.2 3.9M6.5 7.6C4.3 9.1 3 12 3 12s3.5 6 9 6c1.4 0 2.6-.3 3.7-.8"></path><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"></path></svg>
                        ) : (
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M3 12s3.5-6 9-6 9 6 9 6-3.5 6-9 6-9-6-9-6z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                        )}
                      </button>
                    </div>
                  </label>
                </div>

                <label style={{ display: 'flex', alignItems: 'center', gap: 9, marginTop: 14, cursor: 'pointer', width: 'max-content' }}>
                  <input
                    type="checkbox"
                    checked={keep}
                    onChange={() => setKeep((v) => !v)}
                    style={{ width: 17, height: 17, margin: 0, accentColor: NAVY, cursor: 'pointer' }}
                  />
                  <span style={{ fontSize: 14, color: '#4b5058' }}>{t('lbl.login.keep')}</span>
                </label>

                <button type="submit" className="lg-btn" style={{ marginTop: 22 }} disabled={submitDisabled}>
                  {loading ? t('btn.login.ing') : t('btn.login_btn')}
                </button>
              </form>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, marginTop: 18, flexWrap: 'wrap' }}>
                {/* 가입한 이메일(=아이디)이 기억나지 않을 때의 안내 팝업 */}
                <button type="button" className="lg-link" onClick={() => setFindOpen(true)}>{t('lbl.login.find_id')}</button>
                <span style={{ width: 1, height: 12, background: '#d9d5cd' }} />
                <button type="button" className="lg-link" onClick={() => setShowReset((v) => !v)}>
                  {showReset ? t('btn.reset.close') : t('btn.reset.password')}
                </button>
              </div>

              {/* 비밀번호 재설정 폼 */}
              {showReset && (
                <form onSubmit={handleResetSubmit} style={{ marginTop: 16, textAlign: 'left' }}>
                  <label style={{ ...labelTextStyle, display: 'block', marginBottom: 7 }}>{t('lbl.reset.email')}</label>
                  <input
                    className="lg-input"
                    type="email"
                    value={resetEmail}
                    onChange={(e) => setResetEmail(e.target.value)}
                    placeholder={t('msg.ph.email')}
                    required
                  />
                  <button type="submit" className="lg-btn lg-btn-sub" style={{ marginTop: 10, height: 44 }}>
                    {t('btn.reset.send')}
                  </button>
                  {resetMsg && (
                    <div style={{ marginTop: 8, fontSize: 13, color: '#245F97', textAlign: 'center' }}>{resetMsg}</div>
                  )}
                </form>
              )}

              <div style={{ height: 1, background: '#eae7e1', margin: '26px 0 22px' }} />

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, fontSize: 14.5, flexWrap: 'wrap' }}>
                <span style={{ color: '#6b707a' }}>{t('lbl.login.no_account')}</span>
                {/* 회원가입 전용 페이지가 생기기 전까지 기존 회원가입 팝업을 임시 연결 */}
                <button
                  type="button"
                  className="lg-link"
                  style={{ fontSize: 14.5, fontWeight: 700, color: 'oklch(.48 .17 264)' }}
                  onClick={() => setRegisterOpen(true)}
                >
                  {t('btn.login.signup')}
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* 푸터 */}
      <div style={{
        flex: 'none', borderTop: '1px solid #e6e2da', background: '#fff', padding: '20px 24px',
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13.5 }}>
          <a className="lg-link" style={{ fontSize: 13.5 }} href={`${LEGAL_BASE}/${legalLang}/terms`} target="_blank" rel="noopener noreferrer">
            {t('lbl.login.terms')}
          </a>
          <span style={{ color: '#c3bfb7' }}>·</span>
          <a className="lg-link" style={{ fontSize: 13.5, fontWeight: 600 }} href={`${LEGAL_BASE}/${legalLang}/privacy`} target="_blank" rel="noopener noreferrer">
            {t('lbl.login.privacy')}
          </a>
          <span style={{ color: '#c3bfb7' }}>·</span>
          <a className="lg-link" style={{ fontSize: 13.5 }} href="/contact" onClick={(e) => { e.preventDefault(); navigate('/contact') }}>
            {t('lbl.login.support')}
          </a>
        </div>
        <div style={{ fontSize: 12.5, color: '#9a9ea6' }}>© 2026 D2Doc. All rights reserved.</div>
      </div>

      {/* 테넌트 선택 후 처리 중 안내 — 잠시 멈춘 것처럼 보이지 않도록 */}
      {loading && step === 'tenant' && (
        <div style={{
          position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
          background: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 10000,
        }}>
          <div style={{
            background: '#fafae5', padding: '20px 30px', borderRadius: 8, fontSize: 16, fontWeight: 'bold',
            color: '#6c757d', boxShadow: '0 2px 6px rgba(0,0,0,0.3)', display: 'flex', alignItems: 'center', gap: 12,
          }}>
            <Spin />
            <span>{t('msg.tenant.switching')}</span>
          </div>
        </div>
      )}

      <FindEmailModal open={findOpen} onClose={() => setFindOpen(false)} onContact={() => navigate('/contact')} />

      <Suspense fallback={null}>
        {registerOpen && <RegisterModal open onClose={() => setRegisterOpen(false)} />}
      </Suspense>
    </div>
  )
}
