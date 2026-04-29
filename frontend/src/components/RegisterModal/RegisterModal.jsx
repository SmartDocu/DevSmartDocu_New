import { useEffect, useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { useLangStore, t } from '@/stores/langStore'

export default function RegisterModal({ open, onClose }) {
  const [billingmodelcd, setBillingmodelcd] = useState('single')
  const [single, setSingle] = useState('Fr')
  const [tenantid, setTenantid] = useState('')
  const [usernm, setUsernm] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [userinfoyn, setUserinfoyn] = useState(false)
  const [termsofuseyn, setTermsofuseyn] = useState(false)
  const [marketingyn, setMarketingyn] = useState(false)
  const [agreeAll, setAgreeAll] = useState(false)
  const [saving, setSaving] = useState(false)
  useLangStore((s) => s.translations)

  const { data: tenantsData } = useQuery({
    queryKey: ['tenants'],
    queryFn: () => apiClient.get('/auth/tenants').then((r) => r.data),
    enabled: open,
  })
  const tenants = tenantsData?.tenants || []

  // 모달 열릴 때 초기화
  useEffect(() => {
    if (!open) return
    setBillingmodelcd('single')
    setSingle('Fr')
    setTenantid('')
    setUsernm('')
    setEmail('')
    setPassword('')
    setPasswordConfirm('')
    setUserinfoyn(false)
    setTermsofuseyn(false)
    setMarketingyn(false)
    setAgreeAll(false)
  }, [open])

  // ESC 닫기
  useEffect(() => {
    if (!open) return
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  const handleAgreeAll = (checked) => {
    setAgreeAll(checked)
    setUserinfoyn(checked)
    setTermsofuseyn(checked)
    setMarketingyn(checked)
  }

  const syncAgreeAll = (info, terms, mkt) => {
    setAgreeAll(info && terms && mkt)
  }

  const submitDisabled = !usernm.trim() || !email.trim() || !password.trim() || !passwordConfirm.trim() || !userinfoyn || !termsofuseyn

  const handleSubmit = async () => {
    if (!termsofuseyn || !userinfoyn) { alert(t('msg.register.terms.required')); return }
    if (billingmodelcd === 'multi' && !tenantid) { alert(t('msg.register.tenant.required')); return }
    if (!usernm) { alert(t('msg.usernm.required')); return }
    if (!email) { alert(t('msg.email.required')); return }
    if (!password) { alert(t('msg.password.required')); return }
    if (password !== passwordConfirm) { alert(t('msg.password.mismatch')); return }
    if (password.length < 8) { alert(t('msg.password.minlength')); return }

    setSaving(true)
    try {
      await apiClient.post('/auth/register', {
        email,
        password,
        usernm,
        billingmodelcd,
        tenantid: billingmodelcd === 'multi' ? tenantid : undefined,
        userinfoyn: userinfoyn ? 'Y' : 'N',
        termsofuseyn: termsofuseyn ? 'Y' : 'N',
        marketingyn: marketingyn ? 'Y' : 'N',
      })
      alert(t('msg.register.success'))
      onClose()
    } catch (err) {
      const detail = err.response?.data?.detail || t('msg.register.failed')
      alert(detail)
    } finally {
      setSaving(false)
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
        width: 360, boxShadow: '0 8px 24px rgba(0,0,0,0.2)',
        textAlign: 'center', position: 'relative',
      }}>
        {/* 닫기 버튼 */}
        <button
          onClick={onClose}
          style={{ position: 'absolute', top: 10, right: 10, background: 'transparent', border: 'none', fontSize: 20, cursor: 'pointer', lineHeight: 1 }}
        >
          &times;
        </button>

        <h2 style={{ fontWeight: 'bold', marginBottom: 20 }}>{t('ttl.register_ttl')}</h2>

        {/* 사용 모델 */}
        <label style={{ display: 'flex', alignItems: 'center', marginBottom: 10, gap: 8 }}>
          <span style={{ width: 80, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>{t('lbl.billing.model')}</span>
          <div style={{ flex: 1, display: 'flex', gap: 16 }}>
            <label style={{ fontSize: 14 }}>
              <input type="radio" name="billingmodelcd" value="single" checked={billingmodelcd === 'single'}
                onChange={() => setBillingmodelcd('single')} style={{ marginRight: 4 }} />
              {t('lbl.billing.single')}
            </label>
            <label style={{ fontSize: 14 }}>
              <input type="radio" name="billingmodelcd" value="multi" checked={billingmodelcd === 'multi'}
                onChange={() => setBillingmodelcd('multi')} style={{ marginRight: 4 }} />
              {t('lbl.billing.multi')}
            </label>
          </div>
        </label>

        {/* 요금제 (개인) */}
        {billingmodelcd === 'single' && (
          <label style={{ display: 'flex', alignItems: 'center', marginBottom: 10, gap: 8 }}>
            <span style={{ width: 80, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>{t('lbl.plan')}</span>
            <select value={single} onChange={(e) => setSingle(e.target.value)}
              style={{ flex: 1, height: 36, padding: '4px 8px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }}>
              <option value="Fr">{t('lbl.plan.free')}</option>
              <option value="Pr">{t('lbl.plan.pro')}</option>
            </select>
          </label>
        )}

        {/* 기업 선택 (단체) */}
        {billingmodelcd === 'multi' && (
          <label style={{ display: 'flex', alignItems: 'center', marginBottom: 10, gap: 8 }}>
            <span style={{ width: 80, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>{t('lbl.tenant')}</span>
            <select value={tenantid} onChange={(e) => setTenantid(e.target.value)}
              style={{ flex: 1, height: 36, padding: '4px 8px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }}>
              <option value="">{t('msg.ph.tenant.select')}</option>
              {tenants.map((tn) => (
                <option key={tn.id || tn.tenantid} value={tn.id || tn.tenantid}>
                  {tn.tenantname || tn.tenantnm}
                </option>
              ))}
            </select>
          </label>
        )}

        {/* 사용자명 */}
        <label style={{ display: 'flex', alignItems: 'center', marginBottom: 10, gap: 8 }}>
          <span style={{ width: 80, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>{t('lbl.usernm')}</span>
          <input type="text" value={usernm} onChange={(e) => setUsernm(e.target.value)}
            placeholder={t('lbl.usernm')}
            style={{ flex: 1, height: 36, padding: '4px 8px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }} />
        </label>

        {/* 이메일 */}
        <label style={{ display: 'flex', alignItems: 'center', marginBottom: 10, gap: 8 }}>
          <span style={{ width: 80, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>{t('lbl.email')}</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
            placeholder={t('lbl.email')}
            style={{ flex: 1, height: 36, padding: '4px 8px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }} />
        </label>

        {/* 비밀번호 */}
        <label style={{ display: 'flex', alignItems: 'center', marginBottom: 10, gap: 8 }}>
          <span style={{ width: 80, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>{t('lbl.password')}</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
            placeholder={t('lbl.password')}
            style={{ flex: 1, height: 36, padding: '4px 8px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }} />
        </label>

        {/* 비밀번호 확인 */}
        <label style={{ display: 'flex', alignItems: 'center', marginBottom: 16, gap: 8 }}>
          <span style={{ width: 80, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>{t('lbl.password.confirm')}</span>
          <input type="password" value={passwordConfirm} onChange={(e) => setPasswordConfirm(e.target.value)}
            placeholder={t('lbl.password.confirm')}
            style={{ flex: 1, height: 36, padding: '4px 8px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }} />
        </label>

        {/* 전체 동의 */}
        <label style={{ display: 'block', marginBottom: 8, textAlign: 'left', fontSize: 14 }}>
          <input type="checkbox" checked={agreeAll} onChange={(e) => handleAgreeAll(e.target.checked)} style={{ marginRight: 6 }} />
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

        {/* 회원가입 버튼 */}
        <button
          onClick={handleSubmit}
          disabled={submitDisabled || saving}
          className="btn btn-primary"
          style={{ width: '100%', padding: '10px 0', fontSize: 15 }}
        >
          {saving ? t('btn.register.ing') : t('btn.register_btn')}
        </button>
      </div>
    </div>
  )
}
