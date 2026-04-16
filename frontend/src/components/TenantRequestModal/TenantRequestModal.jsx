/**
 * TenantRequestModal — 기업 등록 / 기업 등록 요청
 * type='teams' → 즉시 기업 생성 (로그인 필요)
 * type='tenant' → 요청 저장 (로그인 불필요)
 * _old_ref/pages/templates/pages/master_tenant_request.html 참조
 */
import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import apiClient from '@/api/client'

export default function TenantRequestModal({ open, onClose, type }) {
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const isLoggedIn = !!user

  const [billingusercnt, setBillingusercnt] = useState('')
  const [llmlimityn,     setLlmlimityn]     = useState('false')
  const [tenantnm,       setTenantnm]       = useState('')
  const [bizregno,       setBizregno]       = useState('')
  const [managernm,      setManagernm]      = useState('')
  const [managerdepart,  setManagerdepart]  = useState('')
  const [managerposition,setManagerposition]= useState('')
  const [email,          setEmail]          = useState('')
  const [telno,          setTelno]          = useState('')
  const [bizregFileName, setBizregFileName] = useState('사업자 등록증 사본 파일 없음')
  const [iconFileName,   setIconFileName]   = useState('이미지 파일 없음')
  const [loading,        setLoading]        = useState(false)

  const bizregFileRef = useRef(null)
  const iconFileRef   = useRef(null)

  const isTenant = type === 'tenant'
  const isTeams  = type === 'teams'

  // 전화번호 자동 포맷
  const formatTelno = (value) => {
    const v = value.replace(/[^0-9]/g, '')
    if (v.startsWith('02')) {
      if (v.length <= 2)  return v
      if (v.length <= 6)  return v.replace(/(\d{2})(\d{1,4})/, '$1-$2')
      if (v.length <= 10) return v.replace(/(\d{2})(\d{3,4})(\d{1,4})/, '$1-$2-$3')
      return v.replace(/(\d{2})(\d{4})(\d{4})/, '$1-$2-$3')
    } else {
      if (v.length <= 3)  return v
      if (v.length <= 6)  return v.replace(/(\d{3})(\d{1,3})/, '$1-$2')
      if (v.length <= 10) return v.replace(/(\d{3})(\d{3,4})(\d{1,4})/, '$1-$2-$3')
      return v.replace(/(\d{3})(\d{4})(\d{1,4})/, '$1-$2-$3')
    }
  }

  const resetForm = () => {
    setBillingusercnt(''); setLlmlimityn('false'); setTenantnm(''); setBizregno('')
    setManagernm(''); setManagerdepart(''); setManagerposition('')
    setEmail(''); setTelno('')
    setBizregFileName('사업자 등록증 사본 파일 없음'); setIconFileName('이미지 파일 없음')
    if (bizregFileRef.current) bizregFileRef.current.value = ''
    if (iconFileRef.current)   iconFileRef.current.value   = ''
  }

  const handleClose = () => { resetForm(); onClose() }

  const handleSave = async () => {
    if (isTeams && !isLoggedIn) {
      alert('기업 등록은 로그인 후 이용하실 수 있습니다.')
      handleClose()
      navigate('/')
      return
    }
    if (!tenantnm.trim()) { alert('회사(법인) 명칭을 입력해주세요.'); return }
    if (!managernm.trim()) { alert('담당자 성명을 입력해주세요.'); return }
    if (!email.trim()) { alert('이메일주소를 입력해주세요.'); return }
    if (!billingusercnt) { alert('사용자수를 입력해주세요.'); return }

    setLoading(true)
    try {
      const fd = new FormData()
      fd.append('type',           type)
      fd.append('billingusercnt', billingusercnt)
      fd.append('llmlimityn',     llmlimityn)
      fd.append('tenantnm',       tenantnm)
      fd.append('managernm',      managernm)
      fd.append('email',          email)
      fd.append('telno',          telno)
      if (isTenant) {
        fd.append('bizregno',        bizregno)
        fd.append('managerdepart',   managerdepart)
        fd.append('managerposition', managerposition)
        if (bizregFileRef.current?.files[0]) fd.append('bizregfile', bizregFileRef.current.files[0])
      }
      if (isTeams && iconFileRef.current?.files[0]) {
        fd.append('iconfile', iconFileRef.current.files[0])
      }

      const res = await apiClient.post('/misc/tenant-requests', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })

      if (isTenant) {
        alert('기업 등록 요청을 완료하였습니다.')
      } else {
        alert('기업 등록하였습니다.')
      }
      handleClose()
    } catch (err) {
      const detail = err.response?.data?.detail || err.response?.data?.message || '저장 중 오류가 발생했습니다.'
      alert(detail)
    } finally {
      setLoading(false)
    }
  }

  if (!open) return null

  const labelStyle = { width: 180, flexShrink: 0, fontSize: 14 }
  const inputStyle = { width: 200, height: 28, padding: '2px 6px', fontSize: 13, border: '1px solid #ccc', borderRadius: 3, textAlign: 'right' }

  return (
    <div
      style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 9999,
      }}
      onClick={(e) => { if (e.target === e.currentTarget) handleClose() }}
    >
      <div style={{
        background: '#fff', padding: '30px 28px', borderRadius: 12,
        width: 680, maxHeight: '90vh', overflowY: 'auto',
        boxShadow: '0 8px 24px rgba(0,0,0,0.2)', position: 'relative',
      }}>
        {/* 닫기 */}
        <button
          onClick={handleClose}
          style={{ position: 'absolute', top: 10, right: 14, background: 'transparent', border: 'none', fontSize: 22, cursor: 'pointer', lineHeight: 1 }}
        >×</button>

        {/* 타이틀 */}
        <div className="page-title" style={{ marginBottom: 16, paddingBottom: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <div className="gradient-bar" />
            <div style={{ fontSize: 17, fontWeight: 700 }}>기업 등록{isTenant ? ' 요청' : ''}</div>
          </div>
        </div>

        {/* 안내 */}
        <div className="info" style={{ textAlign: 'center', marginBottom: 16 }}>
          {isTenant ? (
            <>
              <p style={{ margin: '4px 0', fontSize: 13 }}>Enterprise의 경우는 지정 서버 작업이 완료된 후 안내에 따라 사용하실 수 있습니다.</p>
              <p style={{ margin: '4px 0', fontSize: 13 }}>Enterprise는 20인 이상인 경우에 선택하실 수 있습니다.</p>
            </>
          ) : (
            <p style={{ margin: '4px 0', fontSize: 13 }}>Teams 는 기업을 등록 후 사용자 등록하여 사용하실 수 있습니다.</p>
          )}
        </div>

        <div style={{ display: 'flex', gap: 30 }}>
          {/* 좌측: LLM 상세 + 기업 정보 */}
          <div style={{ flex: 1 }}>
            <h3 style={{ fontSize: 15, marginBottom: 12 }}>LLM 상세</h3>

            <div className="form-group-left" style={{ marginBottom: 10 }}>
              <label style={labelStyle}>사용 모델:</label>
              <label style={{ fontSize: 13, fontWeight: 600 }}>{isTenant ? 'Enterprise' : 'Teams'}</label>
            </div>

            <div className="form-group-left" style={{ marginBottom: 10 }}>
              <label style={labelStyle}>사용자수:</label>
              <input
                type="number"
                value={billingusercnt}
                onChange={(e) => setBillingusercnt(e.target.value)}
                placeholder="예: 10"
                style={inputStyle}
              />
              <span style={{ marginLeft: 8, fontSize: 12, color: '#666' }}>＊ 월 동안 사용 가능했던 전체 사용자</span>
            </div>

            <div className="form-group-left" style={{ marginBottom: 10 }}>
              <label style={labelStyle}>요금(원) / 월:</label>
              <input
                type="text"
                value={isTenant ? '100,000' : '50,000'}
                disabled
                style={{ ...inputStyle, background: '#f5f5f5' }}
              />
            </div>

            <div className="form-group-left" style={{ marginBottom: 10, alignItems: 'flex-start' }}>
              <label style={labelStyle}>LLM 추가 사용 제한:</label>
              <div style={{ fontSize: 13 }}>
                <label style={{ marginRight: 12 }}>
                  <input type="radio" name="llmlimityn" value="false" checked={llmlimityn === 'false'} onChange={() => setLlmlimityn('false')} style={{ marginRight: 4 }} />
                  미제한
                </label>
                <label>
                  <input type="radio" name="llmlimityn" value="true" checked={llmlimityn === 'true'} onChange={() => setLlmlimityn('true')} style={{ marginRight: 4 }} />
                  제한
                </label>
                <p style={{ fontSize: 11, color: '#666', margin: '4px 0 0' }}>＊ 제한: 월 인당 100만 토큰 초과시 수행 불가</p>
                <p style={{ fontSize: 11, color: '#666', margin: 0 }}>＊ 미제한: 초과 시 100만 토큰당 5,000원/월 추가</p>
              </div>
            </div>

            <h3 style={{ fontSize: 15, margin: '16px 0 12px' }}>기업 정보</h3>

            <div className="form-group-left" style={{ marginBottom: 10 }}>
              <label style={labelStyle}>회사(법인) 명칭:</label>
              <input type="text" value={tenantnm} onChange={(e) => setTenantnm(e.target.value)} style={inputStyle} />
            </div>

            {isTenant && (
              <div className="form-group-left" style={{ marginBottom: 10 }}>
                <label style={labelStyle}>법인(사업자) 등록번호:</label>
                <input
                  type="text"
                  value={bizregno}
                  onChange={(e) => setBizregno(e.target.value.replace(/[^0-9]/g, ''))}
                  style={inputStyle}
                />
              </div>
            )}

            {isTeams && (
              <div className="form-group-left" style={{ marginBottom: 10, alignItems: 'center' }}>
                <label style={labelStyle}>기업 이미지:</label>
                <input type="file" ref={iconFileRef} style={{ display: 'none' }} accept="image/*"
                  onChange={(e) => setIconFileName(e.target.files[0]?.name || '이미지 파일 없음')} />
                <button type="button" className="icon-btn" onClick={() => iconFileRef.current?.click()}>
                  <div className="icon-wrapper">
                    <img src="/icons/upload.svg" className="icon-img new-icon" alt="업로드" />
                  </div>
                </button>
                <span style={{ fontSize: 13, marginLeft: 8 }}>{iconFileName}</span>
              </div>
            )}

            {isTenant && (
              <div className="form-group-left" style={{ marginBottom: 10, alignItems: 'center' }}>
                <label style={labelStyle}>사업자 등록증 사본:</label>
                <input type="file" ref={bizregFileRef} style={{ display: 'none' }} accept=".pdf,.jpg,.png"
                  onChange={(e) => setBizregFileName(e.target.files[0]?.name || '사업자 등록증 사본 파일 없음')} />
                <button type="button" className="icon-btn" onClick={() => bizregFileRef.current?.click()}>
                  <div className="icon-wrapper">
                    <img src="/icons/upload.svg" className="icon-img new-icon" alt="업로드" />
                  </div>
                </button>
                <span style={{ fontSize: 13, marginLeft: 8 }}>{bizregFileName}</span>
              </div>
            )}
          </div>

          {/* 우측: 서비스 담당자 정보 */}
          <div style={{ flex: 1 }}>
            <h3 style={{ fontSize: 15, marginBottom: 12 }}>서비스 담당자 정보</h3>

            <div className="form-group-left" style={{ marginBottom: 10 }}>
              <label style={labelStyle}>성명:</label>
              <input type="text" value={managernm} onChange={(e) => setManagernm(e.target.value)} style={inputStyle} />
            </div>

            {isTenant && (
              <>
                <div className="form-group-left" style={{ marginBottom: 10 }}>
                  <label style={labelStyle}>부서:</label>
                  <input type="text" value={managerdepart} onChange={(e) => setManagerdepart(e.target.value)} style={inputStyle} />
                </div>
                <div className="form-group-left" style={{ marginBottom: 10 }}>
                  <label style={labelStyle}>직책:</label>
                  <input type="text" value={managerposition} onChange={(e) => setManagerposition(e.target.value)} style={inputStyle} />
                </div>
              </>
            )}

            <div className="form-group-left" style={{ marginBottom: 10 }}>
              <label style={labelStyle}>이메일주소:</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} style={inputStyle} />
            </div>

            <div className="form-group-left" style={{ marginBottom: 10 }}>
              <label style={labelStyle}>전화번호:</label>
              <input
                type="tel"
                value={telno}
                onChange={(e) => setTelno(formatTelno(e.target.value))}
                placeholder="숫자만 입력"
                style={inputStyle}
              />
            </div>
          </div>
        </div>

        {/* 저장 버튼 */}
        <div className="button-group" style={{ marginTop: 20, justifyContent: 'center' }}>
          <button
            type="button"
            className="icon-btn"
            onClick={handleSave}
            disabled={loading}
          >
            <div className="icon-wrapper">
              <img src="/icons/save.svg" className="icon-img save-icon" alt="저장" />
              <span className="icon-label">{loading ? '처리 중...' : '저장'}</span>
            </div>
          </button>
        </div>

        {/* 로딩 오버레이 */}
        {loading && (
          <div style={{
            position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(255,255,255,0.7)', borderRadius: 12,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 10,
          }}>
            <div className="loading-content">
              <div className="spinner" />
              <div style={{ textAlign: 'center', marginTop: 8 }}>기업 생성 중</div>
              <div>잠시만 기다려 주세요.</div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
