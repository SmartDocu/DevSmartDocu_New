import { useState, useRef, useCallback, useEffect } from 'react'
import { App } from 'antd'
import { CodeOutlined, CloseOutlined, PaperClipOutlined } from '@ant-design/icons'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import DatasetUploadModal from '@/components/DatasetUploadModal/DatasetUploadModal'
import chatbotBot from '@/assets/icons/chatbot_bot.svg'
import chatbotHuman from '@/assets/icons/chatbot_human.svg'
import '../d2shared/d2common.css'
import './d2chat.css'

const ASK_TIMEOUT = { timeout: 180000 }

const INITIAL_MESSAGE = {
  role: 'assistant',
  content: '안녕하세요! 데이터 분석을 도와드립니다. 무엇을 도와드릴까요?',
  visualization: null,
  visualizationType: null,
}

const EXAMPLE_QUESTIONS = [
  { label: '인터페이스 오류율', question: '오늘 인터페이스 오류율은?' },
  { label: '크리티컬 오류', question: '어제 크리티컬오류는 몇 건인가요?' },
  { label: '평균 처리 시간', question: '인터페이스 평균 처리 시간은?' },
  { label: '미국 매출액 집계', question: '미국의 총 매출액을 년별로 집계해주세요.' },
  { label: '카테고리별 점유율', question: '북 아메리카의 매출을 카테고리별로 점유율을 그래프로 그려주세요.' },
  { label: '미국 내 판매 지역', question: '미국 판매지역을 모두 알려주세요.' },
]


export default function D2ChatPage() {
  const { message } = App.useApp()
  const user = useAuthStore((s) => s.user)

  // ── 대화 상태 ──────────────────────────────────────────────────
  const [sessionId, setSessionId] = useState(null)
  const sessionIdRef = useRef(null)
  const updateSessionId = (id) => { setSessionId(id); sessionIdRef.current = id }

  const [messages, setMessages] = useState([INITIAL_MESSAGE])
  const [queryHistory, setQueryHistory] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [queryPanelOpen, setQueryPanelOpen] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const [showAutoTest, setShowAutoTest] = useState(true)
  const [viewMode, setViewMode] = useState('chat') // 'chat' | 'history'
  const [historyMessages, setHistoryMessages] = useState([])
  const [historyLabel, setHistoryLabel] = useState('')
  const [viewingSessionId, setViewingSessionId] = useState(null)
  const [viewingSnapshotId, setViewingSnapshotId] = useState(null)
  const [viewingFavoriteQauid, setViewingFavoriteQauid] = useState(null)
  const [favorites, setFavorites] = useState([])

  // ── 사이드바 상태 ──────────────────────────────────────────────
  const [history, setHistory] = useState({})
  const [sharesSent, setSharesSent] = useState([])
  const [sharesReceived, setSharesReceived] = useState([])
  const [openSections, setOpenSections] = useState({ sent: false, received: false, favorites: false, history: true })
  const [openDates, setOpenDates] = useState({})
  const [menuOpenId, setMenuOpenId] = useState(null)
  const [menuSection, setMenuSection] = useState(null) // 'history' | 'favorites' | 'sent' | 'received'
  const [menuPos, setMenuPos] = useState({ top: 0, left: 0 })
  const [shareTarget, setShareTarget] = useState(null)
  const [datasetModalOpen, setDatasetModalOpen] = useState(false)

  const bottomRef = useRef(null)

  const favoritedQaids = new Set(favorites.map((f) => f.qauid))
  const favoritedSessionIds = new Set(favorites.map((f) => f.session_id))

  // ── 데이터 로드 ────────────────────────────────────────────────
  const fetchFavorites = useCallback(async () => {
    try {
      const { data } = await apiClient.get('/d2chat/favorites')
      setFavorites(data || [])
    } catch {
      // ignore
    }
  }, [])

  const fetchHistory = useCallback(async () => {
    try {
      const { data } = await apiClient.get('/d2chat/history')
      setHistory(data || {})
      const today = new Date().toISOString().slice(0, 10)
      if (data?.[today]) setOpenDates((prev) => ({ ...prev, [today]: true }))
    } catch {
      // ignore
    }
  }, [])

  const fetchShares = useCallback(async () => {
    try {
      const [sentRes, receivedRes] = await Promise.all([
        apiClient.get('/d2chat/shares/sent'),
        apiClient.get('/d2chat/shares/received'),
      ])
      setSharesSent(sentRes.data || [])
      setSharesReceived(receivedRes.data || [])
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => { fetchFavorites() }, [fetchFavorites])
  useEffect(() => { fetchHistory(); fetchShares() }, [sessionId, fetchHistory, fetchShares])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading, historyMessages])

  // 외부 클릭 시 ··· 드롭다운 메뉴 닫기
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
    setQueryHistory([])
    setShowAutoTest(true)
    setViewingSessionId(null)
    setViewingSnapshotId(null)
    setViewingFavoriteQauid(null)
    setViewMode('chat')
  }

  const handleSelectSession = async (sid) => {
    try {
      const { data } = await apiClient.get(`/d2chat/history/${sid}`)
      setHistoryMessages(data.messages || [])
      setHistoryLabel('과거 대화 보기')
      setViewingSessionId(sid)
      setViewingSnapshotId(null)
      setViewingFavoriteQauid(null)
      setViewMode('history')
    } catch {
      // ignore
    }
  }

  const handleSelectFavorite = (fav) => {
    setHistoryMessages([
      { role: 'user', content: fav.question, qauid: fav.qauid },
      {
        role: 'assistant', content: fav.answer,
        visualization_type: fav.visualization_type,
        table_html: fav.table_html,
        chart_image: fav.chart_image,
      },
    ])
    setHistoryLabel('즐겨찾기 대화')
    setViewingSessionId(null)
    setViewingSnapshotId(null)
    setViewingFavoriteQauid(fav.qauid)
    setViewMode('history')
  }

  const handleToggleFavorite = async (qauid) => {
    try {
      if (favoritedQaids.has(qauid)) {
        await apiClient.delete(`/d2chat/favorite/qa/${qauid}`)
      } else {
        await apiClient.post('/d2chat/favorite/qa', { qauid })
      }
      fetchFavorites()
    } catch (e) {
      message.error(e.response?.data?.detail || '즐겨찾기 처리 중 오류가 발생했습니다.')
    }
  }

  const handleDeleteFavorite = async (qauid) => {
    try {
      await apiClient.delete(`/d2chat/favorite/qa/${qauid}`)
      fetchFavorites()
    } catch (e) {
      message.error(e.response?.data?.detail || '즐겨찾기 삭제 중 오류가 발생했습니다.')
    }
  }

  const handleSelectSnapshot = async (shareUid, label) => {
    try {
      const { data } = await apiClient.get(`/d2chat/snapshots/${shareUid}`)
      setHistoryMessages(data.messages || [])
      setHistoryLabel(label || '공유받은 대화')
      setViewingSessionId(null)
      setViewingSnapshotId(shareUid)
      setViewingFavoriteQauid(null)
      setViewMode('history')
    } catch {
      // ignore
    }
  }

  const handleContinue = async ({ question, answer, query, visualization_type, table_html, chart_image }) => {
    try {
      const { data } = await apiClient.post('/d2chat/session/inject', {
        session_id: sessionId,
        project_id: user?.projectid ?? null,
        question, answer, query, visualization_type, table_html, chart_image,
      })
      if (data.session_id) updateSessionId(data.session_id)

      const visualization =
        visualization_type === 'table' ? table_html
        : visualization_type === 'chart' ? chart_image
        : null

      setMessages((prev) => [
        ...prev,
        { role: 'user', content: question, visualization: null, visualizationType: null },
        { role: 'assistant', content: answer, visualization, visualizationType: visualization_type },
      ])
      setViewingSessionId(null)
      setViewingSnapshotId(null)
      setViewingFavoriteQauid(null)
      setShowAutoTest(false)
      setViewMode('chat')
    } catch (e) {
      message.error(e.response?.data?.detail || '이어가기 중 오류가 발생했습니다.')
    }
  }

  const addMessage = (role, content, visualization = null, visualizationType = null) => {
    setMessages((prev) => [...prev, { role, content, visualization, visualizationType }])
  }

  const addQueryToHistory = (question, queries) => {
    const queryArray = Array.isArray(queries) ? queries : [{ query: queries, table: null }]
    setQueryHistory((prev) => [...prev, { question, queries: queryArray }])
  }

  const sendQuestion = async (overrideQuestion = null) => {
    const question = (typeof overrideQuestion === 'string' ? overrideQuestion : inputValue).trim()
    if (!question || isLoading) return

    addMessage('user', question)
    setInputValue('')
    setShowAutoTest(false)
    setIsLoading(true)

    try {
      const { data } = await apiClient.post(
        '/d2chat/ask',
        { question, session_id: sessionIdRef.current, project_id: user?.projectid ?? null, account_uid: user?.accountuid ?? null },
        ASK_TIMEOUT,
      )

      if (data.status === 'success') {
        if (data.session_id) updateSessionId(data.session_id)

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

        if (data.queries && data.queries.length > 0) {
          addQueryToHistory(question, data.queries)
        } else if (data.query) {
          addQueryToHistory(question, [{ query: data.query, table: null }])
        }

        const visualization =
          data.visualization_type === 'table' ? data.table_html
          : data.visualization_type === 'chart' ? data.chart_image
          : null

        addMessage('assistant', data.answer, visualization, data.visualization_type)
      } else {
        addMessage('assistant', '오류: ' + (data.error || '알 수 없는 오류'))
      }
    } catch (error) {
      addMessage('assistant', '오류가 발생했습니다: ' + (error.response?.data?.detail || error.message))
    } finally {
      setIsLoading(false)
    }
  }

  const handleDatasetUploaded = (data) => {
    if (data.session_id) updateSessionId(data.session_id)
    setShowAutoTest(false)

    const summary = data.datasets
      .map((d) => `- ${d.filename} (행 ${d.row_count}, 컬럼 ${d.columns.length}) : ${d.description || ''}`)
      .join('\n')
    addMessage(
      'assistant',
      `데이터셋이 등록되었습니다. 이제부터 이 대화는 아래 데이터를 대상으로 답변합니다 (기존 DB 조회는 사용되지 않습니다).\n${summary}`,
    )
  }

  const runAutoTest = async () => {
    try {
      const { data } = await apiClient.get('/d2chat/questions')
      const questions = data.questions || []
      for (let i = 0; i < questions.length; i++) {
        await sendQuestion(questions[i])
        await new Promise((resolve) => setTimeout(resolve, 1000))
      }
    } catch (error) {
      addMessage('assistant', '질문 목록을 가져오는 중 오류 발생: ' + error.message)
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
        await handleDeleteFavorite(id)
      } else if (menuSection === 'sent') {
        await apiClient.delete(`/d2chat/shares/sent/${id}`)
        fetchShares()
      } else if (menuSection === 'received') {
        await apiClient.delete(`/d2chat/shares/received/${id}`)
        fetchShares()
      } else {
        await apiClient.delete(`/d2chat/history/${id}`)
        fetchHistory()
        if (id === sessionId) handleNewChat()
      }
    } catch (e2) {
      message.error(e2.response?.data?.detail || '삭제 중 오류가 발생했습니다.')
    }
  }

  const handleShareOpen = (e, session) => {
    e.stopPropagation()
    setMenuOpenId(null)
    setShareTarget({ session_id: session.session_id, title: session.title })
  }

  const handleShared = () => fetchShares()

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
          <div>AI 데이터 분석 챗봇</div>
        </div>
      </div>

      <div className="d2chat-layout">

        {/* ── 사이드바 ── */}
        <aside className="d2chat-sidebar">
          <div className="current-session-block">
            <span className="current-session-label">현재 대화</span>
            <span className="current-session-title">{currentTitle || '아직 질문이 없습니다.'}</span>
          </div>

          <div className="sidebar-newchat">
            <button type="button" className="new-chat-btn" onClick={handleNewChat}>+ 새 대화</button>
          </div>

          <nav className="sidebar-nav">

            {/* 공유한 내역 */}
            <div className="sidebar-section">
              <SectionHeader sectionKey="sent" icon="↑" label="공유한 내역" count={sharesSent.length} />
              {openSections.sent && (
                <ul className="session-list">
                  {sharesSent.length === 0
                    ? <li className="sidebar-empty">공유한 대화가 없습니다.</li>
                    : sharesSent.map((s) => (
                      <li
                        key={s.shareuid}
                        className={`session-item ${s.shareuid === viewingSnapshotId ? 'viewing' : ''}`}
                        onClick={() => handleSelectSnapshot(s.shareuid, s.sessiontitles)}
                      >
                        <span className="session-title">{s.sessiontitles || '(제목 없음)'}</span>
                        <span className="session-date-badge">{s.createdts?.slice(5, 10)}</span>
                        {/* <span className="session-date-badge">{s.createdt?.slice(5)}</span> */}
                        <button type="button" className="session-menu-btn" onClick={(e) => handleMenuClick(e, s.shareuid, 'sent')}>···</button>
                      </li>
                    ))}
                </ul>
              )}
            </div>

            {/* 공유받은 내역 */}
            <div className="sidebar-section">
              <SectionHeader sectionKey="received" icon="↓" label="공유받은 내역" count={sharesReceived.length} />
              {openSections.received && (
                <ul className="session-list">
                  {sharesReceived.length === 0
                    ? <li className="sidebar-empty">공유받은 대화가 없습니다.</li>
                    : sharesReceived.map((s) => (
                      <li
                        key={s.shareuid}
                        className={`session-item ${s.shareuid === viewingSnapshotId ? 'viewing' : ''}`}
                        onClick={() => handleSelectSnapshot(s.shareuid, s.sessiontitles)}
                      >
                        <span className="session-title">{s.sessiontitles || '(제목 없음)'}</span>
                        <span className="session-date-badge">{s.createdts?.slice(5, 10)}</span>
                        {/* <span className="session-date-badge">{s.createdt?.slice(5)}</span> */}
                        <button type="button" className="session-menu-btn" onClick={(e) => handleMenuClick(e, s.shareuid, 'received')}>···</button>
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

            {/* 대화 목록 (날짜별) */}
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
                              title={favoritedSessionIds.has(s.session_id) ? '즐겨찾기된 대화 있음' : ''}
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
              {menuSection !== 'sent' && menuSection !== 'favorites' && menuSection !== 'received' && (
                <button
                  type="button"
                  className="session-dropdown-item"
                  onClick={(e) => {
                    const session = Object.values(history).flat().find((s) => s.session_id === menuOpenId)
                    if (session) handleShareOpen(e, session)
                  }}
                >공유</button>
              )}
              <button type="button" className="session-dropdown-del" onClick={(e) => handleSidebarDelete(e, menuOpenId)}>삭제</button>
            </div>
          )}
        </aside>

        {/* ── 메인 영역 ── */}
        <div className="d2chat-main">
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
                          visualization={msg.visualization}
                          visualizationType={msg.visualizationType}
                          starButton={starButton}
                        />
                      </div>
                    )
                  })}
                  {isLoading && (
                    <div className="loading">
                      <div className="spinner" />
                      <span className="loading-text">분석 중입니다...</span>
                    </div>
                  )}
                  <div ref={bottomRef} />
                </div>

                <div className="input-container">
                  <div className="examples">
                    <strong>예시 질문:</strong>
                    {EXAMPLE_QUESTIONS.map((item, index) => (
                      <span key={index} className="example-btn" onClick={() => setInputValue(item.question)}>{item.label}</span>
                    ))}
                  </div>
                  <div className="input-wrapper">
                    <textarea
                      id="questionInput"
                      placeholder="질문을 입력하세요..."
                      value={inputValue}
                      onChange={(e) => setInputValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault()
                          sendQuestion()
                        }
                      }}
                    />
                    <button type="button" id="sendBtn" onClick={() => sendQuestion()} disabled={isLoading}>전송</button>
                    {showAutoTest && (
                      <button type="button" id="autoTestBtn" onClick={runAutoTest} disabled={isLoading}>📋 자동실행</button>
                    )}
                    <button
                      type="button"
                      className="toggle-query-btn"
                      title="데이터셋 추가 (파일 업로드 / API 연결)"
                      onClick={() => setDatasetModalOpen(true)}
                    >
                      <PaperClipOutlined style={{ fontSize: 18 }} />
                      <span>데이터 추가</span>
                    </button>
                    <button
                      type="button"
                      className="toggle-query-btn"
                      title={queryPanelOpen ? '쿼리 숨기기' : '쿼리 보기'}
                      onClick={() => setQueryPanelOpen((prev) => !prev)}
                    >
                      {queryPanelOpen ? <CloseOutlined style={{ fontSize: 18 }} /> : <CodeOutlined style={{ fontSize: 18 }} />}
                      <span>{queryPanelOpen ? '쿼리숨기기' : '쿼리보기'}</span>
                    </button>
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
                            visualization={
                              msg.visualization_type === 'table' ? msg.table_html
                              : msg.visualization_type === 'chart' ? msg.chart_image
                              : null
                            }
                            visualizationType={msg.visualization_type}
                            starButton={starButton}
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
                                    query: nextMsg?.query || null,
                                    visualization_type: nextMsg?.visualization_type || 'none',
                                    table_html: nextMsg?.table_html || null,
                                    chart_image: nextMsg?.chart_image || null,
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

          <div className={`query-panel ${queryPanelOpen ? 'active' : ''}`}>
            <div className="query-header">
              <span>쿼리 히스토리</span>
              <button type="button" className="query-close" onClick={() => setQueryPanelOpen(false)}>×</button>
            </div>
            <div className="query-content">
              {queryHistory.map((item, index) => (
                <div className="query-item" key={index}>
                  <div className="query-question">Q: {item.question}</div>
                  {item.queries.map((q, qIndex) => (
                    <div key={qIndex}>
                      {item.queries.length > 1 && (
                        <div style={{ fontSize: 11, color: '#666', marginBottom: 5, fontWeight: 600 }}>쿼리 {qIndex + 1}</div>
                      )}
                      <div className="query-sql">{q.query.trim()}</div>
                      <button
                        type="button"
                        onClick={() => {
                          navigator.clipboard.writeText(q.query.trim()).then(() => {
                            message.success('쿼리가 복사되었습니다!')
                          })
                        }}
                        style={{
                          color: '#fff', background: '#0e66c4', padding: '2px 12px', marginTop: 4,
                          border: '1px solid #0e66c4', borderRadius: 4, cursor: 'pointer',
                        }}
                      >복  사</button>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 공유 모달 */}
      {shareTarget && (
        <ShareModal
          sessionId={shareTarget.session_id}
          sessionTitle={shareTarget.title}
          onClose={() => setShareTarget(null)}
          onShared={handleShared}
        />
      )}

      {/* 데이터셋 추가(업로드/API) 모달 */}
      <DatasetUploadModal
        open={datasetModalOpen}
        sessionId={sessionId}
        onClose={() => setDatasetModalOpen(false)}
        onSuccess={handleDatasetUploaded}
      />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────
// 메시지 말풍선
// ─────────────────────────────────────────────────────────────────
function MessageBubble({ role, content, visualization, visualizationType, starButton }) {
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
        {visualization && (
          <div className="visualization-container">
            {visualizationType === 'table' && <div dangerouslySetInnerHTML={{ __html: visualization }} />}
            {visualizationType === 'chart' && <img src={`data:image/png;base64,${visualization}`} alt="차트" />}
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
// 공유 모달 — 같은 테넌트 사용자에게 대화 공유
// ─────────────────────────────────────────────────────────────────
function ShareModal({ sessionId, sessionTitle, onClose, onShared }) {
  const { message } = App.useApp()
  const [users, setUsers] = useState([])
  const [selected, setSelected] = useState([])
  const [loading, setLoading] = useState(true)
  const [sharing, setSharing] = useState(false)

  useEffect(() => {
    apiClient.get('/d2chat/users/same-tenant')
      .then(({ data }) => { setUsers(data || []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const toggle = (uid) =>
    setSelected((prev) => (prev.includes(uid) ? prev.filter((id) => id !== uid) : [...prev, uid]))

  const handleShare = async () => {
    if (selected.length === 0) return
    setSharing(true)
    try {
      await apiClient.post('/d2chat/share', {
        session_id: sessionId,
        session_titles: sessionTitle,
        target_user_uids: selected,
      })
      onShared?.()
      onClose()
    } catch (e) {
      message.error(e.response?.data?.detail || '공유 중 오류가 발생했습니다.')
      setSharing(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box share-modal" onClick={(e) => e.stopPropagation()}>
        <h2>대화 공유</h2>
        <p className="share-session-title">&quot;{sessionTitle}&quot;</p>

        {loading ? (
          <p className="share-loading">사용자 목록 로딩 중...</p>
        ) : users.length === 0 ? (
          <p className="share-loading">공유 가능한 사용자가 없습니다.</p>
        ) : (
          <ul className="share-user-list">
            {users.map((u) => (
              <li key={u.creator} className="share-user-item">
                <label>
                  <input type="checkbox" checked={selected.includes(u.creator)} onChange={() => toggle(u.creator)} />
                  <span>{u.email}</span>
                </label>
              </li>
            ))}
          </ul>
        )}

        <div className="modal-buttons">
          <button type="button" onClick={handleShare} disabled={selected.length === 0 || sharing}>
            {sharing ? '공유 중...' : `공유 (${selected.length}명)`}
          </button>
          <button type="button" onClick={onClose} style={{ background: '#6c757d' }}>취소</button>
        </div>
      </div>
    </div>
  )
}
