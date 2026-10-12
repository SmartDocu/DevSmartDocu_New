import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { getErrorMessage } from '@/utils/apiError'
import { isPasswordPolicyOk } from '@/utils/passwordPolicy'
import AuthPageShell, { AUTH_NAVY as NAVY, authLabelStyle as labelStyle, authLabelTextStyle as labelTextStyle } from '@/components/Auth/AuthPageShell'

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

// 약관 항목 — key는 가입 API 필드명(…yn)과 약관 페이지 파라미터에 대응한다
const AGREEMENTS = [
  { key: 'userinfoyn', labelKey: 'lbl.terms.privacy', terms: 'collection', required: true },
  { key: 'termsofuseyn', labelKey: 'lbl.terms.service', terms: 'service', required: true },
  { key: 'electronicfinancialtermsyn', labelKey: 'lbl.terms.electronic', terms: 'finance', required: true },
  { key: 'marketingyn', labelKey: 'lbl.terms.marketing', terms: 'marketing', required: false },
]

/**
 * 회원가입 페이지(/register) — 예전 RegisterModal(팝업)을 로그인 페이지와 같은 디자인의 별도 페이지로 옮긴 것.
 * 가입 API(POST /auth/register)와 검증 규칙은 팝업 때와 동일하다.
 */
export default function RegisterPage() {
  const navigate = useNavigate()
  const languageCd = useLangStore((s) => s.languageCd)
  useLangStore((s) => s.translations)
  const alreadyLoggedIn = useAuthStore((s) => !!s.accessToken && !!s.user)

  const [usernm, setUsernm] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [agree, setAgree] = useState({})
  const [saving, setSaving] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [done, setDone] = useState(false)

  if (alreadyLoggedIn) return <Navigate to="/" replace />

  const allAgreed = AGREEMENTS.every((a) => agree[a.key])
  const requiredOk = AGREEMENTS.filter((a) => a.required).every((a) => agree[a.key])
  const submitDisabled = saving || !requiredOk || !usernm.trim() || !email.trim() || !password.trim() || !passwordConfirm.trim()

  const toggleAll = (checked) => setAgree(Object.fromEntries(AGREEMENTS.map((a) => [a.key, checked])))
  const toggleOne = (key) => setAgree((prev) => ({ ...prev, [key]: !prev[key] }))
  const clearErr = () => setErrorMsg('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setErrorMsg('')
    if (!requiredOk) { setErrorMsg(t('msg.register.terms.required')); return }
    if (!usernm.trim()) { setErrorMsg(t('msg.usernm.required')); return }
    if (!EMAIL_REGEX.test(email.trim())) { setErrorMsg(t('msg.email.invalid')); return }
    if (!password) { setErrorMsg(t('msg.password.required')); return }
    if (password !== passwordConfirm) { setErrorMsg(t('msg.password.mismatch')); return }
    if (!isPasswordPolicyOk(password)) { setErrorMsg(t('msg.password.policy')); return }

    setSaving(true)
    try {
      await apiClient.post('/auth/register', {
        email: email.trim(),
        password,
        usernm: usernm.trim(),
        accounttype: 'U',
        userinfoyn: agree.userinfoyn ? 'Y' : 'N',
        termsofuseyn: agree.termsofuseyn ? 'Y' : 'N',
        electronicfinancialtermsyn: agree.electronicfinancialtermsyn ? 'Y' : 'N',
        marketingyn: agree.marketingyn ? 'Y' : 'N',
        languagecd: languageCd,
      })
      setDone(true)
    } catch (err) {
      setErrorMsg(getErrorMessage(err, 'msg.register.failed'))
    } finally {
      setSaving(false)
    }
  }

  if (done) {
    return (
      <AuthPageShell>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14, textAlign: 'center' }}>
          <div style={{ width: 52, height: 52, borderRadius: '50%', background: '#e8f5ec', color: '#2f7d4f', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M5 12.5l4.5 4.5L19 7.5"></path></svg>
          </div>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, letterSpacing: '-.03em' }}>{t('ttl.register_ttl')}</h1>
          <p style={{ margin: 0, fontSize: 14.5, lineHeight: 1.7, color: '#4b5058' }}>{t('msg.register.success')}</p>
        </div>
        <button type="button" className="lg-btn" style={{ marginTop: 26 }} onClick={() => navigate('/login', { replace: true })}>
          {t('btn.register.to_login')}
        </button>
      </AuthPageShell>
    )
  }

  const field = (label, value, setter, type = 'text', auto) => (
    <label style={labelStyle}>
      <span style={labelTextStyle}>{label}</span>
      <input
        className="lg-input"
        style={{ height: 42 }}
        type={type}
        autoComplete={auto}
        value={value}
        disabled={saving}
        onChange={(e) => { setter(e.target.value); clearErr() }}
      />
    </label>
  )

  return (
    <AuthPageShell cardMaxWidth={640} compact>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
        <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, letterSpacing: '-.03em' }}>{t('ttl.register_ttl')}</h1>
        <p style={{ margin: 0, fontSize: 14, color: '#6b707a' }}>{t('inf.register.subtitle')}</p>
      </div>

      <form onSubmit={handleSubmit} noValidate>
        {/* 입력 항목은 2열로 배치해 세로 길이를 줄인다(좁은 화면에서는 자동으로 1열) */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '10px 14px', marginTop: 20 }}>
          {field(t('lbl.usernm'), usernm, setUsernm, 'text', 'name')}
          {field(t('lbl.email'), email, setEmail, 'email', 'username')}
          {field(t('lbl.password'), password, setPassword, 'password', 'new-password')}
          {field(t('lbl.password.confirm'), passwordConfirm, setPasswordConfirm, 'password', 'new-password')}
        </div>
        <div style={{ marginTop: 6, fontSize: 12.5, color: '#8d9199' }}>{t('inf.password.policy')}</div>

        {/* 약관 동의 */}
        <div style={{ marginTop: 14, padding: '10px 14px', border: '1px solid #e6e2da', borderRadius: 12, background: '#faf9f6' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 9, cursor: 'pointer', fontWeight: 700, fontSize: 14 }}>
            <input
              type="checkbox"
              checked={allAgreed}
              disabled={saving}
              onChange={(e) => { toggleAll(e.target.checked); clearErr() }}
              style={{ width: 17, height: 17, margin: 0, accentColor: NAVY, cursor: 'pointer' }}
            />
            {t('lbl.agree.all')}
          </label>
          <div style={{ height: 1, background: '#eae7e1', margin: '8px 0' }} />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '8px 14px' }}>
            {AGREEMENTS.map((a) => (
              <label key={a.key} style={{ display: 'flex', alignItems: 'center', gap: 9, cursor: 'pointer', fontSize: 14 }}>
                <input
                  type="checkbox"
                  checked={!!agree[a.key]}
                  disabled={saving}
                  onChange={() => { toggleOne(a.key); clearErr() }}
                  style={{ width: 17, height: 17, margin: 0, accentColor: NAVY, cursor: 'pointer', flex: 'none' }}
                />
                <span>
                  <a
                    href={`/terms?terms=${a.terms}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    style={{ color: 'oklch(.48 .17 264)', textDecoration: 'underline' }}
                  >{t(a.labelKey)}</a>{' '}
                  <span style={{ color: a.required ? 'oklch(.5 .16 25)' : '#8d9199', fontSize: 12.5, fontWeight: 600 }}>
                    ({a.required ? t('lbl.required') : t('lbl.optional')})
                  </span>
                </span>
              </label>
            ))}
          </div>
        </div>

        {errorMsg && (
          <div style={{
            marginTop: 12, padding: '8px 12px', borderRadius: 9,
            background: 'oklch(.97 .02 25)', border: '1px solid oklch(.9 .05 25)',
            fontSize: 13.5, color: 'oklch(.45 .15 25)',
          }}>
            {errorMsg}
          </div>
        )}

        <button type="submit" className="lg-btn" style={{ marginTop: 16, height: 46 }} disabled={submitDisabled}>
          {saving ? t('btn.register.ing') : t('btn.register_btn')}
        </button>
      </form>

      <div style={{ height: 1, background: '#eae7e1', margin: '16px 0 14px' }} />

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, fontSize: 14.5, flexWrap: 'wrap' }}>
        <span style={{ color: '#6b707a' }}>{t('lbl.register.have_account')}</span>
        <button
          type="button"
          className="lg-link"
          style={{ fontSize: 14.5, fontWeight: 700, color: 'oklch(.48 .17 264)' }}
          onClick={() => navigate('/login')}
        >
          {t('btn.login_btn')}
        </button>
      </div>
    </AuthPageShell>
  )
}
