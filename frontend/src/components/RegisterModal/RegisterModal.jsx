import { useEffect, useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import apiClient from '@/api/client'

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
    if (!termsofuseyn || !userinfoyn) { alert('필수 약관에 동의 하셔야 합니다.'); return }
    if (billingmodelcd === 'multi' && !tenantid) { alert('단체는 기업 선택이 필수입니다.'); return }
    if (!usernm) { alert('이름을 입력해주세요.'); return }
    if (!email) { alert('이메일을 입력해주세요.'); return }
    if (!password) { alert('비밀번호를 입력해주세요.'); return }
    if (password !== passwordConfirm) { alert('비밀번호가 일치하지 않습니다.'); return }
    if (password.length < 8) { alert('비밀번호는 최소 8자 이상이어야 합니다.'); return }

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
      alert('회원가입이 완료되었습니다.')
      onClose()
    } catch (err) {
      const detail = err.response?.data?.detail || '회원가입에 실패했습니다.'
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

        <h2 style={{ fontWeight: 'bold', marginBottom: 20 }}>SmartDocu 회원가입</h2>

        {/* 사용 모델 */}
        <label style={{ display: 'flex', alignItems: 'center', marginBottom: 10, gap: 8 }}>
          <span style={{ width: 80, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>사용 모델</span>
          <div style={{ flex: 1, display: 'flex', gap: 16 }}>
            <label style={{ fontSize: 14 }}>
              <input type="radio" name="billingmodelcd" value="single" checked={billingmodelcd === 'single'}
                onChange={() => setBillingmodelcd('single')} style={{ marginRight: 4 }} />
              개인
            </label>
            <label style={{ fontSize: 14 }}>
              <input type="radio" name="billingmodelcd" value="multi" checked={billingmodelcd === 'multi'}
                onChange={() => setBillingmodelcd('multi')} style={{ marginRight: 4 }} />
              단체
            </label>
          </div>
        </label>

        {/* 요금제 (개인) */}
        {billingmodelcd === 'single' && (
          <label style={{ display: 'flex', alignItems: 'center', marginBottom: 10, gap: 8 }}>
            <span style={{ width: 80, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>요금제</span>
            <select value={single} onChange={(e) => setSingle(e.target.value)}
              style={{ flex: 1, height: 36, padding: '4px 8px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }}>
              <option value="Fr">Free 사용자</option>
              <option value="Pr">Pro 사용자</option>
            </select>
          </label>
        )}

        {/* 기업 선택 (단체) */}
        {billingmodelcd === 'multi' && (
          <label style={{ display: 'flex', alignItems: 'center', marginBottom: 10, gap: 8 }}>
            <span style={{ width: 80, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>기업</span>
            <select value={tenantid} onChange={(e) => setTenantid(e.target.value)}
              style={{ flex: 1, height: 36, padding: '4px 8px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }}>
              <option value="">기업을 선택하세요</option>
              {tenants.map((t) => (
                <option key={t.id || t.tenantid} value={t.id || t.tenantid}>
                  {t.tenantname || t.tenantnm}
                </option>
              ))}
            </select>
          </label>
        )}

        {/* 사용자명 */}
        <label style={{ display: 'flex', alignItems: 'center', marginBottom: 10, gap: 8 }}>
          <span style={{ width: 80, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>사용자명</span>
          <input type="text" value={usernm} onChange={(e) => setUsernm(e.target.value)}
            placeholder="사용자명"
            style={{ flex: 1, height: 36, padding: '4px 8px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }} />
        </label>

        {/* 이메일 */}
        <label style={{ display: 'flex', alignItems: 'center', marginBottom: 10, gap: 8 }}>
          <span style={{ width: 80, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>이메일</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
            placeholder="이메일"
            style={{ flex: 1, height: 36, padding: '4px 8px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }} />
        </label>

        {/* 비밀번호 */}
        <label style={{ display: 'flex', alignItems: 'center', marginBottom: 10, gap: 8 }}>
          <span style={{ width: 80, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>비밀번호</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
            placeholder="비밀번호"
            style={{ flex: 1, height: 36, padding: '4px 8px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }} />
        </label>

        {/* 비밀번호 확인 */}
        <label style={{ display: 'flex', alignItems: 'center', marginBottom: 16, gap: 8 }}>
          <span style={{ width: 80, textAlign: 'right', fontSize: 14, fontWeight: 500 }}>비밀번호<br />확인</span>
          <input type="password" value={passwordConfirm} onChange={(e) => setPasswordConfirm(e.target.value)}
            placeholder="비밀번호 확인"
            style={{ flex: 1, height: 36, padding: '4px 8px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }} />
        </label>

        {/* 전체 동의 */}
        <label style={{ display: 'block', marginBottom: 8, textAlign: 'left', fontSize: 14 }}>
          <input type="checkbox" checked={agreeAll} onChange={(e) => handleAgreeAll(e.target.checked)} style={{ marginRight: 6 }} />
          전체 동의합니다.
        </label>

        {/* 개인정보수집 (필수) */}
        <label style={{ display: 'block', marginBottom: 6, textAlign: 'left', fontSize: 14 }}>
          <input type="checkbox" checked={userinfoyn}
            onChange={(e) => { setUserinfoyn(e.target.checked); syncAgreeAll(e.target.checked, termsofuseyn, marketingyn) }}
            style={{ marginRight: 6 }} />
          <a href="/terms?terms=collection" target="_blank" style={{ color: '#0f6efd', textDecoration: 'underline' }}>개인정보수집동의여부</a> (필수)
        </label>

        {/* 이용약관 (필수) */}
        <label style={{ display: 'block', marginBottom: 6, textAlign: 'left', fontSize: 14 }}>
          <input type="checkbox" checked={termsofuseyn}
            onChange={(e) => { setTermsofuseyn(e.target.checked); syncAgreeAll(userinfoyn, e.target.checked, marketingyn) }}
            style={{ marginRight: 6 }} />
          <a href="/terms?terms=service" target="_blank" style={{ color: '#0f6efd', textDecoration: 'underline' }}>SmartDocu 이용약관</a>에 동의합니다. (필수)
        </label>

        {/* 마케팅 (선택) */}
        <label style={{ display: 'block', marginBottom: 20, textAlign: 'left', fontSize: 14 }}>
          <input type="checkbox" checked={marketingyn}
            onChange={(e) => { setMarketingyn(e.target.checked); syncAgreeAll(userinfoyn, termsofuseyn, e.target.checked) }}
            style={{ marginRight: 6 }} />
          <a href="/terms?terms=marketing" target="_blank" style={{ color: '#0f6efd', textDecoration: 'underline' }}>마케팅동의여부</a> (선택)
        </label>

        {/* 회원가입 버튼 */}
        <button
          onClick={handleSubmit}
          disabled={submitDisabled || saving}
          className="btn btn-primary"
          style={{ width: '100%', padding: '10px 0', fontSize: 15 }}
        >
          {saving ? '가입 중...' : '회원가입'}
        </button>
      </div>
    </div>
  )
}
