import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { useLangStore, t } from '@/stores/langStore'

const SERVICE_LABELS = { Do: 'Doc', Ch: 'Chat', In: 'Insight' }

export default function RegisterModal({ open, onClose }) {
  const [step, setStep] = useState(1)
  const [accounttype, setAccounttype] = useState('U')
  const [tenantid, setTenantid] = useState('')
  const [selectedProducts, setSelectedProducts] = useState({})
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

  const { data: productsData } = useQuery({
    queryKey: ['auth-products'],
    queryFn: () => apiClient.get('/auth/products').then((r) => r.data),
    enabled: open && accounttype === 'U',
  })
  const products = productsData?.products || []

  const productsByService = products.reduce((acc, p) => {
    if (!acc[p.servicecd]) acc[p.servicecd] = []
    acc[p.servicecd].push(p)
    return acc
  }, {})

  useEffect(() => {
    if (!open) return
    setStep(1)
    setAccounttype('U')
    setTenantid('')
    setSelectedProducts({})
    setUsernm('')
    setEmail('')
    setPassword('')
    setPasswordConfirm('')
    setUserinfoyn(false)
    setTermsofuseyn(false)
    setMarketingyn(false)
    setAgreeAll(false)
  }, [open])

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

  const validateStep1 = () => {
    if (!termsofuseyn || !userinfoyn) { alert(t('msg.register.terms.required')); return false }
    if (accounttype === 'T' && !tenantid) { alert(t('msg.register.tenant.required')); return false }
    if (!usernm) { alert(t('msg.usernm.required')); return false }
    if (!email) { alert(t('msg.email.required')); return false }
    if (!password) { alert(t('msg.password.required')); return false }
    if (password !== passwordConfirm) { alert(t('msg.password.mismatch')); return false }
    if (password.length < 8) { alert(t('msg.password.minlength')); return false }
    return true
  }

  const handleNext = () => {
    if (!validateStep1()) return
    setStep(2)
  }

  const handleSubmit = async () => {
    if (!validateStep1()) return

    const selectedProductCds = Object.values(selectedProducts).filter(v => v)

    setSaving(true)
    try {
      await apiClient.post('/auth/register', {
        email,
        password,
        usernm,
        accounttype,
        tenantid: accounttype === 'T' ? tenantid : undefined,
        userinfoyn: userinfoyn ? 'Y' : 'N',
        termsofuseyn: termsofuseyn ? 'Y' : 'N',
        marketingyn: marketingyn ? 'Y' : 'N',
        products: selectedProductCds.length > 0 ? selectedProductCds : undefined,
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

  const step1Disabled = !usernm.trim() || !email.trim() || !password.trim() || !passwordConfirm.trim() || !userinfoyn || !termsofuseyn

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
        width: 480, boxShadow: '0 8px 24px rgba(0,0,0,0.2)',
        textAlign: 'center', position: 'relative',
      }}>
        <button
          onClick={onClose}
          style={{ position: 'absolute', top: 10, right: 10, background: 'transparent', border: 'none', fontSize: 20, cursor: 'pointer', lineHeight: 1 }}
        >
          &times;
        </button>

        <h2 style={{ fontWeight: 'bold', marginBottom: 12 }}>{t('ttl.register_ttl')}</h2>

        {/* 단계 표시 (U 타입만) */}
        {accounttype === 'U' && (
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 8, marginBottom: 20 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <div style={{
                width: 24, height: 24, borderRadius: '50%', fontSize: 12, fontWeight: 600,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: step === 1 ? '#0f6efd' : '#dee2e6',
                color: step === 1 ? '#fff' : '#6c757d',
              }}>1</div>
              <span style={{ fontSize: 12, color: step === 1 ? '#0f6efd' : '#6c757d', fontWeight: step === 1 ? 600 : 400 }}>
                {t('lbl.register.step1')}
              </span>
            </div>
            <div style={{ width: 32, height: 1, background: '#dee2e6' }} />
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <div style={{
                width: 24, height: 24, borderRadius: '50%', fontSize: 12, fontWeight: 600,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: step === 2 ? '#0f6efd' : '#dee2e6',
                color: step === 2 ? '#fff' : '#6c757d',
              }}>2</div>
              <span style={{ fontSize: 12, color: step === 2 ? '#0f6efd' : '#6c757d', fontWeight: step === 2 ? 600 : 400 }}>
                {t('lbl.register.step2')}
              </span>
            </div>
          </div>
        )}

        {/* ── 1단계: 기본 정보 ─────────────────────────────────────────── */}
        {step === 1 && (
          <>
            {/* 사용 모델 */}
            <label style={{ display: 'flex', alignItems: 'center', marginBottom: 10, gap: 8 }}>
              <span style={{ width: 90, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>{t('lbl.billing.model')}</span>
              <div style={{ flex: 1, display: 'flex', gap: 16 }}>
                <label style={{ fontSize: 14 }}>
                  <input type="radio" name="accounttype" value="U" checked={accounttype === 'U'}
                    onChange={() => setAccounttype('U')} style={{ marginRight: 4 }} />
                  {t('lbl.billing.single')}
                </label>
                <label style={{ fontSize: 14 }}>
                  <input type="radio" name="accounttype" value="T" checked={accounttype === 'T'}
                    onChange={() => setAccounttype('T')} style={{ marginRight: 4 }} />
                  {t('lbl.billing.multi')}
                </label>
              </div>
            </label>

            {/* 기업 선택 (단체) */}
            {accounttype === 'T' && (
              <label style={{ display: 'flex', alignItems: 'center', marginBottom: 10, gap: 8 }}>
                <span style={{ width: 90, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>{t('lbl.tenant')}</span>
                <select value={tenantid} onChange={(e) => setTenantid(e.target.value)}
                  style={{ flex: 1, height: 36, padding: '4px 8px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }}>
                  <option value="">{t('msg.register.tenant.required')}</option>
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
              <span style={{ width: 90, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>{t('lbl.usernm')}</span>
              <input type="text" value={usernm} onChange={(e) => setUsernm(e.target.value)}
                placeholder={t('lbl.usernm')}
                style={{ flex: 1, height: 36, padding: '4px 8px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }} />
            </label>

            {/* 이메일 */}
            <label style={{ display: 'flex', alignItems: 'center', marginBottom: 10, gap: 8 }}>
              <span style={{ width: 90, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>{t('lbl.email')}</span>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                placeholder={t('lbl.email')}
                style={{ flex: 1, height: 36, padding: '4px 8px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }} />
            </label>

            {/* 비밀번호 */}
            <label style={{ display: 'flex', alignItems: 'center', marginBottom: 10, gap: 8 }}>
              <span style={{ width: 90, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>{t('lbl.password')}</span>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                placeholder={t('lbl.password')}
                style={{ flex: 1, height: 36, padding: '4px 8px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }} />
            </label>

            {/* 비밀번호 확인 */}
            <label style={{ display: 'flex', alignItems: 'center', marginBottom: 16, gap: 8 }}>
              <span style={{ width: 90, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>{t('lbl.password.confirm')}</span>
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

            {/* 버튼 */}
            {accounttype === 'U' ? (
              <button
                onClick={handleNext}
                disabled={step1Disabled}
                className="btn btn-primary"
                style={{ width: '100%', padding: '10px 0', fontSize: 15 }}
              >
                {t('btn.next')} →
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                disabled={step1Disabled || saving}
                className="btn btn-primary"
                style={{ width: '100%', padding: '10px 0', fontSize: 15 }}
              >
                {saving ? t('btn.register.ing') : t('btn.register_btn')}
              </button>
            )}
          </>
        )}

        {/* ── 2단계: 요금 선택 ─────────────────────────────────────────── */}
        {step === 2 && (
          <>
            <p style={{ fontSize: 13, color: '#6c757d', marginBottom: 20 }}>
              {t('inf.register.plan.desc')}
            </p>

            {Object.keys(productsByService).length > 0 ? (
              Object.entries(productsByService).map(([servicecd, prods]) => (
                <label key={servicecd} style={{ display: 'flex', alignItems: 'center', marginBottom: 12, gap: 8 }}>
                  <span style={{ width: 90, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>
                    {SERVICE_LABELS[servicecd] || servicecd}
                  </span>
                  <select
                    value={selectedProducts[servicecd] || ''}
                    onChange={(e) => setSelectedProducts(prev => ({ ...prev, [servicecd]: e.target.value }))}
                    style={{ flex: 1, height: 36, padding: '4px 8px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }}
                  >
                    <option value="">{t('lbl.none')}</option>
                    {prods.map(p => (
                      <option key={p.productcd} value={p.productcd}>{p.productnm}</option>
                    ))}
                  </select>
                </label>
              ))
            ) : (
              <p style={{ color: '#6c757d', fontSize: 14 }}>Loading...</p>
            )}

            {/* 버튼 */}
            <div style={{ display: 'flex', gap: 8, marginTop: 24 }}>
              <button
                onClick={() => setStep(1)}
                className="btn btn-outline-secondary"
                style={{ flex: 1, padding: '10px 0', fontSize: 15 }}
              >
                ← {t('btn.prev')}
              </button>
              <button
                onClick={handleSubmit}
                disabled={saving}
                className="btn btn-primary"
                style={{ flex: 2, padding: '10px 0', fontSize: 15 }}
              >
                {saving ? t('btn.register.ing') : t('btn.register_btn')}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
