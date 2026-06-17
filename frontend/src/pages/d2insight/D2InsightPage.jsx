import { useState, useRef, useCallback, useEffect } from 'react'
import { App } from 'antd'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import chatbotBot from '@/assets/icons/chatbot_bot.svg'
import chatbotHuman from '@/assets/icons/chatbot_human.svg'
import '../d2shared/d2common.css'
import './d2insight.css'

const CHAT_TIMEOUT = { timeout: 360000 } // 보고서 생성 최대 6분

const INITIAL_MESSAGE = {
  role: 'assistant',
  content: '안녕하세요! AI 분석 보고서 에이전트입니다.\n\n기업 데이터를 분석하여 판매·경영·기술·품질 등 다양한 보고서를 자동으로 생성합니다.\n예: "2024-01 판매분석 보고서 작성해줘"',
  fileurl: null,
  reportPath: null,
}

const EXAMPLE_QUESTIONS = [
  { label: '판매 보고서', question: '2013년 9월 판매실적보고서를 작성해주세요.' },
  { label: '서버로그 보고서', question: '지난 달 서버로그 분석 보고서를 그 전달과 비교하여 일괄 작성해주세요.' },
  { label: '인터페이스로그 보고서', question: '지난달 인터페이스 로그 분석 보고서를 작성해주세요.' },
]


export default function D2InsightPage() {
  const { message } = App.useApp()
  const user = useAuthStore((s) => s.user)
  const userId = user?.id

  // ── 대화 상태 ──────────────────────────────────────────────────
  const [sessionId, setSessionId] = useState(null)
  const sessionIdRef = useRef(null)
  const updateSessionId = (id) => { setSessionId(id); sessionIdRef.current = id }

  const [messages, setMessages] = useState([INITIAL_MESSAGE])
  const [isLoading, setIsLoading] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const [viewMode, setViewMode] = useState('chat') // 'chat' | 'history'
  const [historyMessages, setHistoryMessages] = useState([])
  const [historyLabel, setHistoryLabel] = useState('')
  const [viewingSessionId, setViewingSessionId] = useState(null)
  const [viewingFavoriteQauid, setViewingFavoriteQauid] = useState(null)
  const [favorites, setFavorites] = useState([])
  const [shareTarget, setShareTarget] = useState(null) // {qauid}

  // ── 사이드바 상태 ──────────────────────────────────────────────
  const [history, setHistory] = useState({})
  const [sharesSent, setSharesSent] = useState([])
  const [sharesReceived, setSharesReceived] = useState([])
  const [openSections, setOpenSections] = useState({ sent: false, received: false, favorites: false, history: true })
  const [openDates, setOpenDates] = useState({})
  const [menuOpenId, setMenuOpenId] = useState(null)
  const [menuSection, setMenuSection] = useState(null)
  const [menuPos, setMenuPos] = useState({ top: 0, left: 0 })

  const bottomRef = useRef(null)

  const favoritedQaids = new Set(favorites.map((f) => f.qauid))
  const favoritedSessionIds = new Set(favorites.map((f) => f.session_id))

  // ── 데이터 로드 ────────────────────────────────────────────────
  const fetchFavorites = useCallback(async () => {
    if (!userId) return
    try {
      const { data } = await apiClient.get(`/d2insight/favorites/${userId}`)
      setFavorites(data || [])
    } catch {
      // ignore
    }
  }, [userId])

  const fetchHistory = useCallback(async () => {
    if (!userId) return
    try {
      const { data } = await apiClient.get(`/d2insight/history/${userId}`)
      setHistory(data || {})
      const today = new Date().toISOString().slice(0, 10)
      if (data?.[today]) setOpenDates((prev) => ({ ...prev, [today]: true }))
    } catch {
      // ignore
    }
  }, [userId])

  const fetchShares = useCallback(async () => {
    if (!userId) return
    try {
      const [sentRes, receivedRes] = await Promise.all([
        apiClient.get(`/d2insight/shares/sent/${userId}`),
        apiClient.get(`/d2insight/shares/received/${userId}`),
      ])
      setSharesSent(sentRes.data || [])
      setSharesReceived(receivedRes.data || [])
    } catch {
      // ignore
    }
  }, [userId])

  useEffect(() => { fetchFavorites() }, [fetchFavorites])
  useEffect(() => { fetchHistory(); fetchShares() }, [sessionId, fetchHistory, fetchShares])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading, historyMessages])

  // 외부 클릭 시 ··· 드롭다운 닫기
  useEffect(() => {
    if (menuOpenId === null) return
    const handler = (e) => {
      if (!e.target.closest('.session-dropdown') && !e.target.closest('.session-menu-btn')) {
        setMenuOpenId(null)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [menuOpenId])

  const currentTitle = messages.find((m) => m.role === 'user')?.content?.slice(0, 30) || ''

  // ── 대화 핸들러 ────────────────────────────────────────────────
  const handleNewChat = () => {
    updateSessionId(null)
    setMessages([INITIAL_MESSAGE])
    setViewingSessionId(null)
    setViewingFavoriteQauid(null)
    setViewMode('chat')
    setInputValue('')
  }

  const handleSelectSession = async (sid) => {
    if (!userId) return
    try {
      const { data } = await apiClient.get(`/d2insight/history/${userId}/${sid}`)
      setHistoryMessages(data.messages || [])
      setHistoryLabel('과거 보고서 보기')
      setViewingSessionId(sid)
      setViewingFavoriteQauid(null)
      setViewMode('history')
    } catch {
      // ignore
    }
  }

  const handleSelectFavorite = (fav) => {
    setHistoryMessages([
      { role: 'user', content: fav.question, qauid: fav.qauid },
      { role: 'assistant', content: fav.answer, fileurl: fav.fileurl, reportPath: fav.filenm },
    ])
    setHistoryLabel('즐겨찾기 보고서')
    setViewingSessionId(null)
    setViewingFavoriteQauid(fav.qauid)
    setViewMode('history')
  }

  const handleSelectShare = async (shareQauid, label) => {
    try {
      const { data } = await apiClient.get(`/d2insight/shares/${shareQauid}`)
      let answerText = ''
      try { answerText = JSON.parse(data.answer || '{}').answer || '' } catch { answerText = data.answer || '' }
      setHistoryMessages([
        { role: 'user', content: data.question || '' },
        { role: 'assistant', content: answerText, fileurl: data.fileurl, reportPath: data.filenm },
      ])
      setHistoryLabel(label || '공유받은 보고서')
      setViewingSessionId(null)
      setViewingFavoriteQauid(null)
      setViewMode('history')
    } catch {
      // ignore
    }
  }

  const handleToggleFavorite = async (qauid) => {
    if (!userId) return
    try {
      if (favoritedQaids.has(qauid)) {
        await apiClient.delete(`/d2insight/favorite/qa/${userId}/${qauid}`)
      } else {
        await apiClient.post('/d2insight/favorite/qa', { user_id: userId, qauid })
      }
      fetchFavorites()
    } catch (e) {
      message.error(e.response?.data?.detail || '즐겨찾기 처리 중 오류가 발생했습니다.')
    }
  }

  const handleContinue = async ({ question, answer, fileurl, reportPath }) => {
    try {
      const { data } = await apiClient.post('/d2insight/session/inject', {
        session_id: sessionId,
        user_id: userId,
        question, answer, report_path: reportPath,
      })
      if (data.session_id) updateSessionId(data.session_id)

      setMessages((prev) => [
        ...prev,
        { role: 'user', content: question },
        { role: 'assistant', content: answer, fileurl, reportPath },
      ])
      setViewingSessionId(null)
      setViewingFavoriteQauid(null)
      setViewMode('chat')
    } catch (e) {
      message.error(e.response?.data?.detail || '이어가기 중 오류가 발생했습니다.')
    }
  }

  const sendMessage = async (overrideText = null) => {
    const text = (typeof overrideText === 'string' ? overrideText : inputValue).trim()
    if (!text || isLoading) return

    setMessages((prev) => [...prev, { role: 'user', content: text }])
    setInputValue('')
    setIsLoading(true)

    try {
      const { data } = await apiClient.post(
        '/d2insight/chat',
        { message: text, session_id: sessionIdRef.current, user_id: userId },
        CHAT_TIMEOUT,
      )

      if (data.session_id) updateSessionId(data.session_id)

      // 최근 user 메시지에 qauid 달기
      if (data.qauid) {
        setMessages((prev) => {
          const updated = [...prev]
          for (let i = updated.length - 1; i >= 0; i--) {
            if (updated[i].role === 'user') {
              updated[i] = { ...updated[i], qauid: data.qauid }
              break
            }
          }
          return updated
        })
      }

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.answer || '',
          fileurl: data.fileurl || null,
          reportPath: data.report_path || null,
          qauid: data.qauid || null,
        },
      ])
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: '오류가 발생했습니다: ' + (error.response?.data?.detail || error.message) },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  // ── 사이드바 핸들러 ────────────────────────────────────────────
  const toggleSection = (key) => setOpenSections((prev) => ({ ...prev, [key]: !prev[key] }))
  const toggleDate = (d) => setOpenDates((prev) => ({ ...prev, [d]: !prev[d] }))

  const handleMenuClick = (e, id, section = 'history') => {
    e.stopPropagation()
    if (menuOpenId === id) { setMenuOpenId(null); return }
    const rect = e.currentTarget.getBoundingClientRect()
    setMenuPos({ top: rect.bottom + 4, left: rect.left - 60 })
    setMenuOpenId(id)
    setMenuSection(section)
  }

  const handleSidebarDelete = async (e, id) => {
    e.stopPropagation()
    setMenuOpenId(null)
    try {
      if (menuSection === 'favorites') {
        await apiClient.delete(`/d2insight/favorite/qa/${userId}/${id}`)
        fetchFavorites()
      } else if (menuSection === 'sent') {
        await apiClient.delete(`/d2insight/shares/sent/${id}/${userId}`)
        fetchShares()
      } else if (menuSection === 'received') {
        await apiClient.delete(`/d2insight/shares/received/${id}/${userId}`)
        fetchShares()
      } else {
        await apiClient.delete(`/d2insight/history/${userId}/${id}`)
        fetchHistory()
        if (id === sessionId) handleNewChat()
      }
    } catch (e2) {
      message.error(e2.response?.data?.detail || '삭제 중 오류가 발생했습니다.')
    }
  }

  // ── 사이드바 섹션 헤더 ─────────────────────────────────────────
  const SectionHeader = ({ sectionKey, icon, label, count, iconActive }) => (
    <button
      type="button"
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

  const filteredHistory = Object.entries(history)
    .map(([d, sessions]) => [d, sessions.filter((s) => s.session_id !== sessionId)])
    .filter(([, sessions]) => sessions.length > 0)

  return (
    <div style={{ height: 'calc(100vh - 164px)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

      {/* ── 헤더 ── */}
      <div className="page-title" style={{ flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>AI 분석 보고서 에이전트</div>
        </div>
      </div>

      <div className="d2insight-layout">

        {/* ── 사이드바 ── */}
        <aside className="d2insight-sidebar">
          <div className="current-session-block">
            <span className="current-session-label">현재 세션</span>
            <span className="current-session-title">{currentTitle || '아직 요청이 없습니다.'}</span>
          </div>

          <div className="sidebar-newchat">
            <button type="button" className="new-chat-btn" onClick={handleNewChat}>+ 새 대화</button>
          </div>

          <nav className="sidebar-nav">

            {/* 공유한 내역 */}
            <div className="sidebar-section">
              <SectionHeader sectionKey="sent" icon="↑" label="공유한 보고서" count={sharesSent.length} />
              {openSections.sent && (
                <ul className="session-list">
                  {sharesSent.length === 0
                    ? <li className="sidebar-empty">공유한 보고서가 없습니다.</li>
                    : sharesSent.map((s) => (
                      <li
                        key={s.share_qauid}
                        className="session-item"
                        onClick={() => handleSelectShare(s.share_qauid, s.question?.slice(0, 20))}
                      >
                        <span className="session-title">{s.question?.slice(0, 30) || '(제목 없음)'}</span>
                        <span className="session-date-badge">{s.created_at?.slice(5, 10)}</span>
                        <button type="button" className="session-menu-btn" onClick={(e) => handleMenuClick(e, s.share_qauid, 'sent')}>···</button>
                      </li>
                    ))}
                </ul>
              )}
            </div>

            {/* 공유받은 내역 */}
            <div className="sidebar-section">
              <SectionHeader sectionKey="received" icon="↓" label="공유받은 보고서" count={sharesReceived.length} />
              {openSections.received && (
                <ul className="session-list">
                  {sharesReceived.length === 0
                    ? <li className="sidebar-empty">공유받은 보고서가 없습니다.</li>
                    : sharesReceived.map((s) => (
                      <li
                        key={s.share_qauid}
                        className="session-item"
                        onClick={() => handleSelectShare(s.share_qauid, s.question?.slice(0, 20))}
                      >
                        <span className="session-title">{s.question?.slice(0, 30) || '(제목 없음)'}</span>
                        <span className="session-date-badge">{s.created_at?.slice(5, 10)}</span>
                        <button type="button" className="session-menu-btn" onClick={(e) => handleMenuClick(e, s.share_qauid, 'received')}>···</button>
                      </li>
                    ))}
                </ul>
              )}
            </div>

            {/* 즐겨찾기 */}
            <div className="sidebar-section fav-section">
              <SectionHeader sectionKey="favorites" icon="★" label="즐겨찾기" count={favorites.length} iconActive={favorites.length > 0} />
              {openSections.favorites && (
                <ul className="session-list">
                  {favorites.length === 0
                    ? <li className="sidebar-empty">즐겨찾기가 없습니다.</li>
                    : favorites.map((f) => (
                      <li
                        key={f.qauid}
                        className={`session-item ${f.qauid === viewingFavoriteQauid ? 'viewing' : ''}`}
                        onClick={() => handleSelectFavorite(f)}
                      >
                        <span className="session-fav-star">★</span>
                        <span className="session-title">{f.question?.slice(0, 35) || '(내용 없음)'}</span>
                        <span className="session-date-badge">{f.created_at?.slice(5, 10)}</span>
                        <button type="button" className="session-menu-btn" onClick={(e) => handleMenuClick(e, f.qauid, 'favorites')}>···</button>
                      </li>
                    ))}
                </ul>
              )}
            </div>

            {/* 보고서 목록 (날짜별) */}
            <div className="sidebar-section">
              <SectionHeader
                sectionKey="history" icon="💬" label="대화 목록"
                count={Object.values(history).flat().filter((s) => s.session_id !== sessionId).length}
              />
              {openSections.history && (
                filteredHistory.length === 0 ? (
                  <p className="sidebar-empty">이전 대화가 없습니다.</p>
                ) : filteredHistory.map(([d, sessions]) => (
                  <div key={d} className="date-group">
                    <button type="button" className={`date-toggle ${openDates[d] ? 'open' : ''}`} onClick={() => toggleDate(d)}>
                      <span>{d} <span className="section-count date-count">{sessions.length}</span></span>
                      <span className="arrow">{openDates[d] ? '▾' : '▸'}</span>
                    </button>
                    {openDates[d] && (
                      <ul className="session-list">
                        {sessions.map((s) => (
                          <li
                            key={s.session_id}
                            className={`session-item ${s.session_id === viewingSessionId ? 'viewing' : ''}`}
                            onClick={() => handleSelectSession(s.session_id)}
                          >
                            <span
                              className={`session-fav-indicator ${favoritedSessionIds.has(s.session_id) ? 'fav-on' : ''}`}
                              title={favoritedSessionIds.has(s.session_id) ? '즐겨찾기된 보고서 있음' : ''}
                            >★</span>
                            <span className="session-title">{s.title}</span>
                            <button type="button" className="session-menu-btn" onClick={(e) => handleMenuClick(e, s.session_id)}>···</button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))
              )}
            </div>

          </nav>

          {/* ··· 드롭다운 메뉴 */}
          {menuOpenId && (
            <div className="session-dropdown" style={{ top: menuPos.top, left: menuPos.left }}>
              <button type="button" className="session-dropdown-del" onClick={(e) => handleSidebarDelete(e, menuOpenId)}>삭제</button>
            </div>
          )}
        </aside>

        {/* ── 메인 영역 ── */}
        <div className="d2insight-main">
          <div className="chat-container">
            {viewMode === 'chat' ? (
              <>
                <div className="messages">
                  {messages.map((msg, index) => {
                    const hasAnswer = msg.role === 'user' && messages[index + 1]?.role === 'assistant'
                    const showStar = hasAnswer && msg.qauid
                    const isFav = showStar && favoritedQaids.has(msg.qauid)
                    const starButton = showStar ? (
                      <button
                        type="button"
                        className={`msg-fav-btn${isFav ? ' fav-on' : ''}`}
                        onClick={(e) => { e.stopPropagation(); handleToggleFavorite(msg.qauid) }}
                        title={isFav ? '즐겨찾기 해제' : '즐겨찾기 추가'}
                      >★</button>
                    ) : null

                    return (
                      <div key={index} className="msg-row">
                        <MessageBubble
                          role={msg.role}
                          content={msg.content}
                          fileurl={msg.fileurl}
                          reportPath={msg.reportPath}
                          starButton={starButton}
                          qauid={msg.qauid}
                          onShare={userId ? (qauid) => setShareTarget({ qauid }) : null}
                        />
                      </div>
                    )
                  })}
                  {isLoading && (
                    <div className="loading">
                      <div className="spinner" />
                      <span className="loading-text">보고서를 생성 중입니다...</span>
                    </div>
                  )}
                  <div ref={bottomRef} />
                </div>

                <div className="input-container">
                  <div className="examples">
                    <strong>예시 요청:</strong>
                    {EXAMPLE_QUESTIONS.map((item, index) => (
                      <span key={index} className="example-btn" onClick={() => setInputValue(item.question)}>{item.label}</span>
                    ))}
                  </div>
                  <div className="input-wrapper">
                    <textarea
                      placeholder="보고서 요청을 입력하세요... (예: 2024-01 판매분석 보고서 작성해줘)"
                      value={inputValue}
                      onChange={(e) => setInputValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault()
                          sendMessage()
                        }
                      }}
                    />
                    <button type="button" onClick={() => sendMessage()} disabled={isLoading}>전송</button>
                  </div>
                </div>
              </>
            ) : (
              <div className="history-view">
                <div className="history-bar">
                  <span><strong>이어가기</strong>를 누르면 대화를 이어서 할 수 있습니다.</span>
                  <button
                    type="button"
                    className="history-back-btn"
                    onClick={() => { setViewingSessionId(null); setViewMode('chat') }}
                  >← 현재 대화로</button>
                </div>
                <div className="messages history-messages">
                  {historyMessages.map((msg, index) => {
                    const hasAnswer = msg.role === 'user' && historyMessages[index + 1]?.role === 'assistant'
                    const showStar = hasAnswer && msg.qauid
                    const isFav = showStar && favoritedQaids.has(msg.qauid)
                    const starButton = showStar ? (
                      <button
                        type="button"
                        className={`msg-fav-btn${isFav ? ' fav-on' : ''}`}
                        onClick={(e) => { e.stopPropagation(); handleToggleFavorite(msg.qauid) }}
                        title={isFav ? '즐겨찾기 해제' : '즐겨찾기 추가'}
                      >★</button>
                    ) : null

                    return (
                      <div key={index} className="history-msg-wrapper msg-row">
                        <div className="history-msg-inner">
                          <MessageBubble
                            role={msg.role}
                            content={msg.content}
                            fileurl={msg.fileurl}
                            reportPath={msg.reportPath}
                            starButton={starButton}
                            qauid={msg.qauid}
                            onShare={userId ? (qauid) => setShareTarget({ qauid }) : null}
                          />
                          {msg.role === 'user' && (
                            <div className="fav-btn-row">
                              <button
                                type="button"
                                className="continue-btn"
                                onClick={() => {
                                  const nextMsg = historyMessages[index + 1]
                                  handleContinue({
                                    question: msg.content,
                                    answer: nextMsg?.content || '',
                                    fileurl: nextMsg?.fileurl || null,
                                    reportPath: nextMsg?.reportPath || null,
                                  })
                                }}
                              >이어가기</button>
                            </div>
                          )}
                        </div>
                      </div>
                    )
                  })}
                  <div ref={bottomRef} />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 공유 모달 */}
      {shareTarget && (
        <ShareModal
          qauid={shareTarget.qauid}
          userId={userId}
          onClose={() => setShareTarget(null)}
          onShared={() => fetchShares()}
          message={message}
        />
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────
// 메시지 말풍선
// ─────────────────────────────────────────────────────────────────
function MessageBubble({ role, content, fileurl, reportPath, starButton, qauid, onShare }) {
  const [previewExpanded, setPreviewExpanded] = useState(false)
  const [previewContent, setPreviewContent] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)

  useEffect(() => {
    setPreviewContent('')
    setPreviewExpanded(false)
  }, [fileurl])

  const isMdUrl = fileurl ? /\.md(\?|$)/.test(fileurl) : false
  const mdUrl = fileurl
    ? (isMdUrl ? fileurl : fileurl.replace(/\.pdf(\?.*)?$/, '.md$1'))
    : null
  const pdfUrl = fileurl
    ? (isMdUrl ? fileurl.replace(/\.md(\?.*)?$/, '.pdf$1') : fileurl)
    : null
  const displayName = pdfUrl
    ? decodeURIComponent(pdfUrl.split('/').pop().split('?')[0])
    : (reportPath || '보고서.pdf')

  const handleTogglePreview = async () => {
    if (previewExpanded) { setPreviewExpanded(false); return }
    if (!previewContent && (mdUrl || pdfUrl)) {
      setPreviewLoading(true)
      try {
        if (mdUrl) {
          const res = await fetch(mdUrl)
          if (res.ok) {
            setPreviewContent(await res.text())
          } else {
            setPreviewContent(`__pdf__:${pdfUrl}`)
          }
        } else {
          setPreviewContent(`__pdf__:${pdfUrl}`)
        }
      } catch {
        setPreviewContent(`__pdf__:${pdfUrl || ''}`)
      } finally {
        setPreviewLoading(false)
      }
    }
    setPreviewExpanded(true)
  }

  const handleDownload = async () => {
    if (!pdfUrl) return
    try {
      const res = await fetch(pdfUrl)
      if (!res.ok) throw new Error(res.status)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = displayName
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch { /* silent */ }
  }

  return (
    <div className={`message ${role}`}>
      {role === 'assistant' && (
        <div className="message-label">
          <img className="assistant-icon" src={chatbotBot} alt="assistant" />
        </div>
      )}

      {role === 'user' && starButton}

      <div className="message-content">
        {content}
        {role === 'assistant' && fileurl && (
          <div className="report-card">
            <div className="report-card-header">
              <span className="report-icon">📄</span>
              <span className="report-filename">{displayName}</span>
              <div className="report-btns">
                <button type="button" className="report-btn" onClick={handleTogglePreview} disabled={previewLoading}>
                  {previewLoading ? '로딩 중...' : previewExpanded ? '접기' : '미리보기'}
                </button>
                <button type="button" className="report-btn download" onClick={handleDownload}>다운로드</button>
                {qauid && onShare && (
                  <button type="button" className="report-btn share-btn" onClick={() => onShare(qauid)}>공유</button>
                )}
              </div>
            </div>
            {previewExpanded && previewContent && (
              previewContent.startsWith('__pdf__:')
                ? <iframe src={previewContent.slice(8)} style={{ width: '100%', height: 600, border: 'none' }} title="보고서 미리보기" />
                : <pre className="report-preview-text">{previewContent}</pre>
            )}
          </div>
        )}
      </div>

      {role === 'user' && (
        <div className="message-label">
          <img className="user-icon" src={chatbotHuman} alt="user" />
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────
// 공유 모달 — QA 단위 공유 (tenant 내 공개)
// ─────────────────────────────────────────────────────────────────
function ShareModal({ qauid, userId, onClose, onShared, message }) {
  const [sharing, setSharing] = useState(false)

  const handleShare = async () => {
    setSharing(true)
    try {
      await apiClient.post('/d2insight/share', { user_id: userId, qauid })
      onShared?.()
      onClose()
    } catch (e) {
      message.error(e.response?.data?.detail || '공유 중 오류가 발생했습니다.')
      setSharing(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <h2>보고서 공유</h2>
        <p style={{ color: '#555', fontSize: 14, margin: '0 0 16px' }}>
          이 보고서를 같은 테넌트의 모든 사용자와 공유합니다.
        </p>
        <div className="modal-buttons">
          <button type="button" onClick={handleShare} disabled={sharing}>
            {sharing ? '공유 중...' : '공유하기'}
          </button>
          <button type="button" onClick={onClose} style={{ background: '#6c757d' }}>취소</button>
        </div>
      </div>
    </div>
  )
}
