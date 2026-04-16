import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import RegisterModal from '@/components/RegisterModal/RegisterModal'
import TenantRequestModal from '@/components/TenantRequestModal/TenantRequestModal'

const cardStyle = {
  background: '#f7f9fc',
  border: '1px solid #d8dfeb',
  borderRadius: 12,
  padding: '30px 20px',
  textAlign: 'center',
  boxShadow: '0 2px 5px rgba(0,0,0,0.05)',
  transition: '0.25s',
  display: 'flex',
  flexDirection: 'column',
  justifyContent: 'space-between',
  height: 350,
  width: 250,
}

const btnStyle = {
  display: 'block',
  backgroundColor: 'var(--primary-600, #245F97)',
  color: 'var(--border-color, #fff)',
  padding: '8px 12px',
  borderRadius: 4,
  fontSize: 14,
  cursor: 'pointer',
  border: 'none',
  width: '100%',
  textAlign: 'center',
}

const btnInfoStyle = { ...btnStyle, backgroundColor: 'var(--info-color, #17a2b8)' }

/* 하단 문의 버튼 — 이전앱 <a> 태그와 동일하게 너비 auto */
const btnContactStyle = {
  backgroundColor: 'var(--info-color, #17a2b8)',
  color: 'var(--border-color, #fff)',
  padding: '6px 12px',
  borderRadius: 4,
  fontSize: 14,
  cursor: 'pointer',
  border: 'none',
  textDecoration: 'none',
}

/* 이전앱 .card-extra-description — height 80 → 115 (4줄 수용) */
const extraDescStyle = {
  fontSize: 14,
  color: '#091747',
  lineHeight: 1.5,
  textAlign: 'left',
  padding: 15,
  border: '1px solid #d8dfeb',
  borderRadius: 8,
  backgroundColor: '#f9f9f9',
  margin: '20px 0 10px',
  height: 115,
  boxSizing: 'border-box',
  overflow: 'hidden',
}

export default function UsagePage() {
  const navigate = useNavigate()
  const [registerOpen,    setRegisterOpen]    = useState(false)
  const [tenantType,      setTenantType]      = useState(null)
  const [tenantModalOpen, setTenantModalOpen] = useState(false)
  const [hoveredCard,     setHoveredCard]     = useState(null)

  const openRegister = () => setRegisterOpen(true)
  const openTenant = (type) => { setTenantType(type); setTenantModalOpen(true) }

  const getCardStyle = (id) => ({
    ...cardStyle,
    ...(hoveredCard === id ? {
      boxShadow: '0 5px 15px rgba(0,0,0,0.1)',
      transform: 'translateY(-3px)',
    } : {}),
  })

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>서비스 이용</div>
        </div>
      </div>

      {/* ── 이전앱 .usage-container — margin:0 100px, padding:0 20px ── */}
      <div style={{ display: 'flex', gap: 20, maxWidth: 950, margin: '0 100px', padding: '0 20px' }}>

        {/* 카드1 컬럼: Free */}
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
          <div
            style={getCardStyle('free')}
            onMouseEnter={() => setHoveredCard('free')}
            onMouseLeave={() => setHoveredCard(null)}
          >
            <div style={{ height: 150 }}>
              <div style={{ fontSize: 22, fontWeight: 700, color: '#091747', marginBottom: 10 }}>Free</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: '#091747', marginBottom: 30 }}>Try SmartDocu</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: '#091747', marginBottom: 10 }}>Free</div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 10, height: 82, justifyContent: 'flex-end' }}>
              <button style={btnStyle} onClick={openRegister}>회원가입</button>
            </div>
            <div style={{ fontSize: 14, color: '#091747', lineHeight: 1.6, marginTop: 5, height: 67 }}>
              <div>기본서버</div>
              <div>DB 연동 불가</div>
              <div>기간 지나면 자료 삭제</div>
            </div>
          </div>
          <div style={extraDescStyle}>
            <div>- 등록 자료는 30일 이내 보관 가능</div>
            <div>- 등록 문서는 3개 이내로 제한</div>
            <div>- 문서당 항목은 30개 이내로 제한</div>
          </div>
          <div style={extraDescStyle}>
            <div>- LLM 사용</div>
            <div>&nbsp;&nbsp;일 프롬프트 수행 30회 이내 가능</div>
          </div>
        </div>

        {/* 카드2~4 컬럼: Pro / Teams / Enterprise */}
        <div style={{ display: 'flex', flexDirection: 'column', flex: 3 }}>
          <div style={{ display: 'flex', gap: 30 }}>

            {/* Pro */}
            <div
              style={getCardStyle('pro')}
              onMouseEnter={() => setHoveredCard('pro')}
              onMouseLeave={() => setHoveredCard(null)}
            >
              <div style={{ height: 150 }}>
                <div style={{ fontSize: 22, fontWeight: 700, color: '#091747', marginBottom: 10 }}>Pro</div>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#091747', marginBottom: 30 }}>Individual</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: '#091747', marginBottom: 10 }}>월 2만원 /인</div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 10, height: 82, justifyContent: 'flex-end' }}>
                <button style={btnStyle} onClick={openRegister}>회원가입</button>
              </div>
              <div style={{ fontSize: 14, color: '#091747', lineHeight: 1.6, marginTop: 5, height: 67 }}>
                <div>기본서버</div>
                <div>DB 연동 불가</div>
              </div>
            </div>

            {/* Teams */}
            <div
              style={getCardStyle('teams')}
              onMouseEnter={() => setHoveredCard('teams')}
              onMouseLeave={() => setHoveredCard(null)}
            >
              <div style={{ height: 150 }}>
                <div style={{ fontSize: 22, fontWeight: 700, color: '#091747', marginBottom: 10 }}>Teams</div>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#091747', marginBottom: 30 }}>Multi-User</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: '#091747', marginBottom: 10 }}>
                  <div>20명 이하</div>
                  <div>월 5만원 /인</div>
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 10, height: 82, justifyContent: 'flex-end' }}>
                <button style={btnInfoStyle} onClick={() => openTenant('teams')}>기업 등록</button>
                <button style={btnStyle} onClick={openRegister}>회원가입</button>
              </div>
              <div style={{ fontSize: 14, color: '#091747', lineHeight: 1.6, marginTop: 5, height: 67 }}>
                <div>기본서버</div>
                <div>DB 연동 가능</div>
              </div>
            </div>

            {/* Enterprise */}
            <div
              style={getCardStyle('enterprise')}
              onMouseEnter={() => setHoveredCard('enterprise')}
              onMouseLeave={() => setHoveredCard(null)}
            >
              <div style={{ height: 150 }}>
                <div style={{ fontSize: 22, fontWeight: 700, color: '#091747', marginBottom: 10 }}>Enterprise</div>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#091747', marginBottom: 30 }}>Multi-User Enterprise</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: '#091747', marginBottom: 10 }}>
                  <div>20명 이상</div>
                  <div>월 10만원 /인</div>
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 10, height: 82, justifyContent: 'flex-end' }}>
                <button style={btnInfoStyle} onClick={() => openTenant('tenant')}>기업 등록</button>
                <button style={btnStyle} onClick={openRegister}>회원가입</button>
              </div>
              <div style={{ fontSize: 14, color: '#091747', lineHeight: 1.6, marginTop: 5, height: 67 }}>
                <div>별도 서버 지정</div>
                <div>DB 연동 가능</div>
              </div>
            </div>

          </div>

          {/* 공통 설명 (4줄) */}
          <div style={extraDescStyle}>
            <div>- 등록 자료는 보관 기간 제한 없음</div>
            <div>- 등록 문서 개수 제한 없음</div>
            <div>- 문서당 항목 개수 제한 없음</div>
            <div>- AI 프롬프트 수행 제한 없음</div>
          </div>
          <div style={extraDescStyle}>
            <div>- LLM 사용 용량</div>
            <div>&nbsp;&nbsp;인당 월 100만 입력 토큰</div>
            <div>- LLM 추가 사용 비용</div>
            <div>&nbsp;&nbsp;100만 입력 토큰 당 5,000원</div>
          </div>
        </div>

        {/* 카드5 컬럼: Customizing */}
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
          <div
            style={getCardStyle('customizing')}
            onMouseEnter={() => setHoveredCard('customizing')}
            onMouseLeave={() => setHoveredCard(null)}
          >
            <div style={{ height: 150 }}>
              <div style={{ fontSize: 22, fontWeight: 700, color: '#091747', marginBottom: 10 }}>Customizing</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: '#091747', marginBottom: 30 }}>Add Function</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: '#091747', marginBottom: 10 }}>기능 추가에 따른</div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 10, height: 82, justifyContent: 'flex-end' }}>
              <button style={btnStyle} onClick={() => navigate('/qna')}>문의</button>
            </div>
            <div style={{ fontSize: 14, color: '#091747', lineHeight: 1.6, marginTop: 5, height: 67 }} />
          </div>
        </div>

      </div>

      {/* ── 하단 문의 버튼 — 이전앱과 동일: position fixed, bottom:15px ── */}
      <div style={{
        position: 'fixed',
        bottom: 54,
        left: '50%',
        transform: 'translateX(-50%)',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        zIndex: 1000,
        fontSize: 14,
        color: '#091747',
        fontWeight: 600,
      }}>
        <span>문의:</span>
        <button style={btnContactStyle} onClick={() => navigate('/contact')}>Mail</button>
        <button style={btnContactStyle} onClick={() => navigate('/qna')}>Q&amp;A</button>
      </div>

      <RegisterModal open={registerOpen} onClose={() => setRegisterOpen(false)} />
      <TenantRequestModal
        open={tenantModalOpen}
        onClose={() => { setTenantModalOpen(false); setTenantType(null) }}
        type={tenantType}
      />
    </div>
  )
}
