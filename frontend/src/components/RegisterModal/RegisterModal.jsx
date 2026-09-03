import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { useLangStore, t } from '@/stores/langStore'

export default function RegisterModal({ open, onClose }) {
  const [selectedProducts, setSelectedProducts] = useState([])
  const [usernm, setUsernm] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [userinfoyn, setUserinfoyn] = useState(false)
  const [termsofuseyn, setTermsofuseyn] = useState(false)
  const [electronicfinancialtermsyn, setElectronicfinancialtermsyn] = useState(false)
  const [marketingyn, setMarketingyn] = useState(false)
  const [agreeAll, setAgreeAll] = useState(false)
  const [saving, setSaving] = useState(false)
  useLangStore((s) => s.translations)

  const { data: productsData } = useQuery({
    queryKey: ['auth-products'],
    queryFn: () => apiClient.get('/auth/products').then((r) => r.data),
    enabled: open,
  })
  const products = productsData?.products || []

  const toggleProduct = (productcd) => {
    setSelectedProducts(prev =>
      prev.includes(productcd) ? prev.filter(v => v !== productcd) : [...prev, productcd]
    )
  }

  useEffect(() => {
    if (!open) return
    setSelectedProducts([])
    setUsernm('')
    setEmail('')
    setPassword('')
    setPasswordConfirm('')
    setUserinfoyn(false)
    setTermsofuseyn(false)
    setElectronicfinancialtermsyn(false)
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
    setElectronicfinancialtermsyn(checked)
    setMarketingyn(checked)
  }

  const syncAgreeAll = (info, terms, elec, mkt) => {
    setAgreeAll(info && terms && elec && mkt)
  }

  const handleSubmit = async () => {
    if (!termsofuseyn || !userinfoyn || !electronicfinancialtermsyn) { alert(t('msg.register.terms.required')); return }
    if (!usernm) { alert(t('msg.usernm.required')); return }
    if (!email) { alert(t('msg.email.required')); return }
    if (!password) { alert(t('msg.password.required')); return }
    if (password !== passwordConfirm) { alert(t('msg.password.mismatch')); return }
    if (password.length < 8) { alert(t('msg.password.minlength')); return }
    if (selectedProducts.length === 0) { alert(t('msg.register.product.required')); return }

    setSaving(true)
    try {
      await apiClient.post('/auth/register', {
        email,
        password,
        usernm,
        accounttype: 'U',
        userinfoyn: userinfoyn ? 'Y' : 'N',
        termsofuseyn: termsofuseyn ? 'Y' : 'N',
        electronicfinancialtermsyn: electronicfinancialtermsyn ? 'Y' : 'N',
        marketingyn: marketingyn ? 'Y' : 'N',
        products: selectedProducts,
      })
      alert(t('msg.register.success'))
      onClose()
    } catch (err) {
      const detail = t(err.response?.data?.detail) || t('msg.register.failed')
      alert(detail)
    } finally {
      setSaving(false)
    }
  }

  const submitDisabled = !usernm.trim() || !email.trim() || !password.trim() || !passwordConfirm.trim() || !userinfoyn || !termsofuseyn || !electronicfinancialtermsyn

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
        maxHeight: '90vh', overflowY: 'auto',
      }}>
        <button
          onClick={onClose}
          style={{ position: 'absolute', top: 10, right: 10, background: 'transparent', border: 'none', fontSize: 20, cursor: 'pointer', lineHeight: 1 }}
        >
          &times;
        </button>

        <h2 style={{ fontWeight: 'bold', marginBottom: 20 }}>{t('ttl.register_ttl')}</h2>

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

        {/* 요금 선택 */}
        {products.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ width: 90, textAlign: 'right', fontSize: 14, fontWeight: 500, flexShrink: 0 }}>{t('lbl.services')}</span>
              <div style={{ display: 'flex', gap: 16 }}>
                {products.map(p => (
                  <label key={p.productcd} style={{ display: 'flex', alignItems: 'center', fontSize: 14, cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={selectedProducts.includes(p.productcd)}
                      onChange={() => toggleProduct(p.productcd)}
                      style={{ marginRight: 6 }}
                    />
                    {p.productnm}
                  </label>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* 전체 동의 */}
        <label style={{ display: 'block', marginBottom: 8, textAlign: 'left', fontSize: 14 }}>
          <input type="checkbox" checked={agreeAll} onChange={(e) => handleAgreeAll(e.target.checked)} style={{ marginRight: 6 }} />
          {t('lbl.agree.all')}
        </label>

        {/* 개인정보 수집·이용 동의 (필수) */}
        <label style={{ display: 'block', marginBottom: 6, textAlign: 'left', fontSize: 14 }}>
          <input type="checkbox" checked={userinfoyn}
            onChange={(e) => { setUserinfoyn(e.target.checked); syncAgreeAll(e.target.checked, termsofuseyn, electronicfinancialtermsyn, marketingyn) }}
            style={{ marginRight: 6 }} />
          <a href="/terms?terms=collection" target="_blank" style={{ color: '#0f6efd', textDecoration: 'underline' }}>{t('lbl.terms.privacy')}</a> ({t('lbl.required')})
        </label>

        {/* 서비스 이용약관 (필수) */}
        <label style={{ display: 'block', marginBottom: 6, textAlign: 'left', fontSize: 14 }}>
          <input type="checkbox" checked={termsofuseyn}
            onChange={(e) => { setTermsofuseyn(e.target.checked); syncAgreeAll(userinfoyn, e.target.checked, electronicfinancialtermsyn, marketingyn) }}
            style={{ marginRight: 6 }} />
          <a href="/terms?terms=service" target="_blank" style={{ color: '#0f6efd', textDecoration: 'underline' }}>{t('lbl.terms.service')}</a> ({t('lbl.required')})
        </label>

        {/* 전자금융거래 이용약관 (필수) */}
        <label style={{ display: 'block', marginBottom: 6, textAlign: 'left', fontSize: 14 }}>
          <input type="checkbox" checked={electronicfinancialtermsyn}
            onChange={(e) => { setElectronicfinancialtermsyn(e.target.checked); syncAgreeAll(userinfoyn, termsofuseyn, e.target.checked, marketingyn) }}
            style={{ marginRight: 6 }} />
          <a href="/terms?terms=finance" target="_blank" style={{ color: '#0f6efd', textDecoration: 'underline' }}>{t('lbl.terms.electronic')}</a> ({t('lbl.required')})
        </label>

        {/* 광고성 정보 수신 동의 (선택) */}
        <label style={{ display: 'block', marginBottom: 20, textAlign: 'left', fontSize: 14 }}>
          <input type="checkbox" checked={marketingyn}
            onChange={(e) => { setMarketingyn(e.target.checked); syncAgreeAll(userinfoyn, termsofuseyn, electronicfinancialtermsyn, e.target.checked) }}
            style={{ marginRight: 6 }} />
          <a href="/terms?terms=marketing" target="_blank" style={{ color: '#0f6efd', textDecoration: 'underline' }}>{t('lbl.terms.marketing')}</a> ({t('lbl.optional')})
        </label>

        {/* 가입 버튼 */}
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
