import { useState, useRef, useCallback, useEffect } from 'react'
import { marked } from 'marked'
import './d2insight.css'
import apiClient from '@/api/client'
import { useTabStore } from '@/stores/tabStore'
import { useAuthStore } from '@/stores/authStore'
import chatbotBot from '@/assets/icons/chatbot_bot.svg'
import chatbotHuman from '@/assets/icons/chatbot_human.svg'

const INITIAL_MSG = {
  role: 'assistant',
  content: '안녕하세요! 분석 에이전트입니다.\n분석할 기준월과 원하는 분석 유형을 알려주세요.\n예: "2014-01 보고서 생성해주세요"',
  visualization: null,
  visualizationType: null,
  fileurl: null,
}

// ── markdown + base64 이미지 파싱 ──────────────────────────────────────────────

function parseMarkdownWithImages(text) {
  const images = []
  const processed = text.replace(
    /!\[([^\]]*)\]\((data:image\/[^)]*)\)/g,
    (_match, alt, src) => {
      const id = images.length
      images.push({ alt, src })
      return `CHART_IMG_${id}_PLACEHOLDER`
    }
  )
  let html = marked.parse(processed)
  images.forEach(({ alt, src }, id) => {
    html = html.replace(
      `CHART_IMG_${id}_PLACEHOLDER`,
      `<img src="${src}" alt="${alt}" style="max-width:100%;height:auto;display:block;margin:1em 0;">`
    )
  })
  return html
}

// ── FolderPickerModal ─────────────────────────────────────────────────────────

function FolderPickerModal({ userId, onConfirm, onCancel }) {
  const [folders, setFolders] = useState([])
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiClient.get(`/d2insight/folders/${userId}`)
      .then(r => { setFolders(Array.isArray(r.data) ? r.data : []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [userId])

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <h3 className="modal-title">공유 폴더 선택</h3>
        {loading ? (
          <p className="modal-empty">폴더 로딩 중...</p>
        ) : folders.length === 0 ? (
          <p className="modal-empty">등록된 폴더가 없습니다.</p>
        ) : (
          <ul className="folder-list">
            {folders.map(f => (
              <li
                key={f.folderuid}
                className={`folder-item${selected === f.folderuid ? ' selected' : ''}`}
                style={{ paddingLeft: `${(f.folderlevel - 1) * 16 + 12}px` }}
                onClick={() => setSelected(f.folderuid)}
              >
                {f.folderlevel > 1 ? '└ ' : ''}{f.foldernm}
              </li>
            ))}
          </ul>
        )}
        <div className="modal-actions">
          <button className="modal-btn cancel" onClick={onCancel}>취소</button>
          <button
            className="modal-btn confirm"
            onClick={() => selected && onConfirm(selected)}
            disabled={!selected}
          >공유</button>
        </div>
      </div>
    </div>
  )
}

// ── ReportCard ────────────────────────────────────────────────────────────────

function ReportCard({ reportPath, fileurl, qauid, onShareQa, userId }) {
  const [html, setHtml] = useState('')
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [showFolder, setShowFolder] = useState(false)

  useEffect(() => { setHtml(''); setExpanded(false) }, [fileurl])

  const isMdUrl = fileurl ? /\.md(\?|$)/.test(fileurl) : false
  const mdUrl = isMdUrl
    ? fileurl
    : fileurl
      ? fileurl.replace(/\.pdf(\?.*)?$/, '.md$1')
      : (reportPath ? `/api/d2insight/reports/${reportPath}` : null)

  const pdfUrl = isMdUrl
    ? fileurl.replace(/\.md(\?.*)?$/, '.pdf$1')
    : fileurl || (reportPath ? `/api/d2insight/reports/${reportPath}` : null)

  const displayName = pdfUrl
    ? decodeURIComponent(pdfUrl.split('/').pop().split('?')[0])
    : (reportPath ? reportPath.replace('.md', '.pdf') : '보고서.pdf')

  const handleDownload = async () => {
    if (!pdfUrl) return
    try {
      const res = await fetch(pdfUrl)
      if (!res.ok) throw new Error(`${res.status}`)
      const blob = await res.blob()
      const blobUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = blobUrl; a.download = displayName
      document.body.appendChild(a); a.click()
      document.body.removeChild(a); URL.revokeObjectURL(blobUrl)
    } catch (e) { alert(`다운로드 실패: ${e.message}`) }
  }

  const handleToggle = async () => {
    if (expanded) { setExpanded(false); return }
    if (!html && mdUrl) {
      setLoading(true)
      try {
        const res = await fetch(mdUrl)
        if (res.ok) {
          setHtml(parseMarkdownWithImages(await res.text()))
        } else if (pdfUrl) {
          setHtml(`<iframe src="${pdfUrl}" style="width:100%;height:600px;border:none;" title="보고서 미리보기"></iframe>`)
        } else {
          setHtml('<p style="color:#c00">미리보기를 불러올 수 없습니다.</p>')
        }
      } catch (e) {
        setHtml(`<p style="color:#c00">보고서를 불러올 수 없습니다. (${e.message})</p>`)
      } finally {
        setLoading(false)
      }
    }
    setExpanded(true)
  }

  if (!pdfUrl) return null

  return (
    <div className="report-card">
      <div className="report-card-header">
        <span className="report-icon">📄</span>
        <span className="report-filename">{displayName}</span>
        <div className="report-btns">
          <button className="report-btn" onClick={handleToggle} disabled={loading}>
            {loading ? '로딩 중...' : expanded ? '접기' : '미리보기'}
          </button>
          <button className="report-btn download" onClick={handleDownload}>다운로드</button>
          {qauid && onShareQa && (
            <button className="report-btn share-btn" onClick={() => setShowFolder(true)}>공유</button>
          )}
        </div>
      </div>
      {expanded && html && (
        <div className="report-preview" dangerouslySetInnerHTML={{ __html: html }} />
      )}
      {showFolder && (
        <FolderPickerModal
          userId={userId}
          onCancel={() => setShowFolder(false)}
          onConfirm={(folderUid) => { setShowFolder(false); onShareQa(qauid, folderUid) }}
        />
      )}
    </div>
  )
}

// ── Sidebar ───────────────────────────────────────────────────────────────────

function Sidebar({
  userId,
  history, favorites, sharesSent, sharesReceived,
  activeSessionId, viewingSessionId, viewingShareQauid, viewingFavoriteQauid,
  onNewChat, onSelectSession, onSelectFavorite, onSelectShare,
  onDeleteSession, onDeleteFavorite, onDeleteShareSent, onDeleteShareReceived,
  currentTitle,
}) {
  const [openSections, setOpenSections] = useState({ received: false, sent: false, favorites: false, history: true })
  const [openDates, setOpenDates] = useState({})
  const [menuOpenId, setMenuOpenId] = useState(null)
  const [menuSection, setMenuSection] = useState(null)
  const [menuPos, setMenuPos] = useState({ top: 0, left: 0 })
  const [menuCanDelete, setMenuCanDelete] = useState(true)

  const favSessionIds = new Set(favorites.map(f => f.session_id).filter(Boolean))

  const toggleSection = key => setOpenSections(p => ({ ...p, [key]: !p[key] }))
  const toggleDate = d => setOpenDates(p => ({ ...p, [d]: !p[d] }))

  const openCtx = (e, id, section, canDelete = true) => {
    e.stopPropagation()
    if (menuOpenId === id) { setMenuOpenId(null); return }
    const rect = e.currentTarget.getBoundingClientRect()
    setMenuPos({ top: rect.bottom + 4, left: rect.left - 60 })
    setMenuOpenId(id)
    setMenuSection(section)
    setMenuCanDelete(canDelete)
  }

  useEffect(() => {
    if (menuOpenId === null) return
    const h = (e) => {
      if (!e.target.closest('.session-dropdown') && !e.target.closest('.session-menu-btn'))
        setMenuOpenId(null)
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [menuOpenId])

  const handleDelete = async (e, id) => {
    e.stopPropagation()
    setMenuOpenId(null)
    if (menuSection === 'favorites') onDeleteFavorite?.(id)
    else if (menuSection === 'sent') onDeleteShareSent?.(id)
    else if (menuSection === 'received') onDeleteShareReceived?.(id)
    else onDeleteSession?.(id)
  }

  const SectionHeader = ({ sectionKey, icon, label, count, iconActive }) => (
    <button
      className={`section-toggle ${openSections[sectionKey] ? 'open' : ''}`}
      onClick={() => toggleSection(sectionKey)}
    >
      <span className="section-toggle-left">
        <span className={`section-icon${iconActive ? ' icon-active' : ''}`}>{icon}</span>
        <span className="section-label">{label}</span>
        {count > 0 && <span className="section-count">{count}</span>}
      </span>
      <span className="arrow">{openSections[sectionKey] ? '▾' : '▸'}</span>
    </button>
  )

  return (
    <aside className="sidebar">
      <div className="current-session-block">
        <span className="current-session-label">현재 대화</span>
        <span className="current-session-title">{currentTitle || '아직 질문이 없습니다.'}</span>
      </div>
      <div className="sidebar-newchat">
        <button className="new-chat-btn" onClick={onNewChat}>+ 새 대화</button>
      </div>

      <nav className="sidebar-nav">

        {/* ── 공유보고서 (테넌트 전체) ── */}
        <div className="sidebar-section">
          <SectionHeader sectionKey="received" icon="📂" label="공유보고서" count={sharesReceived.length} />
          {openSections.received && (
            <ul className="session-list">
              {sharesReceived.length === 0
                ? <li className="sidebar-empty">공유된 보고서가 없습니다.</li>
                : sharesReceived.map(s => (
                  <li
                    key={s.share_qauid}
                    className={`session-item ${s.share_qauid === viewingShareQauid ? 'viewing' : ''}`}
                    onClick={() => onSelectShare(s.share_qauid, s.question)}
                  >
                    <span className="session-title">{s.question?.slice(0, 35) || '(내용 없음)'}</span>
                    <span className="session-date-badge">{s.created_at?.slice(5, 10)}</span>
                    {s.creator === userId && (
                      <button className="session-menu-btn" onClick={e => openCtx(e, s.share_qauid, 'received')}>···</button>
                    )}
                  </li>
                ))
              }
            </ul>
          )}
        </div>

        {/* ── 공유한보고서 ── */}
        <div className="sidebar-section">
          <SectionHeader sectionKey="sent" icon="↑" label="공유한보고서" count={sharesSent.length} />
          {openSections.sent && (
            <ul className="session-list">
              {sharesSent.length === 0
                ? <li className="sidebar-empty">공유한 보고서가 없습니다.</li>
                : sharesSent.map(s => (
                  <li
                    key={s.share_qauid}
                    className={`session-item ${s.share_qauid === viewingShareQauid ? 'viewing' : ''}`}
                    onClick={() => onSelectShare(s.share_qauid, s.question)}
                  >
                    <span className="session-title">{s.question?.slice(0, 35) || '(내용 없음)'}</span>
                    <span className="session-date-badge">{s.created_at?.slice(5, 10)}</span>
                    <button className="session-menu-btn" onClick={e => openCtx(e, s.share_qauid, 'sent')}>···</button>
                  </li>
                ))
              }
            </ul>
          )}
        </div>

        {/* ── 즐겨찾기 ── */}
        <div className="sidebar-section fav-section">
          <SectionHeader sectionKey="favorites" icon="★" label="즐겨찾기" count={favorites.length} iconActive={favorites.length > 0} />
          {openSections.favorites && (
            <ul className="session-list">
              {favorites.length === 0
                ? <li className="sidebar-empty">즐겨찾기가 없습니다.</li>
                : favorites.map(f => (
                  <li
                    key={f.qauid}
                    className={`session-item ${f.qauid === viewingFavoriteQauid ? 'viewing' : ''}`}
                    onClick={() => onSelectFavorite(f)}
                  >
                    <span className="session-title">{f.question?.slice(0, 35) || '(내용 없음)'}</span>
                    <span className="session-date-badge">{f.created_at?.slice(5, 10)}</span>
                    <button className="session-menu-btn" onClick={e => openCtx(e, f.qauid, 'favorites')}>···</button>
                  </li>
                ))
              }
            </ul>
          )}
        </div>

        {/* ── 대화 목록 (날짜별) ── */}
        <div className="sidebar-section">
          <SectionHeader
            sectionKey="history" icon="💬" label="대화 목록"
            count={Object.values(history).flat().filter(s => s.session_id !== activeSessionId).length}
          />
          {openSections.history && (() => {
            const filtered = Object.entries(history)
              .map(([d, sessions]) => [d, sessions.filter(s => s.session_id !== activeSessionId)])
              .filter(([, ss]) => ss.length > 0)

            if (filtered.length === 0)
              return <p className="sidebar-empty">이전 대화가 없습니다.</p>

            return filtered.map(([d, sessions]) => (
              <div key={d} className="date-group">
                <button
                  className={`date-toggle ${openDates[d] ? 'open' : ''}`}
                  onClick={() => toggleDate(d)}
                >
                  <span>{d} <span className="section-count date-count">{sessions.length}</span></span>
                  <span className="arrow">{openDates[d] ? '▾' : '▸'}</span>
                </button>
                {openDates[d] && (
                  <ul className="session-list">
                    {sessions.map(s => (
                      <li
                        key={s.session_id}
                        className={`session-item ${s.session_id === viewingSessionId ? 'viewing' : ''}`}
                        onClick={() => onSelectSession(s.session_id)}
                      >
                        <span className={`session-fav-indicator ${favSessionIds.has(s.session_id) ? 'fav-on' : ''}`}>★</span>
                        <span className="session-title">{s.title || '(제목 없음)'}</span>
                        <button className="session-menu-btn" onClick={e => openCtx(e, s.session_id, 'history')}>···</button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))
          })()}
        </div>

      </nav>

      {/* 드롭다운 메뉴 */}
      {menuOpenId && menuCanDelete && (
        <div className="session-dropdown" style={{ top: menuPos.top, left: menuPos.left }}>
          <button className="session-dropdown-del" onClick={e => handleDelete(e, menuOpenId)}>삭제</button>
        </div>
      )}
    </aside>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function D2InsightPage() {
  const tabs = useTabStore(s => s.tabs)
  const siderCollapsed = useTabStore(s => s.siderCollapsed)
  const top = tabs.length > 0 ? 104 : 60
  const left = siderCollapsed ? 50 : 300

  const user = useAuthStore(s => s.user)
  const userId = user?.id || null

  const [sessionId, setSessionId] = useState(null)
  const sessionIdRef = useRef(null)
  const updateSessionId = id => { setSessionId(id); sessionIdRef.current = id }

  const [msgs, setMsgs] = useState([INITIAL_MSG])
  const [inputVal, setInputVal] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [sharesTrigger, setSharesTrigger] = useState(0)

  const [viewMode, setViewMode] = useState('chat')
  const [historyMsgs, setHistoryMsgs] = useState([])
  const [historyLabel, setHistoryLabel] = useState('')
  const [viewingSessionId, setViewingSessionId] = useState(null)
  const [viewingShareQauid, setViewingShareQauid] = useState(null)
  const [viewingFavQauid, setViewingFavQauid] = useState(null)

  const [history, setHistory] = useState({})
  const [favorites, setFavorites] = useState([])
  const [sharesSent, setSharesSent] = useState([])
  const [sharesReceived, setSharesReceived] = useState([])

  const messagesEndRef = useRef(null)
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, isLoading])

  const favQaids = new Set(favorites.map(f => f.qauid))

  // ── 데이터 로드 ──────────────────────────────────────────────────────────────

  const loadHistory = useCallback(() => {
    if (!userId) return
    apiClient.get(`/d2insight/history/${userId}`).then(r => {
      const data = r.data
      if (data && typeof data === 'object' && !Array.isArray(data)) setHistory(data)
    }).catch(() => {})
  }, [userId])

  const loadFavorites = useCallback(() => {
    if (!userId) return
    apiClient.get(`/d2insight/favorites/${userId}`).then(r => setFavorites(Array.isArray(r.data) ? r.data : [])).catch(() => {})
  }, [userId])

  const loadShares = useCallback(() => {
    if (!userId) return
    Promise.all([
      apiClient.get(`/d2insight/shares/sent/${userId}`),
      apiClient.get(`/d2insight/shares/received/${userId}`),
    ]).then(([s, r]) => {
      setSharesSent(Array.isArray(s.data) ? s.data : [])
      setSharesReceived(Array.isArray(r.data) ? r.data : [])
    }).catch(() => {})
  }, [userId])

  useEffect(() => { loadHistory(); loadFavorites(); loadShares() }, [userId])
  useEffect(() => { loadHistory() }, [sessionId])
  useEffect(() => { loadShares() }, [sharesTrigger])

  // ── 핸들러 ──────────────────────────────────────────────────────────────────

  const handleNewChat = () => {
    updateSessionId(null)
    setMsgs([INITIAL_MSG])
    setViewingSessionId(null)
    setViewingShareQauid(null)
    setViewingFavQauid(null)
    setViewMode('chat')
  }

  const handleSelectSession = async (sid) => {
    try {
      const r = await apiClient.get(`/d2insight/history/${userId}/${sid}`)
      setHistoryMsgs(r.data.messages || [])
      setHistoryLabel('과거 대화 보기')
      setViewingSessionId(sid)
      setViewingShareQauid(null)
      setViewingFavQauid(null)
      setViewMode('history')
    } catch {}
  }

  const handleSelectFavorite = (fav) => {
    setHistoryMsgs([
      { role: 'user', content: fav.question, qauid: fav.qauid },
      {
        role: 'assistant', content: fav.answer,
        visualization: fav.visualization_type === 'table' ? fav.table_html : null,
        visualizationType: fav.visualization_type,
        fileurl: fav.fileurl,
      },
    ])
    setHistoryLabel('즐겨찾기')
    setViewingSessionId(null)
    setViewingShareQauid(null)
    setViewingFavQauid(fav.qauid)
    setViewMode('history')
  }

  const handleSelectShare = async (shareQauid, label) => {
    try {
      const r = await apiClient.get(`/d2insight/shares/${shareQauid}`)
      const row = r.data
      let answerText = row.answer || ''
      try {
        const obj = JSON.parse(row.answer)
        answerText = obj.answer || answerText
      } catch {}
      setHistoryMsgs([
        { role: 'user', content: row.question || '' },
        { role: 'assistant', content: answerText, fileurl: row.fileurl, reportPath: row.filenm },
      ])
      setHistoryLabel(label?.slice(0, 40) || '공유된 보고서')
      setViewingSessionId(null)
      setViewingShareQauid(shareQauid)
      setViewingFavQauid(null)
      setViewMode('history')
    } catch {}
  }

  const handleToggleFavorite = async (qauid) => {
    if (!userId) return
    try {
      if (favQaids.has(qauid)) {
        await apiClient.delete(`/d2insight/favorite/qa/${userId}/${qauid}`)
      } else {
        await apiClient.post('/d2insight/favorite/qa', { user_id: userId, qauid })
      }
      loadFavorites()
    } catch {}
  }

  const handleShareQa = async (qauid, folderUid) => {
    if (!qauid || !userId) return
    const r = await apiClient.post('/d2insight/share', {
      user_id: userId,
      qauid,
      folder_uid: folderUid || null,
    })
    if (r.status < 300) setSharesTrigger(n => n + 1)
  }

  const handleDeleteSession = async (sid) => {
    if (!userId) return
    try {
      await apiClient.delete(`/d2insight/history/${userId}/${sid}`)
      loadHistory()
      if (sid === sessionId) handleNewChat()
    } catch {}
  }

  const handleDeleteFavorite = async (qauid) => {
    if (!userId) return
    try { await apiClient.delete(`/d2insight/favorite/qa/${userId}/${qauid}`); loadFavorites() } catch {}
  }

  const handleDeleteShareSent = async (shareUid) => {
    if (!userId) return
    try { await apiClient.delete(`/d2insight/shares/sent/${shareUid}/${userId}`); loadShares() } catch {}
  }

  const handleDeleteShareReceived = async (shareUid) => {
    if (!userId) return
    try { await apiClient.delete(`/d2insight/shares/received/${shareUid}/${userId}`); loadShares() } catch {}
  }

  const handleContinue = async ({ question, answer, visualization_type, table_html, fileurl }) => {
    try {
      const r = await apiClient.post('/d2insight/session/inject', {
        session_id: sessionIdRef.current,
        user_id: userId,
        question, answer, visualization_type, table_html,
      })
      if (r.data.session_id) updateSessionId(r.data.session_id)
      const viz = visualization_type === 'table' ? table_html : null
      setMsgs(prev => [
        ...prev,
        { role: 'user', content: question, visualization: null, visualizationType: null },
        { role: 'assistant', content: answer, visualization: viz, visualizationType: visualization_type, fileurl },
      ])
      setViewingSessionId(null)
      setViewingShareQauid(null)
      setViewingFavQauid(null)
      setViewMode('chat')
    } catch {}
  }

  const sendMessage = async () => {
    const question = inputVal.trim()
    if (!question || isLoading) return

    setMsgs(prev => [...prev, { role: 'user', content: question, visualization: null, visualizationType: null }])
    setInputVal('')
    setIsLoading(true)

    try {
      const r = await apiClient.post('/d2insight/chat', {
        message: question,
        session_id: sessionIdRef.current,
        user_id: userId,
      })
      const data = r.data
      if (data.session_id) updateSessionId(data.session_id)
      if (data.qauid) {
        setMsgs(prev => {
          const updated = [...prev]
          for (let i = updated.length - 1; i >= 0; i--) {
            if (updated[i].role === 'user') { updated[i] = { ...updated[i], qauid: data.qauid }; break }
          }
          return updated
        })
      }
      const viz = data.visualization_type === 'table' ? data.table_html
        : data.visualization_type === 'chart' ? data.chart_image : null
      setMsgs(prev => [...prev, {
        role: 'assistant',
        content: data.answer || '',
        visualization: viz,
        visualizationType: data.visualization_type,
        fileurl: data.fileurl || null,
        reportPath: data.report_path || null,
        qauid: data.qauid || null,
      }])
    } catch (e) {
      setMsgs(prev => [...prev, {
        role: 'assistant',
        content: '오류가 발생했습니다: ' + (e.response?.data?.detail || e.message),
        visualization: null, visualizationType: null, fileurl: null,
      }])
    } finally {
      setIsLoading(false)
      loadHistory()
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
  }

  const currentTitle = msgs.find(m => m.role === 'user')?.content?.slice(0, 40) || ''

  // ── 메시지 렌더 헬퍼 ─────────────────────────────────────────────────────────

  const renderMsg = (msg, i, inHistory = false) => (
    <div key={i} className="msg-row">
      <div className={`message ${msg.role}`}>
        {msg.role === 'assistant' && (
          <img src={chatbotBot} className="assistant-icon" alt="bot" />
        )}
        <div className="message-content">
          {msg.content}
          {msg.visualization && (
            <div className="visualization-container">
              {msg.visualizationType === 'table'
                ? <div dangerouslySetInnerHTML={{ __html: msg.visualization }} />
                : <img src={`data:image/png;base64,${msg.visualization}`} alt="차트" />}
            </div>
          )}
          {msg.role === 'assistant' && (msg.fileurl || msg.reportPath) && (
            <ReportCard
              reportPath={msg.reportPath}
              fileurl={msg.fileurl}
              qauid={!inHistory ? msg.qauid : null}
              onShareQa={!inHistory ? handleShareQa : null}
              userId={userId}
            />
          )}
        </div>
        {msg.role === 'user' && (
          <img src={chatbotHuman} className="user-icon" alt="user" />
        )}
      </div>
      {msg.role === 'user' && msg.qauid && (
        <div className="fav-btn-row">
          <button
            className={`msg-fav-btn ${favQaids.has(msg.qauid) ? 'fav-on' : ''}`}
            onClick={() => handleToggleFavorite(msg.qauid)}
            title={favQaids.has(msg.qauid) ? '즐겨찾기 해제' : '즐겨찾기 추가'}
          >★</button>
        </div>
      )}
    </div>
  )

  return (
    <div
      className="d2insight-wrap"
      style={{ top, left, right: 0, bottom: 0 }}
    >
      {/* ── 사이드바 ── */}
      <Sidebar
        userId={userId}
        history={history}
        favorites={favorites}
        sharesSent={sharesSent}
        sharesReceived={sharesReceived}
        activeSessionId={sessionId}
        viewingSessionId={viewingSessionId}
        viewingShareQauid={viewingShareQauid}
        viewingFavoriteQauid={viewingFavQauid}
        currentTitle={currentTitle}
        onNewChat={handleNewChat}
        onSelectSession={handleSelectSession}
        onSelectFavorite={handleSelectFavorite}
        onSelectShare={handleSelectShare}
        onDeleteSession={handleDeleteSession}
        onDeleteFavorite={handleDeleteFavorite}
        onDeleteShareSent={handleDeleteShareSent}
        onDeleteShareReceived={handleDeleteShareReceived}
      />

      {/* ── 메인 콘텐츠 ── */}
      <div className="main-content">
        {viewMode === 'history' ? (
          // ── 히스토리 뷰 ──
          <div className="history-view">
            <div className="history-bar">
              <button className="history-back-btn" onClick={() => { setViewingSessionId(null); setViewMode('chat') }}>
                ← 돌아가기
              </button>
              <span style={{ flex: 1, fontWeight: 600 }}>{historyLabel}</span>
              {historyMsgs.length >= 2 && (
                <button
                  className="continue-btn"
                  onClick={() => {
                    const i = historyMsgs.length - 2
                    handleContinue({
                      question: historyMsgs[i]?.content,
                      answer: historyMsgs[i + 1]?.content,
                      visualization_type: historyMsgs[i + 1]?.visualization_type || 'none',
                      table_html: historyMsgs[i + 1]?.table_html,
                      fileurl: historyMsgs[i + 1]?.fileurl,
                    })
                  }}
                >이어하기</button>
              )}
            </div>
            <div className="history-messages">
              {historyMsgs.map((msg, i) => renderMsg(msg, i, true))}
            </div>
          </div>
        ) : (
          // ── 채팅 뷰 ──
          <div className="chat-container">
            <div className="messages">
              {msgs.map((msg, i) => renderMsg(msg, i, false))}
              {isLoading && (
                <div className="loading">
                  <div className="spinner" />
                  <span className="loading-text">보고서를 생성 중입니다... 수 분이 소요될 수 있습니다.</span>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
            <div className="input-container">
              <div className="input-wrapper">
                <textarea
                  className="question-input"
                  value={inputVal}
                  onChange={e => setInputVal(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="분석 기간과 보고서 유형을 입력하세요... (Shift+Enter: 줄바꿈)"
                  disabled={isLoading}
                  rows={2}
                />
                <button className="send-btn" onClick={sendMessage} disabled={isLoading}>전송</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
