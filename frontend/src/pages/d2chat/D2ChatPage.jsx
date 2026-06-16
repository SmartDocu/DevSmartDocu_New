import { useState, useRef, useCallback, useEffect } from 'react'
import './d2chat.css'
import apiClient from '@/api/client'
import { useTabStore } from '@/stores/tabStore'
import chatbotQuery from '@/assets/icons/chatbot_query.svg'
import chatbotQueryHide from '@/assets/icons/chatbot_query_hide.svg'
import chatbotBot from '@/assets/icons/chatbot_bot.svg'
import chatbotHuman from '@/assets/icons/chatbot_human.svg'

const INITIAL_MSG = {
  role: 'assistant',
  content: '안녕하세요! 데이터 분석을 도와드립니다. 무엇을 도와드릴까요?',
  visualization: null,
  visualizationType: null,
}

// ── Share Modal (plain HTML/CSS) ──────────────────────────────────────────────

function ShareModal({ sessionId, sessionTitle, onClose, onShared }) {
  const [users, setUsers] = useState([])
  const [selected, setSelected] = useState([])
  const [loading, setLoading] = useState(true)
  const [sharing, setSharing] = useState(false)

  useEffect(() => {
    apiClient.get('/d2chat/users/same-tenant')
      .then(r => { setUsers(r.data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const toggle = (uid) =>
    setSelected(prev => prev.includes(uid) ? prev.filter(id => id !== uid) : [...prev, uid])

  const handleShare = async () => {
    if (!selected.length) return
    setSharing(true)
    try {
      await apiClient.post('/d2chat/share', {
        session_id: sessionId,
        session_titles: sessionTitle,
        target_user_uids: selected,
      })
      onShared?.()
      onClose()
    } catch {
      setSharing(false)
    }
  }

  return (
    <div className="d2chat-share-modal-overlay" onClick={onClose}>
      <div className="d2chat-share-modal-box" onClick={e => e.stopPropagation()}>
        <h3>대화 공유</h3>
        <p className="d2chat-share-session-title">"{sessionTitle}"</p>
        {loading ? (
          <p style={{ color: '#888', fontSize: 13 }}>사용자 목록 로딩 중...</p>
        ) : users.length === 0 ? (
          <p style={{ color: '#888', fontSize: 13 }}>공유 가능한 사용자가 없습니다.</p>
        ) : (
          <ul className="d2chat-share-user-list">
            {users.map(u => (
              <li key={u.creator} className="d2chat-share-user-item">
                <label>
                  <input type="checkbox" checked={selected.includes(u.creator)} onChange={() => toggle(u.creator)} />
                  <span>{u.email}</span>
                </label>
              </li>
            ))}
          </ul>
        )}
        <div className="d2chat-share-modal-actions">
          <button className="share-btn" onClick={handleShare} disabled={!selected.length || sharing}>
            {sharing ? '공유 중...' : `공유 (${selected.length}명)`}
          </button>
          <button className="cancel-btn" onClick={onClose}>취소</button>
        </div>
      </div>
    </div>
  )
}

// ── Sidebar ───────────────────────────────────────────────────────────────────

function Sidebar({
  history, favorites, sharesSent, sharesReceived,
  activeSessionId, viewingSessionId, viewingSnapshotId, viewingFavoriteQauid,
  onNewChat, onSelectSession, onSelectFavorite, onSelectSnapshot,
  onDeleteSession, onDeleteFavorite, onDeleteShareSent, onDeleteShareReceived,
  onShareOpen,
  currentTitle,
}) {
  const [openSections, setOpenSections] = useState({ sent: false, received: false, favorites: false, history: true })
  const [openDates, setOpenDates] = useState({})
  const [menuOpenId, setMenuOpenId] = useState(null)
  const [menuSection, setMenuSection] = useState(null)
  const [menuPos, setMenuPos] = useState({ top: 0, left: 0 })

  const favSessionIds = new Set(favorites.map(f => f.session_id))

  const toggleSection = key => setOpenSections(p => ({ ...p, [key]: !p[key] }))
  const toggleDate = d => setOpenDates(p => ({ ...p, [d]: !p[d] }))

  const openCtx = (e, id, section) => {
    e.stopPropagation()
    if (menuOpenId === id) { setMenuOpenId(null); return }
    const rect = e.currentTarget.getBoundingClientRect()
    setMenuPos({ top: rect.bottom + 4, left: rect.left - 60 })
    setMenuOpenId(id)
    setMenuSection(section)
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
    if (menuSection === 'favorites') { onDeleteFavorite?.(id) }
    else if (menuSection === 'sent') { onDeleteShareSent?.(id) }
    else if (menuSection === 'received') { onDeleteShareReceived?.(id) }
    else { onDeleteSession?.(id) }
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

        {/* ── 공유한 내역 ── */}
        <div className="sidebar-section">
          <SectionHeader sectionKey="sent" icon="↑" label="공유한 내역" count={sharesSent.length} />
          {openSections.sent && (
            <ul className="session-list">
              {sharesSent.length === 0
                ? <li className="sidebar-empty">공유한 대화가 없습니다.</li>
                : sharesSent.map(s => (
                  <li
                    key={s.shareuid}
                    className={`session-item ${s.shareuid === viewingSnapshotId ? 'viewing' : ''}`}
                    onClick={() => onSelectSnapshot(s.shareuid, s.sessiontitles)}
                  >
                    <span className="session-title">{s.sessiontitles || '(제목 없음)'}</span>
                    <span className="session-date-badge">{s.createdt?.slice(5)}</span>
                    <button className="session-menu-btn" onClick={e => openCtx(e, s.shareuid, 'sent')}>···</button>
                  </li>
                ))
              }
            </ul>
          )}
        </div>

        {/* ── 공유받은 내역 ── */}
        <div className="sidebar-section">
          <SectionHeader sectionKey="received" icon="↓" label="공유받은 내역" count={sharesReceived.length} />
          {openSections.received && (
            <ul className="session-list">
              {sharesReceived.length === 0
                ? <li className="sidebar-empty">공유받은 대화가 없습니다.</li>
                : sharesReceived.map(s => (
                  <li
                    key={s.shareuid}
                    className={`session-item ${s.shareuid === viewingSnapshotId ? 'viewing' : ''}`}
                    onClick={() => onSelectSnapshot(s.shareuid, s.sessiontitles)}
                  >
                    <span className="session-title">{s.sessiontitles || '(제목 없음)'}</span>
                    <span className="session-date-badge">{s.createdt?.slice(5)}</span>
                    <button className="session-menu-btn" onClick={e => openCtx(e, s.shareuid, 'received')}>···</button>
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
                    <span className="session-date-badge">{f.create_dt?.slice(5)}</span>
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
                        <button
                          className="session-menu-btn"
                          onClick={e => openCtx(e, s.session_id, 'history')}
                        >···</button>
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
      {menuOpenId && (
        <div className="session-dropdown" style={{ top: menuPos.top, left: menuPos.left }}>
          {menuSection === 'history' && (
            <button
              className="session-dropdown-item"
              onClick={e => {
                const session = Object.values(history).flat().find(x => x.session_id === menuOpenId)
                if (session) onShareOpen(session.session_id, session.title)
                setMenuOpenId(null)
              }}
            >공유</button>
          )}
          <button className="session-dropdown-del" onClick={e => handleDelete(e, menuOpenId)}>삭제</button>
        </div>
      )}
    </aside>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function D2ChatPage() {
  const tabs = useTabStore(s => s.tabs)
  const siderCollapsed = useTabStore(s => s.siderCollapsed)
  const top = tabs.length > 0 ? 104 : 60
  const left = siderCollapsed ? 50 : 300

  const [sessionId, setSessionId] = useState(null)
  const sessionIdRef = useRef(null)
  const updateSessionId = id => { setSessionId(id); sessionIdRef.current = id }

  const [msgs, setMsgs] = useState([INITIAL_MSG])
  const [queryHistory, setQueryHistory] = useState([])
  const [inputVal, setInputVal] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [queryPanelOpen, setQueryPanelOpen] = useState(false)
  const [showAutoTest, setShowAutoTest] = useState(true)

  const [viewMode, setViewMode] = useState('chat')
  const [historyMsgs, setHistoryMsgs] = useState([])
  const [historyLabel, setHistoryLabel] = useState('')
  const [viewingSessionId, setViewingSessionId] = useState(null)
  const [viewingSnapshotId, setViewingSnapshotId] = useState(null)
  const [viewingFavQauid, setViewingFavQauid] = useState(null)

  const [history, setHistory] = useState({})
  const [favorites, setFavorites] = useState([])
  const [sharesSent, setSharesSent] = useState([])
  const [sharesReceived, setSharesReceived] = useState([])
  const [shareTarget, setShareTarget] = useState(null)

  const messagesEndRef = useRef(null)
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, isLoading])

  const favQaids = new Set(favorites.map(f => f.qauid))

  // ── 데이터 로드 ──────────────────────────────────────────────────────────────

  const loadHistory = useCallback(() => {
    apiClient.get('/d2chat/history').then(r => {
      const data = r.data
      setHistory(data)
      const today = new Date().toISOString().slice(0, 10)
      if (data[today]) { /* today's sessions open by default */ }
    }).catch(() => {})
  }, [])

  const loadFavorites = useCallback(() => {
    apiClient.get('/d2chat/favorites').then(r => setFavorites(r.data)).catch(() => {})
  }, [])

  const loadShares = useCallback(() => {
    Promise.all([
      apiClient.get('/d2chat/shares/sent'),
      apiClient.get('/d2chat/shares/received'),
    ]).then(([s, r]) => {
      setSharesSent(s.data)
      setSharesReceived(r.data)
    }).catch(() => {})
  }, [])

  useEffect(() => { loadHistory(); loadFavorites(); loadShares() }, [])
  useEffect(() => { loadHistory() }, [sessionId])

  // ── 핸들러 ──────────────────────────────────────────────────────────────────

  const handleNewChat = () => {
    updateSessionId(null)
    setMsgs([INITIAL_MSG])
    setQueryHistory([])
    setShowAutoTest(true)
    setViewingSessionId(null)
    setViewingSnapshotId(null)
    setViewingFavQauid(null)
    setViewMode('chat')
  }

  const handleSelectSession = async (sid) => {
    try {
      const r = await apiClient.get(`/d2chat/history/${sid}`)
      setHistoryMsgs(r.data.messages || [])
      setHistoryLabel('과거 대화 보기')
      setViewingSessionId(sid)
      setViewingSnapshotId(null)
      setViewingFavQauid(null)
      setViewMode('history')
    } catch {}
  }

  const handleSelectFavorite = (fav) => {
    setHistoryMsgs([
      { role: 'user', content: fav.question, qauid: fav.qauid },
      {
        role: 'assistant', content: fav.answer,
        visualization: fav.visualization_type === 'table' ? fav.table_html : fav.visualization_type === 'chart' ? fav.chart_image : null,
        visualizationType: fav.visualization_type,
      },
    ])
    setHistoryLabel('즐겨찾기')
    setViewingSessionId(null)
    setViewingSnapshotId(null)
    setViewingFavQauid(fav.qauid)
    setViewMode('history')
  }

  const handleSelectSnapshot = async (shareUid, label) => {
    try {
      const r = await apiClient.get(`/d2chat/snapshots/${shareUid}`)
      const transformed = (r.data.messages || []).map(m => ({
        ...m,
        visualization: m.visualization_type === 'table' ? m.table_html : m.visualization_type === 'chart' ? m.chart_image : null,
        visualizationType: m.visualization_type,
      }))
      setHistoryMsgs(transformed)
      setHistoryLabel(label || '공유받은 대화')
      setViewingSessionId(null)
      setViewingSnapshotId(shareUid)
      setViewingFavQauid(null)
      setViewMode('history')
    } catch {}
  }

  const handleToggleFavorite = async (qauid) => {
    try {
      if (favQaids.has(qauid)) {
        await apiClient.delete(`/d2chat/favorite/qa/${qauid}`)
      } else {
        await apiClient.post('/d2chat/favorite/qa', { qauid })
      }
      loadFavorites()
    } catch {}
  }

  const handleDeleteSession = async (sid) => {
    try {
      await apiClient.delete(`/d2chat/history/${sid}`)
      loadHistory()
      if (sid === sessionId) handleNewChat()
    } catch {}
  }

  const handleDeleteFavorite = async (qauid) => {
    try { await apiClient.delete(`/d2chat/favorite/qa/${qauid}`); loadFavorites() } catch {}
  }

  const handleDeleteShareSent = async (shareUid) => {
    try { await apiClient.delete(`/d2chat/shares/sent/${shareUid}`); loadShares() } catch {}
  }

  const handleDeleteShareReceived = async (shareUid) => {
    try { await apiClient.delete(`/d2chat/shares/received/${shareUid}`); loadShares() } catch {}
  }

  const handleContinue = async ({ question, answer, visualization_type, table_html, chart_image }) => {
    try {
      const r = await apiClient.post('/d2chat/session/inject', {
        session_id: sessionIdRef.current,
        question, answer, visualization_type, table_html, chart_image,
      })
      if (r.data.session_id) updateSessionId(r.data.session_id)
      const viz = visualization_type === 'table' ? table_html : visualization_type === 'chart' ? chart_image : null
      setMsgs(prev => [
        ...prev,
        { role: 'user', content: question, visualization: null, visualizationType: null },
        { role: 'assistant', content: answer, visualization: viz, visualizationType: visualization_type },
      ])
      setViewingSessionId(null)
      setViewingSnapshotId(null)
      setViewingFavQauid(null)
      setShowAutoTest(false)
      setViewMode('chat')
    } catch {}
  }

  const sendQuestion = async (override = null) => {
    const question = (typeof override === 'string' ? override : inputVal).trim()
    if (!question || isLoading) return

    setMsgs(prev => [...prev, { role: 'user', content: question, visualization: null, visualizationType: null }])
    setInputVal('')
    setShowAutoTest(false)
    setIsLoading(true)

    try {
      const r = await apiClient.post('/d2chat/ask', {
        question,
        session_id: sessionIdRef.current,
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
      if ((data.queries && data.queries.length > 0) || data.query) {
        setQueryHistory(prev => [...prev, {
          question,
          queries: data.queries?.length ? data.queries : [{ query: data.query, table: null }],
        }])
      }
      const viz = data.visualization_type === 'table' ? data.table_html
        : data.visualization_type === 'chart' ? data.chart_image : null
      setMsgs(prev => [...prev, {
        role: 'assistant',
        content: data.answer || '',
        visualization: viz,
        visualizationType: data.visualization_type,
      }])
    } catch (e) {
      setMsgs(prev => [...prev, {
        role: 'assistant',
        content: '오류가 발생했습니다: ' + (e.response?.data?.detail || e.message),
        visualization: null, visualizationType: null,
      }])
    } finally {
      setIsLoading(false)
      loadHistory()
    }
  }

  const runAutoTest = async () => {
    try {
      const r = await apiClient.get('/d2chat/questions')
      const questions = r.data.questions || []
      for (const q of questions) {
        await sendQuestion(q)
        await new Promise(res => setTimeout(res, 1000))
      }
    } catch {}
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendQuestion() }
  }

  const currentTitle = msgs.find(m => m.role === 'user')?.content?.slice(0, 30) || ''

  return (
    <>
      <div
        className="d2chat-wrap"
        style={{ top, left, right: 0, bottom: 0 }}
      >
        {/* ── 사이드바 ── */}
        <Sidebar
          history={history}
          favorites={favorites}
          sharesSent={sharesSent}
          sharesReceived={sharesReceived}
          activeSessionId={sessionId}
          viewingSessionId={viewingSessionId}
          viewingSnapshotId={viewingSnapshotId}
          viewingFavoriteQauid={viewingFavQauid}
          currentTitle={currentTitle}
          onNewChat={handleNewChat}
          onSelectSession={handleSelectSession}
          onSelectFavorite={handleSelectFavorite}
          onSelectSnapshot={handleSelectSnapshot}
          onDeleteSession={handleDeleteSession}
          onDeleteFavorite={handleDeleteFavorite}
          onDeleteShareSent={handleDeleteShareSent}
          onDeleteShareReceived={handleDeleteShareReceived}
          onShareOpen={(sid, title) => setShareTarget({ sessionId: sid, title })}
        />

        {/* ── 메인 콘텐츠 ── */}
        <div className="main-content">
          <div className="chat-container">
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
                          chart_image: historyMsgs[i + 1]?.chart_image,
                        })
                      }}
                    >이어하기</button>
                  )}
                </div>
                <div className="history-messages">
                  {historyMsgs.map((msg, i) => (
                    <div key={i} className="msg-row">
                      <div className={`message ${msg.role}`}>
                        {msg.role === 'assistant' && <img src={chatbotBot} className="assistant-icon" alt="bot" />}
                        <div className="message-content">{msg.content}</div>
                        {msg.role === 'user' && <img src={chatbotHuman} className="user-icon" alt="user" />}
                      </div>
                      {msg.visualization && (
                        <div className="visualization-container">
                          {msg.visualizationType === 'table'
                            ? <div dangerouslySetInnerHTML={{ __html: msg.visualization }} />
                            : <img src={`data:image/png;base64,${msg.visualization}`} alt="차트" />}
                        </div>
                      )}
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
                  ))}
                </div>
              </div>
            ) : (
              <>
                {/* ── 메시지 목록 ── */}
                <div className="messages">
                  {msgs.map((msg, i) => (
                    <div key={i} className="msg-row">
                      <div className={`message ${msg.role}`}>
                        {msg.role === 'assistant' && <img src={chatbotBot} className="assistant-icon" alt="bot" />}
                        <div className="message-content">{msg.content}</div>
                        {msg.role === 'user' && <img src={chatbotHuman} className="user-icon" alt="user" />}
                      </div>
                      {msg.visualization && (
                        <div className="visualization-container">
                          {msg.visualizationType === 'table'
                            ? <div dangerouslySetInnerHTML={{ __html: msg.visualization }} />
                            : <img src={`data:image/png;base64,${msg.visualization}`} alt="차트" />}
                        </div>
                      )}
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
                  ))}
                  {isLoading && (
                    <div className="loading">
                      <div className="spinner" />
                      <span className="loading-text">분석 중입니다...</span>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>

                {/* ── 입력창 ── */}
                <div className="input-container">
                  <div className="input-wrapper">
                    <textarea
                      className="question-input"
                      value={inputVal}
                      onChange={e => setInputVal(e.target.value)}
                      onKeyDown={handleKeyDown}
                      placeholder="데이터에 대해 질문하세요... (Shift+Enter: 줄바꿈)"
                      disabled={isLoading}
                      rows={2}
                    />
                    <button className="send-btn" onClick={() => sendQuestion()} disabled={isLoading}>전송</button>
                    {showAutoTest && (
                      <button className="auto-test-btn" onClick={runAutoTest} disabled={isLoading}>샘플 질문</button>
                    )}
                    <button
                      className="d2chat-toggle-query-btn"
                      onClick={() => setQueryPanelOpen(p => !p)}
                      title={queryPanelOpen ? '쿼리 숨기기' : '쿼리 보기'}
                    >
                      <img src={queryPanelOpen ? chatbotQueryHide : chatbotQuery} alt="query toggle" />
                      <div className="toggle-text">{queryPanelOpen ? '쿼리 숨기기' : '쿼리 보기'}</div>
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>

          {/* ── 쿼리 패널 ── */}
          <div className={`query-panel ${queryPanelOpen ? 'active' : ''}`}>
            <div className="query-header">
              <span>SQL 쿼리 로그</span>
              <button className="query-close" onClick={() => setQueryPanelOpen(false)}>✕</button>
            </div>
            <div className="query-content">
              {queryHistory.length === 0 ? (
                <p style={{ color: '#aaa', fontSize: 13 }}>실행된 쿼리가 없습니다.</p>
              ) : queryHistory.slice().reverse().map((item, i) => (
                <div key={i} className="query-item">
                  <div className="query-question">{item.question}</div>
                  {(item.queries || []).map((q, j) => (
                    <div key={j}>
                      <pre className="query-sql">{q.query}</pre>
                      <button className="query-copy-btn" onClick={() => navigator.clipboard.writeText(q.query)}>복사</button>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>


      {/* ── 공유 모달 ── */}
      {shareTarget && (
        <ShareModal
          sessionId={shareTarget.sessionId}
          sessionTitle={shareTarget.title}
          onClose={() => setShareTarget(null)}
          onShared={() => { loadShares(); setShareTarget(null) }}
        />
      )}
    </>
  )
}
