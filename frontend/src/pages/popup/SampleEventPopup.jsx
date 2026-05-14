import { useSearchParams } from 'react-router-dom'

const content = {
  en: {
    badge: 'Limited Time',
    headline: 'Summer Event 2026',
    body: 'Start with D2Doc now and get 3 months free!\nAI-powered document automation at your fingertips.',
    cta: 'Start Free Trial',
  },
  ko: {
    badge: '한정 기간',
    headline: '2026 여름 이벤트',
    body: 'D2Doc를 지금 시작하면 3개월 무료!\nAI 문서 자동화를 경험해 보세요.',
    cta: '무료 체험 시작',
  },
  ja: {
    badge: '期間限定',
    headline: '2026 夏のイベント',
    body: 'D2Docを今すぐ始めると3ヶ月無料！\nAI文書自動化をぜひ体験ください。',
    cta: '無料トライアル開始',
  },
  // es 없음 → en fallback 확인용
}

export default function SampleEventPopup() {
  const [params] = useSearchParams()
  const langCd = params.get('lang') || 'en'
  const c = content[langCd] ?? content.en

  return (
    <div style={{
      height: '100vh',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      alignItems: 'center',
      color: '#fff',
      padding: 28,
      boxSizing: 'border-box',
      textAlign: 'center',
      fontFamily: 'inherit',
    }}>
      <span style={{
        background: 'rgba(255,255,255,0.25)',
        padding: '4px 16px',
        borderRadius: 20,
        fontSize: 12,
        letterSpacing: 1,
        marginBottom: 18,
      }}>
        {c.badge}
      </span>

      <h2 style={{ margin: '0 0 14px', fontSize: 22, fontWeight: 700 }}>
        {c.headline}
      </h2>

      <p style={{ margin: '0 0 24px', fontSize: 13, opacity: 0.9, whiteSpace: 'pre-line', lineHeight: 1.7 }}>
        {c.body}
      </p>

      <button style={{
        background: '#fff',
        color: '#764ba2',
        border: 'none',
        borderRadius: 6,
        padding: '10px 24px',
        fontWeight: 700,
        fontSize: 14,
        cursor: 'pointer',
      }}>
        {c.cta}
      </button>
    </div>
  )
}
