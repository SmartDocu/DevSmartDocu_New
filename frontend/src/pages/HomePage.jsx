import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'

const slides = [
  {
    title: '데이터 설정',
    desc: 'ODBC를 지원하는 모든 데이터베이스와 Excel 자료에 대한 연결 정보, 쿼리, 데이터 항목을 정의합니다.',
    img: '/Home01.png',
  },
  {
    title: '문서 설정',
    desc: '구성할 목차, 템플릿, 템플릿 내 항목을 정의합니다.\n개체에 해당하는 문장, 테이블, 차트는 AI와 UI로 정의합니다.',
    img: '/Home02.png',
  },
  {
    title: '문서 작성',
    desc: '문서의 노출된 매개변수에 값을 기입하여 해당 매개변수 기준으로 문서를 작성합니다.',
    img: '/Home03.png',
  },
]

export default function HomePage() {
  const navigate = useNavigate()
  const [current, setCurrent] = useState(0)
  const timerRef = useRef(null)

  const startTimer = () => {
    timerRef.current = setInterval(() => {
      setCurrent(prev => (prev + 1) % slides.length)
    }, 5000)
  }

  const resetTimer = (index) => {
    clearInterval(timerRef.current)
    setCurrent(index)
    startTimer()
  }

  useEffect(() => {
    startTimer()
    return () => clearInterval(timerRef.current)
  }, [])

  return (
    <div>
      {/* 상단 타이틀 */}
      <div style={{ textAlign: 'center', padding: 20 }}>
        <p style={{ fontSize: '1rem', margin: 0, opacity: 0.8 }}>효율적인 문서 자동 작성</p>
        <p style={{ fontSize: '5rem', fontWeight: 300, margin: 0 }}>SmartDocu</p>
      </div>

      {/* 설명 배너 */}
      <div style={{ display: 'flex', gap: 0, marginTop: 40 }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div style={{ marginLeft: 'auto', marginRight: '10%', backgroundColor: 'rgb(230,230,230)', padding: '15px 100px 15px 30px', borderRadius: 8 }}>
            <p style={{ textAlign: 'left', color: 'black', fontWeight: 'normal', margin: 0 }}>
              SmartDocu는 DB와 Excel로부터 <br />
              AI 기능을 이용하여 문서를 작성합니다.
            </p>
          </div>
        </div>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <div style={{ marginRight: 'auto', marginLeft: '10%', backgroundColor: 'rgb(230,230,230)', padding: '15px 100px 15px 30px', borderRadius: 8 }}>
            <p style={{ textAlign: 'left', color: 'black', fontWeight: 'normal', margin: 0 }}>
              작성에서 검토 및 확정 중심으로 전환,<br />
              One-Click으로 문서를 자동 작성합니다.
            </p>
          </div>
        </div>
      </div>

      {/* What / Why / How 카드 */}
      <div style={{ maxWidth: 700, margin: '60px auto', display: 'flex', flexDirection: 'column', gap: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20, padding: '20px 25px', borderRadius: 15, background: 'linear-gradient(90deg, #55C7D9, #91E3F3)', boxShadow: '0 8px 20px rgba(0,0,0,0.2)', color: '#fff' }}>
          <svg xmlns="http://www.w3.org/2000/svg" width="50" height="50" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/></svg>
          <strong style={{ fontSize: '1.2rem' }}>What</strong>
          정기적으로 작성해야 하는 문서
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 20, padding: '20px 25px', borderRadius: 15, background: 'linear-gradient(90deg, #FF9A8B, #FF6A88)', boxShadow: '0 8px 20px rgba(0,0,0,0.2)', color: '#fff' }}>
          <svg xmlns="http://www.w3.org/2000/svg" width="50" height="50" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12" y2="16"/></svg>
          <strong style={{ fontSize: '1.2rem' }}>Why</strong>
          반복적인 자료 조회, 비효율적인 작성
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 20, padding: '20px 25px', borderRadius: 15, background: 'linear-gradient(90deg, #FDCB6E, #FFB347)', boxShadow: '0 8px 20px rgba(0,0,0,0.2)', color: '#fff' }}>
          <svg xmlns="http://www.w3.org/2000/svg" width="50" height="50" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0-4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          <strong style={{ fontSize: '1.2rem' }}>How</strong>
          문서에 사용될 데이터와 서식 설정을 통해
        </div>
      </div>

      {/* 슬라이더 */}
      <div style={{ maxWidth: 800, margin: '50px auto', border: '1px solid #ddd', borderRadius: 15, overflow: 'hidden', position: 'relative', paddingBottom: 40 }}>
        <div style={{ display: 'flex', padding: 20, gap: 20, alignItems: 'center' }}>
          <div style={{ flex: 3 }}>
            <h2 style={{ margin: '0 0 8px' }}>{slides[current].title}</h2>
            <p style={{ margin: 0, whiteSpace: 'pre-line' }}>{slides[current].desc}</p>
          </div>
          <div style={{ flex: 7, textAlign: 'right' }}>
            <img src={slides[current].img} alt={slides[current].title} style={{ maxWidth: '100%', borderRadius: 10 }} />
          </div>
        </div>

        {/* 슬라이드 점 */}
        <div style={{ position: 'absolute', bottom: 12, left: '50%', transform: 'translateX(-50%)', display: 'flex', gap: 10, zIndex: 10 }}>
          {slides.map((_, i) => (
            <div
              key={i}
              onClick={() => resetTimer(i)}
              style={{
                width: 10, height: 10, borderRadius: '50%',
                background: i === current ? '#55C7D9' : '#bbb',
                cursor: 'pointer',
                transform: i === current ? 'scale(1.3)' : 'scale(1)',
                transition: 'all 0.2s',
              }}
            />
          ))}
        </div>
      </div>

      {/* 체험하기 / 따라하기 / 문의 */}
      <div style={{ maxWidth: 900, margin: '0 auto', display: 'flex', gap: 0, paddingBottom: 30 }}>

        <div style={{ flex: 1, textAlign: 'center', padding: '0 20px' }}>
          <p style={{ fontSize: 24, margin: '0 0 10px' }}>체험하기</p>
          <p style={{ fontSize: 16, margin: '0 0 20px', opacity: 0.8 }}>문장, 표, 차트를<br />AI 프롬프트로<br />수정해보기</p>
          <div style={{ display: 'flex', justifyContent: 'center', gap: 10 }}>
            <button
              style={{ backgroundColor: '#17a2b8', color: '#fff', padding: '8px 16px', borderRadius: 4, textDecoration: 'none', cursor: 'pointer', border: 'none', fontSize: 14 }}
              onClick={() => navigate('/experience')}
            >
              체험 시작
            </button>
          </div>
        </div>

        <div style={{ flex: 1, textAlign: 'center', padding: '0 20px' }}>
          <p style={{ fontSize: 24, margin: '0 0 10px' }}>따라하기</p>
          <p style={{ fontSize: 16, margin: '0 0 20px', opacity: 0.8 }}>제공 데이터를 활용해<br />따라하기 문서<br />실습해보기</p>
          <div style={{ display: 'flex', justifyContent: 'center', gap: 10 }}>
            <button
              style={{ backgroundColor: '#17a2b8', color: '#fff', padding: '8px 16px', borderRadius: 4, textDecoration: 'none', cursor: 'pointer', border: 'none', fontSize: 14 }}
              onClick={() => navigate('/follow')}
            >
              따라하기
            </button>
          </div>
        </div>

        <div style={{ flex: 1, textAlign: 'center', padding: '0 20px' }}>
          <p style={{ fontSize: 24, margin: '0 0 10px' }}>SmartDocu <span style={{ color: '#FFC107', fontWeight: 100 }}>AI</span></p>
          <p style={{ fontSize: 16, margin: '0 0 20px', lineHeight: 1.5, opacity: 0.8 }}>
            사용 및 적용<br />도입문의<br />커스터마이징 문의
          </p>
          <div style={{ display: 'flex', justifyContent: 'center', gap: 10 }}>
            <button
              style={{ backgroundColor: '#17a2b8', color: '#fff', padding: '8px 16px', borderRadius: 4, textDecoration: 'none', cursor: 'pointer', border: 'none', fontSize: 14 }}
              onClick={() => navigate('/contact')}
            >
              문의
            </button>
            <a
              href="https://dev-rag-medicine.azurewebsites.net/?projectid=6"
              target="_blank"
              rel="noreferrer"
              style={{ backgroundColor: '#17a2b8', color: '#fff', padding: '8px 16px', borderRadius: 4, textDecoration: 'none', fontSize: 14 }}
            >
              Chat
            </a>
          </div>
        </div>

      </div>

      {/* 푸터 */}
      <div style={{ backgroundColor: '#000', padding: '20px 0' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto', display: 'flex', gap: 0, padding: '0 20px' }}>

          <div style={{ flex: 1, padding: '0 20px', fontSize: 14 }}>
            <div style={{ color: '#fff', fontWeight: 600, marginBottom: 8 }}>MENU</div>
            {[
              { label: '서비스 소개', path: '/service' },
              { label: '기능 소개', path: '/about' },
              { label: '서비스 이용', path: '/usage' },
              { label: '체험하기', path: '/experience' },
              { label: '따라하기', path: '/follow' },
              { label: '문의', path: '/contact' },
              { label: 'Chat', path: 'https://dev-rag-medicine.azurewebsites.net/?projectid=6', external: true },
            ].map(m => (
              <a
                key={m.path}
                href={m.path}
                target={m.external ? '_blank' : undefined}
                rel={m.external ? 'noreferrer' : undefined}
                style={{ color: '#fff', textDecoration: 'none', display: 'block', margin: '4px 0', paddingLeft: 15 }}
              >{m.label}</a>
            ))}
          </div>

          <div style={{ flex: 1, padding: '0 20px', fontSize: 14 }}>
            <div style={{ color: '#999', fontWeight: 600, marginBottom: 8 }}>문서</div>
          </div>

          <div style={{ flex: 1, padding: '0 20px', fontSize: 14 }}>
            <div style={{ color: '#999', fontWeight: 600, marginBottom: 8 }}>기준 정보</div>
            <ul style={{ listStyle: 'none', paddingLeft: 15, margin: '6px 0 0', color: '#999' }}>
              {['문서 관리', '챕터 관리', '항목 관리', 'Excel 데이터', 'AI 데이터'].map(t => (
                <li key={t} style={{ margin: '3px 0' }}>{t}</li>
              ))}
            </ul>
          </div>

          <div style={{ flex: 1, padding: '0 20px', fontSize: 14 }}>
            <div style={{ color: '#999', fontWeight: 600, marginBottom: 8 }}>프로젝트 관리</div>
            <ul style={{ listStyle: 'none', paddingLeft: 15, margin: '6px 0 0', color: '#999' }}>
              {['기업 사용자 관리', '기업 LLM 관리', '프로젝트 관리', '프로젝트 사용자 관리'].map(t => (
                <li key={t} style={{ margin: '3px 0' }}>{t}</li>
              ))}
            </ul>
          </div>

          <div style={{ flex: 1, padding: '0 20px', fontSize: 14 }}>
            <div style={{ color: '#999', fontWeight: 600, marginBottom: 8 }}>DB 정보</div>
            <ul style={{ listStyle: 'none', paddingLeft: 15, margin: '6px 0 0', color: '#999' }}>
              {['DB 연결정보', 'DB 데이터'].map(t => (
                <li key={t} style={{ margin: '3px 0' }}>{t}</li>
              ))}
            </ul>
          </div>

        </div>
      </div>
    </div>
  )
}
