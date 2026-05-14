import { useState } from 'react'
import { useLangStore } from '@/stores/langStore'
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
      {visible.map((popup, idx) => (
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
            <span style={{ fontWeight: 600, fontSize: 13, color: '#333' }}>{popup.title}</span>
            <button
              onClick={() => handleClose(popup.popupid)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: '#aaa', lineHeight: 1, padding: '0 2px' }}
            >×</button>
          </div>

          {/* 팝업 콘텐츠 — langCd를 URL param으로 전달, 팝업 페이지 내부에서 fallback 처리 */}
          <iframe
            src={`${popup.pageurl}?lang=${langCd}`}
            style={{ width: '100%', height: popup.height ?? 280, border: 'none', display: 'block' }}
            title={popup.title}
          />

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
              {popup.deactivateday ?? 7}일간 보지 않기
            </button>
            <span style={{ color: '#e0e0e0' }}>|</span>
            <button
              onClick={() => handleClose(popup.popupid)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 12, color: '#999' }}
            >
              닫기
            </button>
          </div>
        </div>
      ))}
    </>
  )
}
