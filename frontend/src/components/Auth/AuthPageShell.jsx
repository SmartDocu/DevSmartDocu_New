import { useNavigate } from 'react-router-dom'
import { useLangStore, t } from '@/stores/langStore'

const LEGAL_BASE = 'https://d1y3pyhkb7jr6k.cloudfront.net'

export const AUTH_NAVY = '#0B2A6B'
export const authLabelStyle = { display: 'flex', flexDirection: 'column', gap: 7 }
export const authLabelTextStyle = { fontSize: 13, fontWeight: 600, color: '#4b5058' }

// 로그인/회원가입 공용 스타일(.lg-*) — 로그인 페이지 디자인 시안 기준
const AUTH_CSS = `
.lg-input{height:46px;padding:0 14px;font-family:inherit;font-size:15px;color:#14161a;background:#fff;border:1px solid #d9d5cd;border-radius:10px;outline:none;width:100%;box-sizing:border-box}
.lg-input:focus{border-color:oklch(.52 .17 264);box-shadow:0 0 0 3px oklch(.93 .04 264)}
.lg-btn{width:100%;height:48px;border:none;border-radius:11px;background:${AUTH_NAVY};color:#fff;font-family:inherit;font-size:16px;font-weight:700;cursor:pointer}
.lg-btn:hover:not(:disabled){background:#123a8f}
.lg-btn:disabled{opacity:.55;cursor:default}
.lg-btn-sub{background:#fff;color:#4b5058;border:1px solid #d9d5cd}
.lg-btn-sub:hover:not(:disabled){background:#f4f2ee}
.lg-link{color:#4b5058;text-decoration:none;background:none;border:none;padding:0;font-family:inherit;font-size:14px;cursor:pointer}
.lg-link:hover{color:oklch(.4 .17 264)}
`

/**
 * 로그인·회원가입 페이지 공통 틀 — 가운데 흰 카드 + 하단 푸터(약관·개인정보처리방침·고객지원).
 * AppLayout Content의 좌우·하단 padding(24px)을 상쇄해 푸터가 화면 좌우 끝·바닥에 붙는다.
 */
export default function AuthPageShell({ cardMaxWidth = 420, compact = false, children }) {
  const navigate = useNavigate()
  const languageCd = useLangStore((s) => s.languageCd)
  useLangStore((s) => s.translations)
  const legalLang = languageCd === 'ko' ? 'ko' : 'en'

  return (
    <div style={{
      minHeight: 'calc(100vh - 60px)', margin: '0 -24px -24px', display: 'flex', flexDirection: 'column',
      background: '#f4f2ee', color: '#14161a', overflow: 'hidden',
      fontFamily: 'Pretendard, system-ui, sans-serif',
    }}>
      <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css" precedence="default" />
      <style>{AUTH_CSS}</style>

      {/* 본문 */}
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: compact ? '16px 20px' : '40px 20px' }}>
        <div style={{
          width: '100%', maxWidth: cardMaxWidth, background: '#fff', border: '1px solid #e6e2da',
          borderRadius: 18, padding: compact ? '26px 32px 22px' : '40px 36px 32px', boxShadow: '0 24px 60px -40px rgba(11,42,107,.35)',
        }}>
          {children}
        </div>
      </div>

      {/* 푸터 */}
      <div style={{
        flex: 'none', borderTop: '1px solid #e6e2da', background: '#fff', padding: '20px 24px',
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13.5 }}>
          <a className="lg-link" style={{ fontSize: 13.5 }} href={`${LEGAL_BASE}/${legalLang}/terms`} target="_blank" rel="noopener noreferrer">
            {t('lbl.login.terms')}
          </a>
          <span style={{ color: '#c3bfb7' }}>·</span>
          <a className="lg-link" style={{ fontSize: 13.5, fontWeight: 600 }} href={`${LEGAL_BASE}/${legalLang}/privacy`} target="_blank" rel="noopener noreferrer">
            {t('lbl.login.privacy')}
          </a>
          <span style={{ color: '#c3bfb7' }}>·</span>
          <a className="lg-link" style={{ fontSize: 13.5 }} href="/contact" onClick={(e) => { e.preventDefault(); navigate('/contact') }}>
            {t('lbl.login.support')}
          </a>
        </div>
        <div style={{ fontSize: 12.5, color: '#9a9ea6' }}>© 2026 D2Doc. All rights reserved.</div>
      </div>
    </div>
  )
}
