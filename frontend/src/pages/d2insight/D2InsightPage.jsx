import { useState, useRef, useCallback, useEffect } from 'react'
import { App } from 'antd'
import { PaperClipOutlined } from '@ant-design/icons'
import { marked } from 'marked'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import DatasetUploadModal from '@/components/DatasetUploadModal/DatasetUploadModal'
import chatbotBot from '@/assets/icons/chatbot_bot.svg'
import chatbotHuman from '@/assets/icons/chatbot_human.svg'
import '../d2shared/d2common.css'
import './d2insight.css'

const CHAT_TIMEOUT = { timeout: 3600000 } // 보고서 생성 최대 6분

function getInitialMessage() {
  return {
    role: 'assistant',
    // 다국어 테이블에 저장된 텍스트가 실제 개행 문자 대신 리터럴 "\n"으로 들어있는 경우가
    // 있어(수동 입력 시 이스케이프가 해석되지 않음), 렌더링 전에 실제 개행으로 치환한다.
    content: t('msg.d2insight.welcome').replace(/\\n/g, '\n'),
    fileurl: null,
    reportPath: null,
  }
}

const EXAMPLE_QUESTION_DEFS = [
  { labelKey: 'btn.d2insight.example_sales', questionKey: 'msg.d2insight.example_sales_question' },
  { labelKey: 'btn.d2insight.example_serverlog', questionKey: 'msg.d2insight.example_serverlog_question' },
  { labelKey: 'btn.d2insight.example_interfacelog', questionKey: 'msg.d2insight.example_interfacelog_question' },
]


export default function D2InsightPage() {
  useLangStore((s) => s.translations)
  const { message, modal } = App.useApp()
  const user = useAuthStore((s) => s.user)
  const userId = user?.id
  const EXAMPLE_QUESTIONS = EXAMPLE_QUESTION_DEFS.map((d) => ({ label: t(d.labelKey), question: t(d.questionKey) }))

  // ── 대화 상태 ──────────────────────────────────────────────────
  const [sessionId, setSessionId] = useState(null)
  const sessionIdRef = useRef(null)
  const updateSessionId = (id) => { setSessionId(id); sessionIdRef.current = id }

  const [messages, setMessages] = useState([getInitialMessage()])
  const [isLoading, setIsLoading] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const [viewMode, setViewMode] = useState('chat') // 'chat' | 'history'
  const [historyMessages, setHistoryMessages] = useState([])
  const [historyLabel, setHistoryLabel] = useState('')
  const [viewingSessionId, setViewingSessionId] = useState(null)
  const [viewingFavoriteQauid, setViewingFavoriteQauid] = useState(null)
  const [favorites, setFavorites] = useState([])
  const [shareTarget, setShareTarget] = useState(null) // {qauid}
  const [datasetModalOpen, setDatasetModalOpen] = useState(false)

  // ── 사이드바 상태 ──────────────────────────────────────────────
  const [history, setHistory] = useState({})
  const [sharesSent, setSharesSent] = useState([])
  const [sharesReceived, setSharesReceived] = useState([])
  const [openSections, setOpenSections] = useState({
    favorites: false, history: false, schedules: false, sent: false, received: false,
    sentSchedule: false, receivedSchedule: false,
  })
  const [openDates, setOpenDates] = useState({})
  const [openSchedules, setOpenSchedules] = useState({}) // sessionId → 펼침여부
  const [scheduleTurns, setScheduleTurns] = useState({}) // sessionId → 턴배열 | 'loading'
  const [viewingScheduleQauid, setViewingScheduleQauid] = useState(null)
  const [viewingScheduleSessionId, setViewingScheduleSessionId] = useState(null)
  const [scheduleSettings, setScheduleSettings] = useState(null) // 현재 보이는 정기 보고서의 요일/시간 설정(수정용)
  const [activeReportIndex, setActiveReportIndex] = useState(null) // 클릭해 선택한 말풍선(보고서) 인덱스 — null이면 최신 보고서 기본 표시

  // 보고서 preview (단독앱 pr_module_insight_202608061005 방식) — 채팅 send 시 서버에서
  // 시나리오 매칭 결과와 스텝-모듈-툴 목록을 받아 오른편 옵션 패널에 표시. "이대로 작성"
  // 클릭 시 이 데이터를 옵션 JSON으로 실어 /chat에 실제 실행 요청. null이면 preview 없음.
  const [previewData, setPreviewData] = useState(null)
  const [previewOriginalMessage, setPreviewOriginalMessage] = useState('')

  // 정기 보고서 공유(공유한/공유받은)
  const [sharesSentSchedule, setSharesSentSchedule] = useState([])
  const [sharesReceivedSchedule, setSharesReceivedSchedule] = useState([])
  const [openSentSchedules, setOpenSentSchedules] = useState({}) // share_uid → 펼침여부
  const [sentScheduleTurns, setSentScheduleTurns] = useState({})
  const [openSharedSchedules, setOpenSharedSchedules] = useState({})
  const [sharedScheduleTurns, setSharedScheduleTurns] = useState({})

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

  const fetchScheduleShares = useCallback(async () => {
    if (!userId) return
    try {
      const [sentRes, receivedRes] = await Promise.all([
        apiClient.get(`/d2insight/schedule/shares/sent/${userId}`),
        apiClient.get(`/d2insight/schedule/shares/received/${userId}`),
      ])
      setSharesSentSchedule(sentRes.data || [])
      setSharesReceivedSchedule(receivedRes.data || [])
    } catch {
      // ignore
    }
  }, [userId])

  const loadScheduleSettings = useCallback(async (sid) => {
    if (!sid) { setScheduleSettings(null); return }
    try {
      const { data } = await apiClient.get(`/d2insight/schedule/${sid}/settings`)
      setScheduleSettings({ ...data, session_id: sid })
    } catch {
      setScheduleSettings(null)
    }
  }, [])

  // 최초 진입/세션 전환 시 사이드바 데이터를 한 번에 불러온다 (offsetminutes 6회 조회 → 1회).
  // 개별 액션 후 부분 갱신은 위 fetchFavorites/fetchHistory/fetchShares/fetchScheduleShares를 그대로 사용한다.
  const fetchBootstrap = useCallback(async () => {
    if (!userId) return
    try {
      const { data } = await apiClient.get(`/d2insight/bootstrap/${userId}`)
      setFavorites(data?.favorites || [])
      setHistory(data?.history || {})
      setSharesSent(data?.shares_sent || [])
      setSharesReceived(data?.shares_received || [])
      setSharesSentSchedule(data?.schedule_shares_sent || [])
      setSharesReceivedSchedule(data?.schedule_shares_received || [])
    } catch {
      // ignore
    }
  }, [userId])

  useEffect(() => { fetchBootstrap() }, [sessionId, fetchBootstrap])
  useEffect(() => {
    if (viewMode === 'chat') loadScheduleSettings(sessionId)
  }, [sessionId, viewMode, loadScheduleSettings])

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
    setMessages([getInitialMessage()])
    setViewingSessionId(null)
    setViewingFavoriteQauid(null)
    setViewingScheduleQauid(null)
    setViewingScheduleSessionId(null)
    setScheduleSettings(null)
    setActiveReportIndex(null)
    setViewMode('chat')
    setInputValue('')
  }

  const handleSelectSession = async (sid) => {
    if (!userId) return
    try {
      const { data } = await apiClient.get(`/d2insight/history/${userId}/${sid}`)
      setHistoryMessages(data.messages || [])
      setHistoryLabel(t('msg.d2insight.view_past_report'))
      setViewingSessionId(sid)
      setViewingFavoriteQauid(null)
      setViewingScheduleQauid(null)
      setViewingScheduleSessionId(null)
      setScheduleSettings(null)
      setActiveReportIndex(null)
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
    setHistoryLabel(t('msg.d2insight.favorite_report'))
    setViewingSessionId(null)
    setViewingFavoriteQauid(fav.qauid)
    setViewingScheduleQauid(null)
    setViewingScheduleSessionId(null)
    setScheduleSettings(null)
    setActiveReportIndex(null)
    setViewMode('history')
  }

  const handleSelectShare = async (shareQauid, label) => {
    try {
      const { data } = await apiClient.get(`/d2insight/shares/${shareQauid}`)
      let answerText = ''
      let appliedSteps = null
      try {
        const parsed = JSON.parse(data.answer || '{}')
        answerText = parsed.answer || ''
        // 내가 공유한 것일 때만 우측 패널(모듈/툴/파라미터)을 복원한다 — 남이 공유한 것을
        // 받아 볼 때는 그 세부 구성까지 노출할 필요가 없다.
        if (data.creator === userId) appliedSteps = parsed.applied_steps || null
      } catch { answerText = data.answer || '' }
      setHistoryMessages([
        { role: 'user', content: data.question || '' },
        { role: 'assistant', content: answerText, fileurl: data.fileurl, reportPath: data.filenm, appliedSteps },
      ])
      setHistoryLabel(label || t('ttl.d2insight.shares_received'))
      setViewingSessionId(null)
      setViewingFavoriteQauid(null)
      setViewingScheduleQauid(null)
      setViewingScheduleSessionId(null)
      setScheduleSettings(null)
      setActiveReportIndex(null)
      setViewMode('history')
    } catch {
      // ignore
    }
  }

  // 정기 보고서 회차(턴) 지연 조회 — 제목을 처음 펼칠 때만 조회한다.
  const loadScheduleTurns = async (sid) => {
    setScheduleTurns((prev) => ({ ...prev, [sid]: 'loading' }))
    try {
      const { data } = await apiClient.get(`/d2insight/schedule/${sid}/turns`)
      setScheduleTurns((prev) => ({ ...prev, [sid]: Array.isArray(data) ? data : [] }))
    } catch {
      setScheduleTurns((prev) => ({ ...prev, [sid]: [] }))
    }
  }

  const toggleSchedule = (sid) => {
    setOpenSchedules((prev) => ({ ...prev, [sid]: !prev[sid] }))
    if (scheduleTurns[sid] === undefined) loadScheduleTurns(sid)
  }

  // 공유한/공유받은 정기 보고서 회차 지연 조회 — 둘 다 같은 엔드포인트(share_uid 기준)를 쓴다.
  const loadSentScheduleTurns = async (shareUid) => {
    setSentScheduleTurns((prev) => ({ ...prev, [shareUid]: 'loading' }))
    try {
      const { data } = await apiClient.get(`/d2insight/schedule/shares/${shareUid}/turns`)
      setSentScheduleTurns((prev) => ({ ...prev, [shareUid]: Array.isArray(data) ? data : [] }))
    } catch {
      setSentScheduleTurns((prev) => ({ ...prev, [shareUid]: [] }))
    }
  }

  const toggleSentSchedule = (shareUid) => {
    setOpenSentSchedules((prev) => ({ ...prev, [shareUid]: !prev[shareUid] }))
    if (sentScheduleTurns[shareUid] === undefined) loadSentScheduleTurns(shareUid)
  }

  const loadSharedScheduleTurns = async (shareUid) => {
    setSharedScheduleTurns((prev) => ({ ...prev, [shareUid]: 'loading' }))
    try {
      const { data } = await apiClient.get(`/d2insight/schedule/shares/${shareUid}/turns`)
      setSharedScheduleTurns((prev) => ({ ...prev, [shareUid]: Array.isArray(data) ? data : [] }))
    } catch {
      setSharedScheduleTurns((prev) => ({ ...prev, [shareUid]: [] }))
    }
  }

  const toggleSharedSchedule = (shareUid) => {
    setOpenSharedSchedules((prev) => ({ ...prev, [shareUid]: !prev[shareUid] }))
    if (sharedScheduleTurns[shareUid] === undefined) loadSharedScheduleTurns(shareUid)
  }

  const handleSelectScheduleTurn = (turn, session) => {
    setHistoryMessages([
      { role: 'user', content: turn.question, qauid: turn.qauid },
      { role: 'assistant', content: turn.answer, reportPath: turn.filenm, fileurl: turn.fileurl, qauid: turn.qauid, appliedSteps: turn.appliedSteps },
    ])
    setHistoryLabel(turn.target_period ? `${session.title} · ${turn.target_period}` : session.title)
    setViewingSessionId(null)
    setViewingFavoriteQauid(null)
    setViewingScheduleQauid(turn.qauid)
    setViewingScheduleSessionId(session.session_id)
    setActiveReportIndex(null)
    loadScheduleSettings(session.session_id)
    setViewMode('history')
  }

  // 공유받은 정기 보고서 회차 선택 — 남의 것이라 수정 UI를 띄우지 않는다(scheduleSettings 그대로 null).
  const handleSelectSharedScheduleTurn = (turn, shareMeta) => {
    setHistoryMessages([
      { role: 'user', content: turn.question, qauid: turn.qauid },
      { role: 'assistant', content: turn.answer, reportPath: turn.filenm, fileurl: turn.fileurl, qauid: turn.qauid, appliedSteps: turn.appliedSteps },
    ])
    setHistoryLabel(turn.target_period ? `${shareMeta.title} · ${turn.target_period}` : shareMeta.title)
    setViewingSessionId(null)
    setViewingFavoriteQauid(null)
    setViewingScheduleQauid(turn.qauid)
    setViewingScheduleSessionId(null)
    setScheduleSettings(null)
    setActiveReportIndex(null)
    setViewMode('history')
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
      message.error(e.response?.data?.detail || t('msg.d2insight.fav_error'))
    }
  }

  const handleContinue = async ({ question, answer, fileurl, reportPath }) => {
    try {
      const { data } = await apiClient.post('/d2insight/session/inject', {
        session_id: sessionId,
        user_id: userId,
        project_id: user?.myprojectid ?? null,
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
      setViewingScheduleQauid(null)
      setViewingScheduleSessionId(null)
      setActiveReportIndex(null)
      setViewMode('chat')
    } catch (e) {
      message.error(e.response?.data?.detail || t('msg.d2insight.continue_error'))
    }
  }

  // 실제 /chat 실행 — sendMessage(preview 흐름 성공 시) 또는 handleConfirmPreview에서 호출.
  const _executeChat = async (text, options = null) => {
    try {
      const payload = {
        message: text,
        session_id: sessionIdRef.current,
        user_id: userId,
        project_id: user?.myprojectid ?? null,
        account_uid: user?.accountuid ?? null,
      }
      if (options) payload.options = options
      const { data } = await apiClient.post('/d2insight/chat', payload, CHAT_TIMEOUT)

      if (data.session_id) updateSessionId(data.session_id)
      if (data.qauid) {
        setMessages((prev) => {
          const updated = [...prev]
          for (let i = updated.length - 1; i >= 0; i--) {
            if (updated[i].role === 'user') { updated[i] = { ...updated[i], qauid: data.qauid }; break }
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
          appliedSteps: data.applied_steps || null,
        },
      ])
      setActiveReportIndex(null)
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: t('msg.d2insight.chat_error_prefix') + (error.response?.data?.detail || error.message) },
      ])
    }
  }

  // "이대로 작성" 클릭 — preview 확정 후 /chat 실제 실행. 옵션은 서버가 이해할 형태로 전달.
  // previewData는 보고서 생성이 끝날 때까지 지우지 않는다 — 생성 중에도 오른쪽 패널이 방금
  // 확인한 스텝 목록을 계속 보여줘야 하고(카탈로그만 남는 빈 화면 방지), 생성이 끝나면 백엔드가
  // 이 스텝 목록을 그대로 되돌려주므로(pipeline_runner.py) 패널 내용이 그대로 이어진다.
  const handleConfirmPreview = async () => {
    if (!previewData || isLoading) return
    const text = previewOriginalMessage
    const options = {
      scenario: previewData.scenario,
      applied_steps: previewData.applied_steps,
    }
    setIsLoading(true)
    try {
      await _executeChat(text, options)
    } finally {
      setPreviewData(null)
      setPreviewOriginalMessage('')
      setIsLoading(false)
    }
  }

  // JSON 편집 저장 시 스키마 기준 재검증(LLM 호출 없음) — 활성/비활성 상태를 다시 계산.
  const handleValidateSteps = async (steps) => {
    const { data } = await apiClient.post('/d2insight/report/validate_steps', {
      steps,
      scenario: previewData?.scenario,
      session_id: sessionIdRef.current,
      user_id: userId,
      project_id: user?.myprojectid ?? null,
      account_uid: user?.accountuid ?? null,
    })
    return data.applied_steps || steps
  }

  const sendMessage = async (overrideText = null) => {
    const text = (typeof overrideText === 'string' ? overrideText : inputValue).trim()
    if (!text || isLoading) return

    setMessages((prev) => [...prev, { role: 'user', content: text }])
    setInputValue('')
    setIsLoading(true)

    // 1) 먼저 preview로 시나리오 매칭 시도 (단독앱 방식). 매칭되면 옵션 패널에 표시하고
    //    실제 /chat은 사용자가 "이대로 작성" 눌러야 실행. 매칭 안 되면 그대로 /chat 진행.
    try {
      const previewResp = await apiClient.post('/d2insight/report/preview', {
        message: text,
        session_id: sessionIdRef.current,
        user_id: userId,
        project_id: user?.myprojectid ?? null,
        account_uid: user?.accountuid ?? null,
      })
      if (previewResp.data?.applied_steps?.length) {
        setPreviewData(previewResp.data)
        setPreviewOriginalMessage(text)
        const scenarioMsg = previewResp.data.scenario
          ? `'${previewResp.data.scenario}' 시나리오로 매칭됐어요.`
          : '보고서 구성을 준비했어요.'
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: `${scenarioMsg} 오른쪽 옵션 패널을 확인하고 '이대로 작성'을 눌러주세요.`,
          },
        ])
        setIsLoading(false)
        return
      }
    } catch (_) {
      // preview 실패해도 조용히 /chat 폴백
    }

    // 2) preview 매칭 없음 → 기존 /chat 흐름 그대로.
    try {
      const { data } = await apiClient.post(
        '/d2insight/chat',
        { message: text, session_id: sessionIdRef.current, user_id: userId, project_id: user?.myprojectid ?? null, account_uid: user?.accountuid ?? null },
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
          appliedSteps: data.applied_steps || null,
        },
      ])
      setActiveReportIndex(null) // 새 답변이 왔으니 다시 "최신 보고서" 기본 표시로
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: t('msg.d2insight.chat_error_prefix') + (error.response?.data?.detail || error.message) },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  const handleDatasetUploaded = (data) => {
    if (data.session_id) updateSessionId(data.session_id)

    const summary = data.datasets
      .map((d) => `- ${d.filename} (행 ${d.row_count}, 컬럼 ${d.columns.length}) : ${d.description || ''}`)
      .join('\n')
    setMessages((prev) => [
      ...prev,
      {
        role: 'assistant',
        content: `${t('msg.d2insight.dataset_registered')}\n${summary}`,
        fileurl: null,
        reportPath: null,
      },
    ])
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

  // 정기 보고서 세션의 현재 공유 여부 — history 목록 응답에 이미 share_uid가 포함돼 있어
  // 메뉴를 열 때마다 별도로 조회하지 않는다.
  const getScheduleShareUid = (sessionId2) =>
    Object.values(history).flat().find((s) => s.session_id === sessionId2)?.share_uid || null

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
      message.error(e2.response?.data?.detail || t('msg.d2insight.delete_error'))
    }
  }

  // ── 정기 보고서 공유 핸들러 ────────────────────────────────────
  const handleShareSchedule = async (sid) => {
    setMenuOpenId(null)
    try {
      await apiClient.post(`/d2insight/schedule/${sid}/share`, { user_id: userId })
      fetchScheduleShares()
    } catch (e) {
      message.error(e.response?.data?.detail || '공유에 실패했습니다.')
    }
  }

  const handleUnshareSchedule = async (shareUid) => {
    setMenuOpenId(null)
    try {
      await apiClient.delete(`/d2insight/schedule/share/${shareUid}/${userId}`)
      fetchScheduleShares()
    } catch (e) {
      message.error(e.response?.data?.detail || '공유 취소에 실패했습니다.')
    }
  }

  // 회차(턴) 하드 삭제 — 되돌릴 수 없어 확인 팝업을 거친다.
  const handleDeleteScheduleTurn = (qauid, label, refresh) => {
    modal.confirm({
      title: '이 보고서를 삭제할까요?',
      content: `'${label || '이 회차'}' 보고서를 삭제합니다. 되돌릴 수 없습니다.`,
      okText: '삭제',
      okType: 'danger',
      cancelText: '취소',
      onOk: async () => {
        try {
          await apiClient.delete(`/d2insight/schedule/turn/${qauid}/${userId}`)
          refresh?.()
        } catch (e) {
          message.error(e.response?.data?.detail || '삭제에 실패했습니다.')
        }
      },
    })
  }

  const handleDeleteReceivedScheduleShare = async (shareUid) => {
    setMenuOpenId(null)
    try {
      await apiClient.delete(`/d2insight/schedule/shares/received/${shareUid}/${userId}`)
      fetchScheduleShares()
    } catch (e) {
      message.error(e.response?.data?.detail || '삭제에 실패했습니다.')
    }
  }

  // ── 정기 보고서 등록/수정 핸들러(패널에서 호출) ───────────────
  const handlePreviewRegisterSchedule = async (settings) => {
    try {
      const { data } = await apiClient.post('/d2insight/schedule/register-preview', {
        qauid: settings.qauid,
        user_id: userId,
        project_id: user?.myprojectid ?? null,
        day_of_month: settings.day_of_month,
        hour: settings.hour,
        minute: settings.minute,
      })
      return data
    } catch (e) {
      message.error(e.response?.data?.detail || '정기 보고서 등록 확인에 실패했습니다.')
      return null
    }
  }

  // 등록은 특정 보고서(qauid) 기준이다 — 서버가 그 보고서 전용의 새 세션을 만들어 결과를
  // 쌓으므로, 원래 대화 세션은 건드리지 않는다. 등록 직후 그 qauid의 "이미 등록됨" 표시가
  // 곧바로 반영되도록 현재 보이는 메시지 목록도 같이 갱신한다.
  const handleRegisterSchedule = async (settings) => {
    try {
      await apiClient.post('/d2insight/schedule/register', {
        qauid: settings.qauid,
        user_id: userId,
        project_id: user?.myprojectid ?? null,
        day_of_month: settings.day_of_month,
        hour: settings.hour,
        minute: settings.minute,
      })
      const markTemplate = (list) => list.map((m) => (
        m.role === 'assistant' && m.qauid === settings.qauid ? { ...m, isTemplate: true } : m
      ))
      setMessages((prev) => markTemplate(prev))
      setHistoryMessages((prev) => markTemplate(prev))
      fetchHistory()
    } catch (e) {
      message.error(e.response?.data?.detail || '정기 보고서 등록에 실패했습니다.')
    }
  }

  const handlePreviewScheduleUpdate = async (settings) => {
    try {
      const { data } = await apiClient.post(`/d2insight/schedule/${settings.session_id}/update-preview`, {
        user_id: userId,
        day_of_month: settings.day_of_month,
        hour: settings.hour,
        minute: settings.minute,
      })
      return data
    } catch (e) {
      message.error(e.response?.data?.detail || '일정 변경 확인에 실패했습니다.')
      return null
    }
  }

  const handleApplyScheduleUpdate = async (settings) => {
    try {
      await apiClient.post(`/d2insight/schedule/${settings.session_id}/update`, {
        user_id: userId,
        day_of_month: settings.day_of_month,
        hour: settings.hour,
        minute: settings.minute,
      })
      loadScheduleSettings(settings.session_id)
      fetchHistory()
    } catch (e) {
      message.error(e.response?.data?.detail || '일정 변경에 실패했습니다.')
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
    .map(([d, sessions]) => [d, sessions.filter((s) => s.session_id !== sessionId && !s.is_schedule)])
    .filter(([, sessions]) => sessions.length > 0)

  const scheduleSessions = Object.values(history).flat().filter((s) => s.is_schedule)

  // 우측 옵션 패널에 보여줄 대상 — 말풍선을 클릭하면 그 보고서로 전환되고(activeReportIndex),
  // 아무것도 클릭하지 않았으면(null) 가장 최근에 생성된 보고서를 기본으로 보여준다.
  // activeReportMsgIndex는 실제로 패널에 표시 중인 assistant 메시지의 인덱스 — 말풍선 목록에서
  // 그 보고서를 하이라이트(active-report)하는 데도 같이 쓴다.
  const activeMessages = viewMode === 'history' ? historyMessages : messages
  const findLatestReportIndex = (list) => {
    for (let i = list.length - 1; i >= 0; i--) {
      if (list[i].role === 'assistant' && list[i].appliedSteps) return i
    }
    return null
  }
  const activeReportMsgIndex = (
    activeReportIndex != null && activeMessages[activeReportIndex]?.role === 'assistant'
      ? activeReportIndex
      : findLatestReportIndex(activeMessages)
  )
  const activeReportMessage = activeReportMsgIndex != null ? activeMessages[activeReportMsgIndex] : null
  const activeAppliedSteps = activeReportMessage?.appliedSteps || null

  // 말풍선 클릭 → 그 보고서(assistant 메시지)의 옵션을 패널에 표시한다.
  const selectReportForIndex = (idx, list) => {
    const m = list[idx]
    if (!m) return
    const assistantIdx = m.role === 'assistant' ? idx : (list[idx + 1]?.role === 'assistant' ? idx + 1 : idx)
    setActiveReportIndex(assistantIdx)
  }

  return (
    <div style={{ height: 'calc(100vh - 164px)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

      {/* ── 헤더 ── */}
      <div className="page-title" style={{ flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.d2insight.agent')}</div>
        </div>
      </div>

      <div className="d2insight-layout">

        {/* ── 사이드바 ── */}
        <aside className="d2insight-sidebar">
          <div className="current-session-block">
            <span className="current-session-label">{t('lbl.d2insight.current_session')}</span>
            <span className="current-session-title">{currentTitle || t('msg.d2insight.no_request')}</span>
          </div>

          <div className="sidebar-newchat">
            <button type="button" className="new-chat-btn" onClick={handleNewChat}>{t('btn.d2insight.new_chat')}</button>
          </div>

          <nav className="sidebar-nav">

            {/* 즐겨찾기 */}
            <div className="sidebar-section fav-section">
              <SectionHeader sectionKey="favorites" icon="★" label={t('ttl.d2insight.favorites')} count={favorites.length} iconActive={favorites.length > 0} />
              {openSections.favorites && (
                <ul className="session-list">
                  {favorites.length === 0
                    ? <li className="sidebar-empty">{t('msg.d2insight.no_favorites')}</li>
                    : favorites.map((f) => (
                      <li
                        key={f.qauid}
                        className={`session-item ${f.qauid === viewingFavoriteQauid ? 'viewing' : ''}`}
                        onClick={() => handleSelectFavorite(f)}
                      >
                        <span className="session-fav-star">★</span>
                        <span className="session-title">{f.question?.slice(0, 35) || t('msg.d2insight.no_content')}</span>
                        <span className="session-date-badge">{f.created_at?.slice(5, 10)}</span>
                        <button type="button" className="session-menu-btn" onClick={(e) => handleMenuClick(e, f.qauid, 'favorites')}>···</button>
                      </li>
                    ))}
                </ul>
              )}
            </div>

            {/* 대화 목록 (날짜별, 정기 보고서 세션 제외) */}
            <div className="sidebar-section">
              <SectionHeader
                sectionKey="history" icon="💬" label={t('ttl.d2insight.history')}
                count={Object.values(history).flat().filter((s) => s.session_id !== sessionId && !s.is_schedule).length}
              />
              {openSections.history && (
                filteredHistory.length === 0 ? (
                  <p className="sidebar-empty">{t('msg.d2insight.no_history')}</p>
                ) : (
                  <div className="date-group-list">
                    {filteredHistory.map(([d, sessions]) => (
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
                                  title={favoritedSessionIds.has(s.session_id) ? t('msg.d2insight.fav_exists') : ''}
                                >★</span>
                                <span className="session-title">{s.title}</span>
                                <button type="button" className="session-menu-btn" onClick={(e) => handleMenuClick(e, s.session_id)}>···</button>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    ))}
                  </div>
                )
              )}
            </div>

            {/* 정기 보고서 (제목 → 회차별 목록) */}
            <div className="sidebar-section">
              <SectionHeader sectionKey="schedules" icon="📅" label="정기 보고서" count={scheduleSessions.length} />
              {openSections.schedules && (
                scheduleSessions.length === 0 ? (
                  <p className="sidebar-empty">등록된 정기 보고서가 없습니다.</p>
                ) : (
                  <div className="date-group-list">
                    {scheduleSessions.map((s) => {
                      const turns = scheduleTurns[s.session_id]
                      return (
                        <div key={s.session_id} className="date-group">
                          <div className="schedule-title-row">
                            <button
                              type="button"
                              className={`date-toggle ${openSchedules[s.session_id] ? 'open' : ''}`}
                              onClick={() => toggleSchedule(s.session_id)}
                            >
                              <span>
                                <span
                                  className={`schedule-status-dot ${s.schedule_active ? 'active' : 'inactive'}`}
                                  title={s.schedule_active ? '진행 중' : '종료됨'}
                                />
                                {s.title}
                              </span>
                              <span className="arrow">{openSchedules[s.session_id] ? '▾' : '▸'}</span>
                            </button>
                            <button type="button" className="session-menu-btn" onClick={(e) => handleMenuClick(e, s.session_id, 'schedule')}>···</button>
                          </div>
                          {openSchedules[s.session_id] && (
                            <ul className="session-list">
                              {turns === 'loading'
                                ? <li className="sidebar-empty">불러오는 중...</li>
                                : (!turns || turns.length === 0)
                                  ? <li className="sidebar-empty">아직 생성된 보고서가 없습니다.</li>
                                  : turns.map((turn) => (
                                    <li
                                      key={turn.qauid}
                                      className={`session-item ${turn.qauid === viewingScheduleQauid ? 'viewing' : ''}`}
                                      onClick={() => handleSelectScheduleTurn(turn, s)}
                                    >
                                      <span
                                        className={`session-fav-indicator ${favoritedQaids.has(turn.qauid) ? 'fav-on' : ''}`}
                                        title={favoritedQaids.has(turn.qauid) ? '즐겨찾기됨' : ''}
                                      >★</span>
                                      <span className="session-title">
                                        {turn.target_period || turn.question?.slice(0, 20) || '(내용 없음)'}
                                      </span>
                                      <button
                                        type="button"
                                        className="session-menu-btn"
                                        onClick={(e) => {
                                          e.stopPropagation()
                                          handleDeleteScheduleTurn(turn.qauid, turn.target_period || s.title, () => loadScheduleTurns(s.session_id))
                                        }}
                                      >···</button>
                                    </li>
                                  ))
                              }
                            </ul>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )
              )}
            </div>

            <div className="sidebar-group-divider" />

            {/* 공유한 보고서 */}
            <div className="sidebar-section">
              <SectionHeader sectionKey="sent" icon="↑" label="공유한 보고서" count={sharesSent.length} />
              {openSections.sent && (
                <ul className="session-list">
                  {sharesSent.length === 0
                    ? <li className="sidebar-empty">{t('msg.d2insight.no_shares_sent')}</li>
                    : sharesSent.map((s) => (
                      <li
                        key={s.share_qauid}
                        className="session-item"
                        onClick={() => handleSelectShare(s.share_qauid, s.question?.slice(0, 20))}
                      >
                        <span className="session-title">{s.question?.slice(0, 30) || t('msg.d2insight.no_title')}</span>
                        <span className="session-date-badge">{s.created_at?.slice(5, 10)}</span>
                        <button type="button" className="session-menu-btn" onClick={(e) => handleMenuClick(e, s.share_qauid, 'sent')}>···</button>
                      </li>
                    ))}
                </ul>
              )}
            </div>

            {/* 공유받은 보고서 */}
            <div className="sidebar-section">
              <SectionHeader sectionKey="received" icon="📂" label="공유받은 보고서" count={sharesReceived.length} />
              {openSections.received && (
                <ul className="session-list">
                  {sharesReceived.length === 0
                    ? <li className="sidebar-empty">{t('msg.d2insight.no_shares_received')}</li>
                    : sharesReceived.map((s) => (
                      <li
                        key={s.share_qauid}
                        className="session-item"
                        onClick={() => handleSelectShare(s.share_qauid, s.question?.slice(0, 20))}
                      >
                        <span className="session-title">{s.question?.slice(0, 30) || t('msg.d2insight.no_title')}</span>
                        <span className="session-date-badge">{s.created_at?.slice(5, 10)}</span>
                        <button type="button" className="session-menu-btn" onClick={(e) => handleMenuClick(e, s.share_qauid, 'received')}>···</button>
                      </li>
                    ))}
                </ul>
              )}
            </div>

            <div className="sidebar-group-divider" />

            {/* 공유한 정기 보고서 */}
            <div className="sidebar-section">
              <SectionHeader sectionKey="sentSchedule" icon="📤" label="공유한 정기 보고서" count={sharesSentSchedule.length} />
              {openSections.sentSchedule && (
                sharesSentSchedule.length === 0 ? (
                  <p className="sidebar-empty">공유한 정기 보고서가 없습니다.</p>
                ) : (
                  <div className="date-group-list">
                    {sharesSentSchedule.map((s) => {
                      const turns = sentScheduleTurns[s.share_uid]
                      return (
                        <div key={s.share_uid} className="date-group">
                          <div className="schedule-title-row">
                            <button
                              type="button"
                              className={`date-toggle ${openSentSchedules[s.share_uid] ? 'open' : ''}`}
                              onClick={() => toggleSentSchedule(s.share_uid)}
                            >
                              <span>{s.title}</span>
                              <span className="arrow">{openSentSchedules[s.share_uid] ? '▾' : '▸'}</span>
                            </button>
                            <button type="button" className="session-menu-btn" onClick={(e) => handleMenuClick(e, s.share_uid, 'sentSchedule')}>···</button>
                          </div>
                          {openSentSchedules[s.share_uid] && (
                            <ul className="session-list">
                              {turns === 'loading'
                                ? <li className="sidebar-empty">불러오는 중...</li>
                                : (!turns || turns.length === 0)
                                  ? <li className="sidebar-empty">아직 생성된 보고서가 없습니다.</li>
                                  : turns.map((turn) => (
                                    <li
                                      key={turn.qauid}
                                      className={`session-item ${turn.qauid === viewingScheduleQauid ? 'viewing' : ''}`}
                                      onClick={() => handleSelectScheduleTurn(turn, s)}
                                    >
                                      <span className="session-title">
                                        {turn.target_period || turn.question?.slice(0, 20) || '(내용 없음)'}
                                      </span>
                                      <button
                                        type="button"
                                        className="session-menu-btn"
                                        onClick={(e) => {
                                          e.stopPropagation()
                                          handleDeleteScheduleTurn(turn.qauid, turn.target_period || s.title, () => loadSentScheduleTurns(s.share_uid))
                                        }}
                                      >···</button>
                                    </li>
                                  ))
                              }
                            </ul>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )
              )}
            </div>

            {/* 공유받은 정기 보고서 */}
            <div className="sidebar-section">
              <SectionHeader sectionKey="receivedSchedule" icon="📁" label="공유받은 정기 보고서" count={sharesReceivedSchedule.length} />
              {openSections.receivedSchedule && (
                sharesReceivedSchedule.length === 0 ? (
                  <p className="sidebar-empty">공유받은 정기 보고서가 없습니다.</p>
                ) : (
                  <div className="date-group-list">
                    {sharesReceivedSchedule.map((s) => {
                      const turns = sharedScheduleTurns[s.share_uid]
                      return (
                        <div key={s.share_uid} className="date-group">
                          <div className="schedule-title-row">
                            <button
                              type="button"
                              className={`date-toggle ${openSharedSchedules[s.share_uid] ? 'open' : ''}`}
                              onClick={() => toggleSharedSchedule(s.share_uid)}
                            >
                              <span>{s.title}</span>
                              <span className="arrow">{openSharedSchedules[s.share_uid] ? '▾' : '▸'}</span>
                            </button>
                            <button type="button" className="session-menu-btn" onClick={(e) => handleMenuClick(e, s.share_uid, 'receivedSchedule')}>···</button>
                          </div>
                          {openSharedSchedules[s.share_uid] && (
                            <ul className="session-list">
                              {turns === 'loading'
                                ? <li className="sidebar-empty">불러오는 중...</li>
                                : (!turns || turns.length === 0)
                                  ? <li className="sidebar-empty">아직 생성된 보고서가 없습니다.</li>
                                  : turns.map((turn) => (
                                    <li
                                      key={turn.qauid}
                                      className={`session-item ${turn.qauid === viewingScheduleQauid ? 'viewing' : ''}`}
                                      onClick={() => handleSelectSharedScheduleTurn(turn, s)}
                                    >
                                      <span className="session-title">
                                        {turn.target_period || turn.question?.slice(0, 20) || '(내용 없음)'}
                                      </span>
                                    </li>
                                  ))
                              }
                            </ul>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )
              )}
            </div>

          </nav>

          {/* ··· 드롭다운 메뉴 */}
          {menuOpenId && (
            <div className="session-dropdown" style={{ top: menuPos.top, left: menuPos.left }}>
              {menuSection === 'schedule' && !getScheduleShareUid(menuOpenId) && (
                <button
                  type="button"
                  className="session-dropdown-item"
                  onClick={(e) => { e.stopPropagation(); handleShareSchedule(menuOpenId) }}
                >공유</button>
              )}
              {menuSection === 'sentSchedule' && (
                <button
                  type="button"
                  className="session-dropdown-del"
                  onClick={(e) => { e.stopPropagation(); handleUnshareSchedule(menuOpenId) }}
                >{t('btn.delete')}</button>
              )}
              {menuSection === 'receivedSchedule' && (
                <button
                  type="button"
                  className="session-dropdown-del"
                  onClick={(e) => { e.stopPropagation(); handleDeleteReceivedScheduleShare(menuOpenId) }}
                >{t('btn.delete')}</button>
              )}
              {menuSection !== 'sentSchedule' && menuSection !== 'receivedSchedule' && (
                <button type="button" className="session-dropdown-del" onClick={(e) => handleSidebarDelete(e, menuOpenId)}>
                  {t('btn.delete')}
                </button>
              )}
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
                        title={isFav ? t('btn.d2insight.fav_remove') : t('btn.d2insight.fav_add')}
                      >★</button>
                    ) : null

                    // 이 말풍선을 클릭하면 그 보고서(appliedSteps)를 오른쪽 옵션 패널에 띄운다 —
                    // 한 대화창에서 여러 보고서를 작성했을 때 어떤 보고서가 패널에 보이는지
                    // 구분할 수 있도록 현재 선택된 보고서의 assistant 말풍선을 강조 표시한다.
                    const isActiveReport = msg.role === 'assistant' && index === activeReportMsgIndex
                    return (
                      <div
                        key={index}
                        className={`msg-row turn-clickable${isActiveReport ? ' active-report' : ''}`}
                        onClick={() => selectReportForIndex(index, messages)}
                      >
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
                      <span className="loading-text">{t('msg.d2insight.generating')}</span>
                    </div>
                  )}
                  <div ref={bottomRef} />
                </div>

                <div className="input-container">
                  <div className="examples">
                    <strong>{t('lbl.d2insight.example_request')}</strong>
                    {EXAMPLE_QUESTIONS.map((item, index) => (
                      <span key={index} className="example-btn" onClick={() => setInputValue(item.question)}>{item.label}</span>
                    ))}
                  </div>
                  <div className="input-wrapper">
                    <textarea
                      placeholder={t('inf.d2insight.input_placeholder')}
                      value={inputValue}
                      onChange={(e) => setInputValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault()
                          sendMessage()
                        }
                      }}
                    />
                    <button type="button" onClick={() => sendMessage()} disabled={isLoading}>{t('btn.send')}</button>
                    <button
                      type="button"
                      className="toggle-query-btn"
                      title={t('inf.d2insight.add_dataset_tooltip')}
                      onClick={() => setDatasetModalOpen(true)}
                    >
                      <PaperClipOutlined style={{ fontSize: 18 }} />
                      <span>{t('btn.d2insight.add_data')}</span>
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <div className="history-view">
                <div className="history-bar">
                  <span>{t('msg.d2insight.continue_hint')}</span>
                  <button
                    type="button"
                    className="history-back-btn"
                    onClick={() => {
                      setViewingSessionId(null)
                      setViewingFavoriteQauid(null)
                      setViewingScheduleQauid(null)
                      setViewingScheduleSessionId(null)
                      setScheduleSettings(null)
                      setActiveReportIndex(null)
                      setViewMode('chat')
                    }}
                  >← {t('btn.d2insight.back_to_current')}</button>
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
                        title={isFav ? t('btn.d2insight.fav_remove') : t('btn.d2insight.fav_add')}
                      >★</button>
                    ) : null

                    const isActiveReport = msg.role === 'assistant' && index === activeReportMsgIndex
                    return (
                      <div
                        key={index}
                        className={`history-msg-wrapper msg-row${viewingSessionId ? ' turn-clickable' : ''}${isActiveReport ? ' active-report' : ''}`}
                        onClick={viewingSessionId ? () => selectReportForIndex(index, historyMessages) : undefined}
                      >
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
                              >{t('btn.d2insight.continue')}</button>
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

        {/* ── 우측 옵션 패널 (적용된 모듈/툴/파라미터 + 패널 내 정기 보고서 등록/수정) ── */}
        <ReportOptionsPanel
          appliedSteps={activeAppliedSteps}
          reportQauid={activeReportMessage?.qauid || null}
          isTemplate={!!activeReportMessage?.isTemplate}
          scheduleSettings={scheduleSettings}
          onPreviewRegisterSchedule={handlePreviewRegisterSchedule}
          onRegisterSchedule={handleRegisterSchedule}
          onPreviewScheduleUpdate={handlePreviewScheduleUpdate}
          onApplyScheduleUpdate={handleApplyScheduleUpdate}
          preview={previewData}
          previewGenerating={isLoading}
          onConfirmPreview={handleConfirmPreview}
          onCancelPreview={() => { setPreviewData(null); setPreviewOriginalMessage('') }}
          onReorderPreviewSteps={(newSteps) =>
            setPreviewData((prev) => (prev ? { ...prev, applied_steps: newSteps } : prev))
          }
          onValidateSteps={handleValidateSteps}
        />
      </div>

      {/* 공유 모달 */}
      {shareTarget && (
        <FolderPickerModal
          qauid={shareTarget.qauid}
          userId={userId}
          onClose={() => setShareTarget(null)}
          onShared={() => fetchShares()}
          message={message}
        />
      )}

      {/* 데이터셋 추가(업로드/API) 모달 */}
      <DatasetUploadModal
        open={datasetModalOpen}
        sessionId={sessionId}
        apiBase="/d2insight"
        onClose={() => setDatasetModalOpen(false)}
        onSuccess={handleDatasetUploaded}
      />
    </div>
  )
}

// Base64 data URI 이미지를 플레이스홀더로 교체 후 marked 파싱, 복원
function parseMarkdownWithImages(text) {
  const images = []
  const placeholder = text.replace(
    /!\[([^\]]*)\]\((data:image\/[^)]*)\)/g,
    (_, alt, src) => {
      const id = images.length
      images.push({ alt, src })
      return `![${alt}](CHART_IMG_${id}_PLACEHOLDER)`
    }
  )
  // marked는 GFM 취소선을 ~~두 개~~뿐 아니라 ~한 개~도 델리미터로 인정한다. 보고서 본문이
  // "2만~6만 달러"처럼 숫자 범위에 물결표 하나를 "부터"라는 뜻으로 쓰면, 문장 뒤쪽 다른
  // 범위 표기("3만~4만")의 물결표와 짝지어져 그 사이 전체가 취소선으로 렌더링되는 문제가
  // 있었다. 진짜 취소선(~~쌍~~)은 그대로 두고, 홀로 쓰인 ~만 이스케이프해 취소선으로
  // 해석되지 않게 한다.
  const tildesEscaped = placeholder.replace(/~~|~/g, (m) => (m === '~~' ? '~~' : '\\~'))
  let html = marked.parse(tildesEscaped)
  // 플레이스홀더 토큰(영숫자만)만 찾아 src로 바꾼다 — alt에 특수문자가 있으면 marked가
  // 이스케이프해 <img> 태그 전체를 문자 그대로 재구성한 문자열과 안 맞을 수 있다.
  images.forEach(({ src }, id) => {
    html = html.replace(`CHART_IMG_${id}_PLACEHOLDER`, src)
  })
  html = html.replace(/<img /g, '<img style="max-width:100%;height:auto;display:block;margin:12px 0;" ')
  return html
}

// ─────────────────────────────────────────────────────────────────
// 우측 옵션 패널 — 보고서가 어떤 모듈/툴/파라미터로 만들어졌는지 표시(읽기 전용)
// ─────────────────────────────────────────────────────────────────
function ReportOptionsPanel({
  appliedSteps, reportQauid, isTemplate,
  scheduleSettings,
  onPreviewRegisterSchedule, onRegisterSchedule,
  onPreviewScheduleUpdate, onApplyScheduleUpdate,
  preview, previewGenerating, onConfirmPreview, onCancelPreview, onReorderPreviewSteps,
  onValidateSteps,
}) {
  useLangStore((s) => s.translations)
  const { modal } = App.useApp()
  const [showJson, setShowJson] = useState(false)
  const [showPreviewJson, setShowPreviewJson] = useState(false)
  const [dragIndex, setDragIndex] = useState(null)

  // preview 모드의 JSON 편집 buffer — textarea에서 사용자가 편집하는 중간 문자열.
  // "JSON 저장" 눌러야 부모 previewData.applied_steps에 반영된다 (그 전까지 카드는 안 바뀜).
  // 편집 결과가 유효하면 아래 카드도 자동 리렌더되고, 그 순서·모듈 그대로 "이대로 작성"이
  // 실제 /chat 실행 옵션으로 넘어가 보고서에 반영된다.
  const [jsonText, setJsonText] = useState('')
  const [jsonError, setJsonError] = useState('')
  const [jsonSaveOk, setJsonSaveOk] = useState(false)

  // preview가 새로 세팅되거나 부모에서 갱신될 때(드래그 재정렬 포함) buffer도 동기화한다.
  // JSON.stringify를 매번 새로 만들어 사용자가 편집했던 buffer는 리셋된다 — 이 편이 헷갈리지 않다.
  useEffect(() => {
    if (!preview) { setJsonText(''); setJsonError(''); setJsonSaveOk(false); return }
    setJsonText(JSON.stringify(preview.applied_steps || [], null, 2))
    setJsonError('')
    setJsonSaveOk(false)
  }, [preview])

  const applyJsonEdit = async () => {
    let parsed
    try {
      parsed = JSON.parse(jsonText)
      if (!Array.isArray(parsed)) throw new Error('applied_steps는 배열이어야 해요')
    } catch (e) {
      setJsonError('JSON 형식 오류: ' + e.message)
      setJsonSaveOk(false)
      return
    }
    setJsonError('')
    let resolved = parsed
    try {
      resolved = (await onValidateSteps?.(parsed)) || parsed
    } catch {
      // 재검증 실패해도 로컬 파싱 결과로 반영한다.
    }
    onReorderPreviewSteps?.(resolved)
    setJsonSaveOk(true)
    setShowPreviewJson(false)
    setTimeout(() => setJsonSaveOk(false), 3000)
  }

  // preview 스텝 드래그 순서 재정렬 — 사용자가 스텝을 위/아래로 드래그하면
  // 그 순서가 부모의 previewData.applied_steps에 반영되고, "이대로 작성" 시
  // 그대로 백엔드로 전달돼 보고서 스텝 순서가 바뀐다.
  // 참고: pr_module_insight_202608061005/frontend/src/components/OptionsPanel.jsx의
  //       handleDragStart/handleDragOver/handleDrop 패턴만 발췌.
  // 잠금 규칙은 백엔드가 이미 각 step에 locked 플래그로 부착해 내려준다
  // (d2insight/chat/router.py::preview_report). 프론트는 그걸 읽어 이동·드롭을 막기만 한다.
  // 잠금 판정을 프론트가 따로 하면 규칙이 두 곳으로 갈라진다 — 단독앱 원칙과 같다.
  const handleStepDragStart = (idx) => (e) => {
    const steps = preview?.applied_steps || []
    if (steps[idx]?.locked) { e.preventDefault(); return }
    setDragIndex(idx)
    try { e.dataTransfer.effectAllowed = 'move' } catch { /* jsdom 등 */ }
  }
  const handleStepDragOver = (idx) => (e) => {
    const steps = preview?.applied_steps || []
    if (steps[idx]?.locked) return
    e.preventDefault()
    try { e.dataTransfer.dropEffect = 'move' } catch { /* jsdom 등 */ }
  }
  const handleStepDrop = (idx) => (e) => {
    e.preventDefault()
    const steps = [...(preview?.applied_steps || [])]
    if (dragIndex === null || dragIndex === idx || steps[idx]?.locked) { setDragIndex(null); return }
    const [moved] = steps.splice(dragIndex, 1)
    steps.splice(idx, 0, moved)
    onReorderPreviewSteps?.(steps)
    setDragIndex(null)
  }
  const handleStepDragEnd = () => setDragIndex(null)

  // 카탈로그 (시나리오·스텝·모듈·툴) — 옵션 패널이 마운트될 때 1회 로드.
  // 표시용 데이터일 뿐이므로 실패해도 조용히 넘긴다(카탈로그 없이도 기존 옵션 패널은 동작).
  const [catalog, setCatalog] = useState(null)
  const [showCatalog, setShowCatalog] = useState(false)

  useEffect(() => {
    let cancelled = false
    apiClient.get('/d2insight/catalog')
      .then((r) => { if (!cancelled) setCatalog(r.data) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  const [showScheduleForm, setShowScheduleForm] = useState(false)
  const [scheduleDay, setScheduleDay] = useState(1)
  const [scheduleHour, setScheduleHour] = useState(9)
  const [registering, setRegistering] = useState(false)

  const [showEditSchedule, setShowEditSchedule] = useState(false)
  const [editDay, setEditDay] = useState(1)
  const [editHour, setEditHour] = useState(9)
  const [updating, setUpdating] = useState(false)

  useEffect(() => {
    if (scheduleSettings) {
      setEditDay(scheduleSettings.day_of_month || 1)
      setEditHour(scheduleSettings.hour ?? 9)
    }
    setShowScheduleForm(false)
    setShowEditSchedule(false)
  }, [scheduleSettings, reportQauid])

  const handleRequestSaveSchedule = async () => {
    if (!reportQauid) return
    setRegistering(true)
    try {
      const settings = {
        qauid: reportQauid,
        day_of_month: scheduleDay,
        hour: scheduleHour,
        minute: 0,
      }
      const res = await onPreviewRegisterSchedule?.(settings)
      if (!res) return
      modal.confirm({
        title: '정기 보고서 등록',
        content: res.message,
        okText: '등록',
        cancelText: '취소',
        onOk: async () => {
          await onRegisterSchedule?.(settings)
          setShowScheduleForm(false)
        },
      })
    } finally {
      setRegistering(false)
    }
  }

  const handleRequestScheduleUpdate = async () => {
    if (!scheduleSettings?.session_id) return
    setUpdating(true)
    try {
      const settings = { session_id: scheduleSettings.session_id, day_of_month: editDay, hour: editHour, minute: 0 }
      const res = await onPreviewScheduleUpdate?.(settings)
      if (!res) return
      modal.confirm({
        title: '정기 보고서 일정 변경',
        content: res.message,
        okText: '변경',
        cancelText: '취소',
        onOk: async () => {
          await onApplyScheduleUpdate?.(settings)
          setShowEditSchedule(false)
        },
      })
    } finally {
      setUpdating(false)
    }
  }

  return (
    <aside className="options-panel">
      <div className="options-panel-header">
        <span className="options-panel-title">
          {preview ? '작성 전 확인 (preview)' : '적용된 옵션'}
        </span>
      </div>
      <div className="options-panel-body">
        {/* preview 모드 — 사용자 요청에 대해 시나리오 매칭 결과 표시 + "이대로 작성" 버튼.
            단독앱 pr_module_insight_202608061005의 OptionsPanel.jsx 방식. */}
        {preview && (
          <div className="opt-preview" style={{ marginBottom: 16, padding: 12, background: '#fff8e1', border: '1px solid #ffe082', borderRadius: 6 }}>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>📊 {preview.scenario}</div>
            {preview.report_title && (
              <div style={{ color: '#666', fontSize: 12, marginBottom: 8 }}>{preview.report_title}</div>
            )}

            {/* JSON 원문 보기 토글 — 스텝 리스트 위에 배치.
                단독앱 pr_module_insight_202608061005/frontend/src/components/OptionsPanel.jsx의
                341~357행 배치 순서와 동일. */}
            <button
              type="button"
              className="opt-json-toggle"
              onClick={() => setShowPreviewJson((v) => !v)}
              style={{ marginBottom: 6 }}
            >
              {showPreviewJson ? 'JSON 접기' : 'JSON 원문 보기'}
            </button>
            {showPreviewJson && (
              <div className="opt-json-box" style={{ marginBottom: 10 }}>
                <textarea
                  value={jsonText}
                  onChange={(e) => setJsonText(e.target.value)}
                  rows={14}
                  style={{ width: '100%', fontFamily: 'monospace', fontSize: 12 }}
                />
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
                  <button
                    type="button"
                    onClick={applyJsonEdit}
                    style={{ padding: '6px 12px', background: '#1976d2', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer', fontWeight: 600 }}
                  >
                    JSON 저장
                  </button>
                  {jsonSaveOk && (
                    <span style={{ color: '#2e7d32', fontSize: 12 }}>✓ 스텝에 반영됐어요.</span>
                  )}
                </div>
                {jsonError && (
                  <div style={{ marginTop: 6, color: '#c62828', fontSize: 12 }}>{jsonError}</div>
                )}
              </div>
            )}

            <div style={{ color: '#888', fontSize: 11, margin: '6px 0' }}>
              스텝을 드래그해 순서를 조정할 수 있어요. 🔒 표시는 순서 고정 스텝이에요.
            </div>
            <div style={{ margin: '4px 0 12px 0', fontSize: 13 }}>
              {(preview.applied_steps || []).map((step, i) => {
                const isLocked = !!step.locked
                const isDisabled = step.enabled === false
                return (
                  <div
                    key={i}
                    draggable={!isLocked}
                    onDragStart={handleStepDragStart(i)}
                    onDragOver={handleStepDragOver(i)}
                    onDrop={handleStepDrop(i)}
                    onDragEnd={handleStepDragEnd}
                    style={{
                      marginBottom: 6,
                      padding: '6px 8px',
                      background: isDisabled ? '#f0f0f0' : (isLocked ? '#f5f5f5' : (dragIndex === i ? '#fff3cd' : '#fff')),
                      border: `1px solid ${isDisabled ? '#ccc' : (isLocked ? '#ddd' : '#e0d38a')}`,
                      borderRadius: 4,
                      cursor: isLocked ? 'default' : 'grab',
                      opacity: isDisabled ? 0.6 : (dragIndex === i ? 0.6 : 1),
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span
                        style={{ color: isLocked ? '#888' : '#bbb', fontSize: 13, width: 16, display: 'inline-block' }}
                        title={isLocked ? '순서 고정' : '드래그해 순서 변경'}
                      >
                        {isLocked ? '🔒' : '⋮⋮'}
                      </span>
                      <strong style={{ color: isDisabled ? '#999' : (isLocked ? '#555' : 'inherit') }}>
                        {i + 1}. {step.title}
                      </strong>
                      {isDisabled && (
                        <span style={{ color: '#c62828', fontSize: 11, border: '1px solid #e0a0a0', borderRadius: 3, padding: '0 4px' }}>
                          작성 불가
                        </span>
                      )}
                    </div>
                    {/* 단독앱 방식: module_id는 감추고 purpose만 조용히 보여준다.
                        도구·파라미터는 JSON 원문에서 확인. */}
                    {(step.modules || []).length > 0 && (
                      <div style={{ marginLeft: 22, marginTop: 3, color: '#777', fontSize: 12 }}>
                        {step.modules.map((m) => m.purpose || m.module_id).join(' · ')}
                      </div>
                    )}
                    {isDisabled && step.disabled_reason && (
                      <div style={{ marginLeft: 22, marginTop: 3, color: '#c62828', fontSize: 11 }}>
                        {step.disabled_reason}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                onClick={onConfirmPreview}
                disabled={previewGenerating}
                style={{
                  padding: '8px 14px', background: '#1976d2', color: 'white', border: 'none',
                  borderRadius: 4, cursor: previewGenerating ? 'default' : 'pointer', fontWeight: 600,
                  opacity: previewGenerating ? 0.6 : 1,
                }}
              >
                {previewGenerating ? '작성 중...' : '이대로 작성'}
              </button>
              <button
                type="button"
                onClick={onCancelPreview}
                disabled={previewGenerating}
                style={{
                  padding: '8px 14px', background: '#eee', border: '1px solid #ccc', borderRadius: 4,
                  cursor: previewGenerating ? 'default' : 'pointer', opacity: previewGenerating ? 0.6 : 1,
                }}
              >
                취소
              </button>
            </div>
          </div>
        )}

        {/* preview가 떠 있는 동안(= 새 보고서 확인/생성 중)에는 이전 보고서의 "적용된 옵션"을
            같이 보여주지 않는다 — 그렇지 않으면 두 번째 보고서를 만들 때 방금 뜬 preview 카드
            아래에 직전 보고서의 스텝 카드가 나란히 남아 스텝이 두 벌 보이는 것처럼 보인다. */}
        {!preview && (!appliedSteps || appliedSteps.length === 0 ? (
          <p className="options-panel-empty">이 말풍선에는 적용된 보고서 옵션이 없습니다.</p>
        ) : (
          <>
            {reportQauid && !scheduleSettings && isTemplate && (
              <div className="opt-schedule opt-schedule-done">
                📅 이미 정기 보고서로 등록된 보고서입니다.
              </div>
            )}

            {reportQauid && !scheduleSettings && !isTemplate && (
              <div className="opt-schedule">
                <button type="button" className="opt-schedule-toggle" onClick={() => setShowScheduleForm((v) => !v)}>
                  📅 {showScheduleForm ? '정기 보고서 등록 취소' : '정기 보고서로 저장'}
                </button>
                {showScheduleForm && (
                  <div className="opt-schedule-form">
                    <span>매달</span>
                    <select value={scheduleDay} onChange={(e) => setScheduleDay(Number(e.target.value))}>
                      {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
                        <option key={d} value={d}>{d}일</option>
                      ))}
                    </select>
                    <select value={scheduleHour} onChange={(e) => setScheduleHour(Number(e.target.value))}>
                      {Array.from({ length: 24 }, (_, i) => i).map((h) => (
                        <option key={h} value={h}>{h}시</option>
                      ))}
                    </select>
                    <button type="button" className="opt-schedule-submit" onClick={handleRequestSaveSchedule} disabled={registering}>
                      {registering ? '확인 중...' : '등록 요청'}
                    </button>
                  </div>
                )}
              </div>
            )}

            {scheduleSettings && (
              <div className="opt-schedule">
                <div className="opt-schedule-current">
                  정기 보고서 작성 일시: 매달 {scheduleSettings.day_of_month}일 {scheduleSettings.hour}시
                </div>
                <button type="button" className="opt-schedule-toggle" onClick={() => setShowEditSchedule((v) => !v)}>
                  {showEditSchedule ? '수정 취소' : '수정'}
                </button>
                {showEditSchedule && (
                  <div className="opt-schedule-form">
                    <span>매달</span>
                    <select value={editDay} onChange={(e) => setEditDay(Number(e.target.value))}>
                      {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
                        <option key={d} value={d}>{d}일</option>
                      ))}
                    </select>
                    <select value={editHour} onChange={(e) => setEditHour(Number(e.target.value))}>
                      {Array.from({ length: 24 }, (_, i) => i).map((h) => (
                        <option key={h} value={h}>{h}시</option>
                      ))}
                    </select>
                    <button type="button" className="opt-schedule-submit" onClick={handleRequestScheduleUpdate} disabled={updating}>
                      {updating ? '확인 중...' : '변경'}
                    </button>
                  </div>
                )}
              </div>
            )}

            <button type="button" className="opt-json-toggle" onClick={() => setShowJson((v) => !v)}>
              {showJson ? 'JSON 접기' : 'JSON 원문 보기'}
            </button>
            {showJson && (
              <div className="opt-json-box">
                <textarea value={JSON.stringify(appliedSteps, null, 2)} readOnly rows={10} />
              </div>
            )}

            {/* 스텝 카드 — "이대로 작성"으로 확정한 보고서는 preview 때 봤던 것과 같은 형태
                (제목 + 모듈 purpose)로 그대로 보여준다(pipeline_runner.py가 scenario_options의
                applied_steps를 그대로 되돌려주므로 여기 step.title/step.modules가 채워져 있다).
                옛날에 저장된 보고서(자유 대화형, scenario 매칭 없이 생성됨)는 실행 트레이스
                형태(step.step/step.tools, 2026-08-20 이전 저장분은 구 키 step.section)라
                모듈 purpose가 없다 — 제목만 보여주고 실행 중 호출한 도구·파라미터 같은 상세
                내용은 노출하지 않는다(JSON 원문 보기로만 확인). step.section은 리네임 전에
                저장된 이력과의 하위호환을 위해 남겨둔 폴백이다. */}
            <div className="opt-steps">
              {appliedSteps.map((step, idx) => {
                const isDisabled = step.enabled === false
                return (
                  <div key={idx} className="opt-step" style={isDisabled ? { opacity: 0.6 } : undefined}>
                    <div className="opt-step-header">
                      <span className="opt-step-title" style={isDisabled ? { color: '#999' } : undefined}>
                        {idx + 1}. {step.title || step.step || step.section}
                      </span>
                      {isDisabled && (
                        <span style={{ color: '#c62828', fontSize: 11, marginLeft: 6, border: '1px solid #e0a0a0', borderRadius: 3, padding: '0 4px' }}>
                          작성 안 됨
                        </span>
                      )}
                    </div>
                    {(step.modules || []).length > 0 && (
                      <div className="opt-module">
                        <span className="opt-module-name" style={{ fontWeight: 'normal', color: '#666' }}>
                          {step.modules.map((m) => m.purpose || m.module_id).join(' · ')}
                        </span>
                      </div>
                    )}
                    {isDisabled && step.disabled_reason && (
                      <div style={{ color: '#c62828', fontSize: 11, marginTop: 2 }}>{step.disabled_reason}</div>
                    )}
                  </div>
                )
              })}
            </div>
          </>
        ))}

        {/* 카탈로그 참조 — appliedSteps 유무와 무관하게 항상 표시 (시연용 참조 브라우저). */}
        {catalog && (
          <div className="opt-catalog" style={{ marginTop: 16, borderTop: '1px solid #eee', paddingTop: 12 }}>
            <button type="button" className="opt-json-toggle" onClick={() => setShowCatalog((v) => !v)}>
              🗂 {showCatalog
                ? '카탈로그 접기'
                : `카탈로그 (시나리오 ${Object.keys(catalog.scenarios).length}·스텝 ${Object.keys(catalog.steps).length}·모듈 ${Object.keys(catalog.modules).length}·툴 ${Object.keys(catalog.tools).length})`}
            </button>
            {showCatalog && (
              <div style={{ marginTop: 8, fontSize: 12, maxHeight: 400, overflowY: 'auto' }}>
                {Object.entries(catalog.scenarios).map(([scName, scDef]) => (
                  <details key={scName} style={{ marginBottom: 6 }}>
                    <summary style={{ cursor: 'pointer', fontWeight: 600, padding: '4px 0' }}>
                      📊 {scName}
                    </summary>
                    <ol style={{ margin: '4px 0 8px 20px', padding: 0 }}>
                      {(scDef.steps || []).map((s, i) => {
                        const stepDef = catalog.steps[s.step_id]
                        return (
                          <li key={i} style={{ marginBottom: 4 }}>
                            <strong>{stepDef?.title || s.step_id}</strong>
                            <ul style={{ margin: '2px 0 0 16px', color: '#666', listStyle: 'circle' }}>
                              {(stepDef?.default_modules || []).map((m, j) => (
                                <li key={j}>
                                  <code>{m.module_id}</code>
                                  {catalog.modules[m.module_id]?.purpose && (
                                    <span> — {catalog.modules[m.module_id].purpose}</span>
                                  )}
                                </li>
                              ))}
                            </ul>
                          </li>
                        )
                      })}
                    </ol>
                  </details>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  )
}

// ─────────────────────────────────────────────────────────────────
// 메시지 말풍선
// ─────────────────────────────────────────────────────────────────
function MessageBubble({ role, content, fileurl, reportPath, starButton, qauid, onShare }) {
  useLangStore((s) => s.translations)
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
    : (reportPath || t('lbl.d2insight.default_report_name'))

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
                  {previewLoading ? t('msg.d2insight.preview_loading') : previewExpanded ? t('btn.d2insight.collapse') : t('btn.d2insight.preview')}
                </button>
                <button type="button" className="report-btn download" onClick={handleDownload}>{t('btn.d2insight.download')}</button>
                {qauid && onShare && (
                  <button type="button" className="report-btn share-btn" onClick={() => onShare(qauid)}>{t('btn.d2insight.share')}</button>
                )}
              </div>
            </div>
            {previewExpanded && previewContent && (
              previewContent.startsWith('__pdf__:')
                ? <iframe src={previewContent.slice(8)} style={{ width: '100%', height: 600, border: 'none' }} title={t('ttl.d2insight.report_preview')} />
                : <div
                    className="report-preview-html"
                    dangerouslySetInnerHTML={{ __html: parseMarkdownWithImages(previewContent) }}
                  />
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
// 공유 모달 — 폴더 선택 후 tenant 내 공유
// ─────────────────────────────────────────────────────────────────
function FolderPickerModal({ qauid, userId, onClose, onShared, message }) {
  useLangStore((s) => s.translations)
  const [folders, setFolders] = useState([])
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)
  const [sharing, setSharing] = useState(false)

  useEffect(() => {
    if (!userId) return
    apiClient.get(`/d2insight/folders/${userId}`)
      .then(r => setFolders(Array.isArray(r.data) ? r.data : []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [userId])

  const handleShare = async () => {
    if (!selected) return
    setSharing(true)
    try {
      await apiClient.post('/d2insight/share', { user_id: userId, qauid, folder_uid: selected })
      onShared?.()
      onClose()
    } catch (e) {
      message.error(e.response?.data?.detail || t('msg.d2insight.share_error'))
      setSharing(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box folder-modal-box" onClick={(e) => e.stopPropagation()}>
        <h3 className="modal-title">{t('ttl.d2insight.select_share_folder')}</h3>
        {loading ? (
          <p className="modal-empty">{t('msg.d2insight.loading_folders')}</p>
        ) : folders.length === 0 ? (
          <p className="modal-empty">{t('msg.d2insight.no_folders')}</p>
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
          <button type="button" className="modal-btn cancel" onClick={onClose}>{t('btn.cancel')}</button>
          <button
            type="button"
            className="modal-btn confirm"
            onClick={handleShare}
            disabled={!selected || sharing}
          >
            {sharing ? t('msg.d2insight.sharing') : t('btn.d2insight.share')}
          </button>
        </div>
      </div>
    </div>
  )
}

