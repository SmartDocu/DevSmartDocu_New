import { useState } from 'react'
import { marked } from 'marked'
import { useLangStore, t } from '@/stores/langStore'
import { useAuthStore } from '@/stores/authStore'
import { useDeactivatePopup } from '@/hooks/usePopups'

// 비로그인 사용자용 localStorage fallback
function isDeactivatedLocally(popupid) {
  const enddt = localStorage.getItem(`popup_deactivate_${popupid}`)
  if (!enddt) return false
  return enddt >= new Date().toISOString().split('T')[0]
}

function saveDeactivateLocally(popupid, days) {
  const end = new Date()
  end.setDate(end.getDate() + days)
  localStorage.setItem(`popup_deactivate_${popupid}`, end.toISOString().split('T')[0])
}

const ALIGN_TO_FLEX = { left: 'flex-start', center: 'center', right: 'flex-end' }

// content_type='inline'인 팝업의 제목/본문/버튼을 langCd 기준으로 로컬라이즈.
// 번역 오버라이드가 없으면 base(popups.title/body/button_text) 사용.
function localizePopup(popup, langCd) {
  const loc = popup.translations?.[langCd] || {}
  return {
    title: loc.title || popup.title,
    body: loc.body || popup.body,
    buttonText: loc.button_text || popup.button_text,
  }
}

export default function PopupManager({ popups = [] }) {
  const langCd = useLangStore(s => s.languageCd) || 'en'
  const isAuthenticated = useAuthStore(s => s.isAuthenticated())
  const deactivateMutation = useDeactivatePopup()
  const [closed, setClosed] = useState({})

  // 서버에서 이미 기간·DB비활성화 필터 완료 → 비로그인은 localStorage 추가 확인
  const visible = popups.filter(p =>
    !closed[p.popupid] && (isAuthenticated || !isDeactivatedLocally(p.popupid))
  )

  if (!visible.length) return null

  const handleClose = (id) => setClosed(prev => ({ ...prev, [id]: true }))

  const handleDeactivate = (popup) => {
    if (isAuthenticated) {
      deactivateMutation.mutate(popup.popupid)  // 로그인: DB에만 저장
    } else {
      saveDeactivateLocally(popup.popupid, popup.deactivateday ?? 7)  // 비로그인: localStorage에만 저장
    }
    handleClose(popup.popupid)
  }

  return (
    <>
      {visible.map((popup, idx) => {
        const loc = localizePopup(popup, langCd)
        return (
        <div
          key={popup.popupid}
          style={{
            position: 'fixed',
            left: (popup.lefts ?? 100) + idx * 20,
            top: (popup.top ?? 100) + idx * 20,
            width: popup.width ?? 400,
            zIndex: 1000 + idx,
            background: '#fff',
            border: '1px solid #d9d9d9',
            borderRadius: 8,
            boxShadow: '0 6px 24px rgba(0,0,0,0.2)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {/* 헤더 */}
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '8px 12px',
            borderBottom: '1px solid #f0f0f0',
            background: '#fafafa',
            flexShrink: 0,
          }}>
            <span style={{ fontWeight: 600, fontSize: 13, color: '#333' }}>{loc.title}</span>
            <button
              onClick={() => handleClose(popup.popupid)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: '#aaa', lineHeight: 1, padding: '0 2px' }}
            >×</button>
          </div>

          {/* 팝업 콘텐츠 */}
          {popup.content_type === 'inline' ? (
            <div style={{ width: '100%', height: popup.height ?? 280, overflow: 'auto', padding: 16, boxSizing: 'border-box', display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div
                style={{ fontSize: 13, color: '#333', flex: 1, textAlign: popup.text_align || 'left' }}
                dangerouslySetInnerHTML={{ __html: marked.parse(loc.body || '') }}
              />
              {loc.buttonText && (
                popup.button_url ? (
                  <a
                    href={popup.button_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ alignSelf: ALIGN_TO_FLEX[popup.text_align] ?? 'flex-start', padding: '6px 16px', background: '#1677ff', color: '#fff', borderRadius: 4, fontSize: 13, textDecoration: 'none' }}
                  >
                    {loc.buttonText}
                  </a>
                ) : (
                  <button
                    onClick={() => handleClose(popup.popupid)}
                    style={{ alignSelf: ALIGN_TO_FLEX[popup.text_align] ?? 'flex-start', padding: '6px 16px', background: '#1677ff', color: '#fff', border: 'none', borderRadius: 4, fontSize: 13, cursor: 'pointer' }}
                  >
                    {loc.buttonText}
                  </button>
                )
              )}
            </div>
          ) : (
            // 'page' 타입 — langCd를 URL param으로 전달, 팝업 페이지 내부에서 fallback 처리
            <iframe
              src={`${popup.pageurl}?lang=${langCd}`}
              style={{ width: '100%', height: popup.height ?? 280, border: 'none', display: 'block' }}
              title={loc.title}
            />
          )}

          {/* 푸터 */}
          <div style={{
            display: 'flex',
            justifyContent: 'flex-end',
            alignItems: 'center',
            gap: 12,
            padding: '6px 12px',
            borderTop: '1px solid #f0f0f0',
            background: '#fafafa',
            flexShrink: 0,
          }}>
            <button
              onClick={() => handleDeactivate(popup)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 12, color: '#999' }}
            >
              {popup.deactivateday ?? 7}{t('lbl.popup.days_hide_suffix')}
            </button>
            <span style={{ color: '#e0e0e0' }}>|</span>
            <button
              onClick={() => handleClose(popup.popupid)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 12, color: '#999' }}
            >
              {t('btn.close')}
            </button>
          </div>
        </div>
        )
      })}
    </>
  )
}
