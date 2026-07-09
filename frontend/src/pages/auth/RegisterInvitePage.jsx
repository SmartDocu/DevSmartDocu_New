import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useLangStore, t } from '@/stores/langStore'
import { useInviteInfo, useRegisterInvite } from '@/hooks/useAuth'

export default function RegisterInvitePage() {
  useLangStore((s) => s.translations)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const req = searchParams.get('req')

  const { data: invite, isLoading: infoLoading, isError } = useInviteInfo(req)

  useEffect(() => {
    if (invite?.already_registered) {
      alert(t('msg.invite.already.registered'))
      navigate('/')
    }
  }, [invite, navigate])

  const [usernm, setUsernm] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [termsofuseyn, setTermsofuseyn] = useState(false)
  const [userinfoyn, setUserinfoyn] = useState(false)
  const [marketingyn, setMarketingyn] = useState(false)
  const [agreeAll, setAgreeAll] = useState(false)
  const [saving, setSaving] = useState(false)

  const registerMutation = useRegisterInvite()

  const handleAgreeAll = (checked) => {
    setAgreeAll(checked)
    setTermsofuseyn(checked)
    setUserinfoyn(checked)
    setMarketingyn(checked)
  }

  const syncAgreeAll = (info, terms, mkt) => setAgreeAll(info && terms && mkt)

  const handleSubmit = async () => {
    if (!termsofuseyn || !userinfoyn) { alert(t('msg.register.terms.required')); return }
    if (!usernm.trim()) { alert(t('msg.usernm.required')); return }
    if (!password) { alert(t('msg.password.required')); return }
    if (password !== passwordConfirm) { alert(t('msg.password.mismatch')); return }
    if (password.length < 8) { alert(t('msg.password.minlength')); return }

    setSaving(true)
    try {
      await registerMutation.mutateAsync({
        req,
        usernm,
        password,
        password_confirm: passwordConfirm,
        termsofuseyn: termsofuseyn ? 'Y' : 'N',
        userinfoyn: userinfoyn ? 'Y' : 'N',
        marketingyn: marketingyn ? 'Y' : 'N',
      })
      alert(t('msg.register.success'))
      navigate('/')
    } catch (err) {
      alert(err.response?.data?.detail || t('msg.register.failed'))
    } finally {
      setSaving(false)
    }
  }

  const inputStyle = {
    flex: 1, height: 36, padding: '4px 8px',
    borderRadius: 4, border: '1px solid #ccc', fontSize: 14,
  }
  const roInputStyle = { ...inputStyle, backgroundColor: '#f0f0f0', color: '#555' }
  const labelStyle = { display: 'flex', alignItems: 'center', marginBottom: 10, gap: 8 }
  const labelSpanStyle = { width: 100, textAlign: 'right', fontSize: 14, fontWeight: 500, flexShrink: 0 }

  const submitDisabled = !usernm.trim() || !password || !passwordConfirm || !userinfoyn || !termsofuseyn

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: '#f0f2f5',
    }}>
      <div style={{
        background: '#fff', padding: '30px 28px', borderRadius: 12,
        width: 500, boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
        maxHeight: '90vh', overflowY: 'auto',
      }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <h2 style={{ margin: 0, fontWeight: 'bold', fontSize: 22 }}>Smart Document</h2>
          <p style={{ color: '#888', marginTop: 6, marginBottom: 0 }}>{t('ttl.register.invite')}</p>
        </div>

        {/* 초대 정보 안내 */}
        {infoLoading && (
          <p style={{ textAlign: 'center', color: '#888' }}>{t('msg.loading')}</p>
        )}
        {isError && (
          <div style={{ textAlign: 'center', marginBottom: 16 }}>
            <p style={{ color: '#ff4d4f' }}>{t('msg.invite.invalid')}</p>
            <button className="btn btn-primary" onClick={() => navigate('/')}>{t('btn.go.login')}</button>
          </div>
        )}
        {!req && (
          <div style={{ textAlign: 'center', marginBottom: 16 }}>
            <p style={{ color: '#ff4d4f' }}>{t('msg.invite.invalid')}</p>
            <button className="btn btn-primary" onClick={() => navigate('/')}>{t('btn.go.login')}</button>
          </div>
        )}

        {invite && !invite.already_registered && (
          <>
            {/* 초대 안내 배너 */}
            <div style={{
              background: '#f6ffed', border: '1px solid #b7eb8f',
              borderRadius: 6, padding: '10px 14px', marginBottom: 20, fontSize: 13,
            }}>
              <strong>{invite.tenantnm}</strong>{t('inf.invite.from')}
              {invite.servicecd && (
                <span style={{ marginLeft: 4 }}>
                  ({invite.servicecd})
                </span>
              )}
            </div>

            {/* 사용자명 */}
            <label style={labelStyle}>
              <span style={labelSpanStyle}>{t('lbl.usernm')}</span>
              <input type="text" value={usernm} onChange={(e) => setUsernm(e.target.value)}
                placeholder={t('lbl.usernm')} style={inputStyle} />
            </label>

            {/* 이메일 (읽기 전용) */}
            <label style={labelStyle}>
              <span style={labelSpanStyle}>{t('lbl.email')}</span>
              <input type="email" value={invite.email} readOnly style={roInputStyle} />
            </label>

            {/* 비밀번호 */}
            <label style={labelStyle}>
              <span style={labelSpanStyle}>{t('lbl.password')}</span>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                placeholder={t('lbl.password')} style={inputStyle} />
            </label>

            {/* 비밀번호 확인 */}
            <label style={{ ...labelStyle, marginBottom: 20 }}>
              <span style={labelSpanStyle}>{t('lbl.password.confirm')}</span>
              <input type="password" value={passwordConfirm} onChange={(e) => setPasswordConfirm(e.target.value)}
                placeholder={t('lbl.password.confirm')} style={inputStyle} />
            </label>

            {/* 전체 동의 */}
            <label style={{ display: 'block', marginBottom: 8, textAlign: 'left', fontSize: 14 }}>
              <input type="checkbox" checked={agreeAll}
                onChange={(e) => handleAgreeAll(e.target.checked)} style={{ marginRight: 6 }} />
              {t('lbl.agree.all')}
            </label>

            {/* 개인정보수집 (필수) */}
            <label style={{ display: 'block', marginBottom: 6, textAlign: 'left', fontSize: 14 }}>
              <input type="checkbox" checked={userinfoyn}
                onChange={(e) => { setUserinfoyn(e.target.checked); syncAgreeAll(e.target.checked, termsofuseyn, marketingyn) }}
                style={{ marginRight: 6 }} />
              <a href="/terms?terms=collection" target="_blank" style={{ color: '#0f6efd', textDecoration: 'underline' }}>{t('lbl.terms.privacy')}</a> ({t('lbl.required')})
            </label>

            {/* 이용약관 (필수) */}
            <label style={{ display: 'block', marginBottom: 6, textAlign: 'left', fontSize: 14 }}>
              <input type="checkbox" checked={termsofuseyn}
                onChange={(e) => { setTermsofuseyn(e.target.checked); syncAgreeAll(userinfoyn, e.target.checked, marketingyn) }}
                style={{ marginRight: 6 }} />
              <a href="/terms?terms=service" target="_blank" style={{ color: '#0f6efd', textDecoration: 'underline' }}>{t('lbl.terms.service')}</a>{t('lbl.terms.agree')} ({t('lbl.required')})
            </label>

            {/* 마케팅 (선택) */}
            <label style={{ display: 'block', marginBottom: 20, textAlign: 'left', fontSize: 14 }}>
              <input type="checkbox" checked={marketingyn}
                onChange={(e) => { setMarketingyn(e.target.checked); syncAgreeAll(userinfoyn, termsofuseyn, e.target.checked) }}
                style={{ marginRight: 6 }} />
              <a href="/terms?terms=marketing" target="_blank" style={{ color: '#0f6efd', textDecoration: 'underline' }}>{t('lbl.terms.marketing')}</a> ({t('lbl.optional')})
            </label>

            {/* 가입 버튼 */}
            <button
              onClick={handleSubmit}
              disabled={submitDisabled || saving}
              className="btn btn-primary"
              style={{ width: '100%', padding: '10px 0', fontSize: 15, marginBottom: 10 }}
            >
              {saving ? t('btn.register.ing') : t('btn.register_btn')}
            </button>

            <div style={{ textAlign: 'center' }}>
              <button
                type="button"
                onClick={() => navigate('/')}
                style={{ background: 'none', border: 'none', color: '#0f6efd', cursor: 'pointer', fontSize: 13 }}
              >
                {t('btn.back.to.login')}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
