import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import { CSS_COLORS, CONTINUOUS_COLORMAPS, CATEGORICAL_COLORMAPS } from '@/utils/colorData'

const publicClient = axios.create({ baseURL: '/api' })

const DISPLAY_TYPE_NAMES = {
  bar: '막대그래프', line: '선그래프', pie: '원형그래프',
  scatter: '산점도', boxplot: '박스플롯', histogram: '히스토그램',
  dual_axis: '이중축', heatmap: '히트맵', subplot: '서브플롯',
  simple_question: '단순 질의', summary: '요약', report: '보고서',
  predict: '예측', table: '테이블',
}

function getDisplayName(p) {
  const typeName = p.displaytype ? DISPLAY_TYPE_NAMES[p.displaytype] : ''
  return typeName ? `${typeName} - ${p.promptnm}` : p.promptnm
}

export default function ExperiencePage() {
  const [allPrompts,        setAllPrompts]        = useState([])
  const [objectType,        setObjectType]        = useState('CA')
  const [selectedPromptuid, setSelectedPromptuid] = useState('')
  const [promptDesc,        setPromptDesc]        = useState('')
  const [prompt,            setPrompt]            = useState('')
  const [selectedDatauid,   setSelectedDatauid]   = useState('')
  const [columns,           setColumns]           = useState([])
  const [previewResult,     setPreviewResult]     = useState(null)
  const [previewLoading,    setPreviewLoading]    = useState(false)
  const [loading,           setLoading]           = useState(true)
  const [showColors,        setShowColors]        = useState(false)
  const [showColormap,      setShowColormap]      = useState(false)

  const promptRef = useRef(null)
  const cursorPos = useRef(0)

  useEffect(() => {
    publicClient.get('/llm/experience/prompts')
      .then(r => {
        const prompts = r.data.prompts || []
        setAllPrompts(prompts)
        // 첫 번째 CA 프롬프트 자동 선택
        const firstCa = prompts.find(p => p.objecttypecd === 'CA')
        if (firstCa) {
          setSelectedPromptuid(firstCa.promptuid)
          setPromptDesc(firstCa.desc || '')
          setPrompt(firstCa.prompt || '')
          setSelectedDatauid(firstCa.datauid ? String(firstCa.datauid) : '')
        }
      })
      .finally(() => setLoading(false))
  }, [])

  // 데이터 선택 변경 → 열이름 로드
  useEffect(() => {
    if (!selectedDatauid) { setColumns([]); return }
    publicClient.get('/llm/experience/columns', { params: { datauid: selectedDatauid } })
      .then(r => setColumns(r.data.columns || []))
      .catch(() => setColumns([]))
  }, [selectedDatauid])

  const filteredPrompts = allPrompts.filter(p => p.objecttypecd === objectType)

  const trackCursor = () => {
    if (promptRef.current) cursorPos.current = promptRef.current.selectionStart
  }

  const insertAtCursor = (text) => {
    const ta = promptRef.current
    if (!ta) return
    const pos = cursorPos.current
    const newVal = prompt.substring(0, pos) + text + prompt.substring(pos)
    setPrompt(newVal)
    const newPos = pos + text.length
    cursorPos.current = newPos
    setTimeout(() => {
      ta.setSelectionRange(newPos, newPos)
      ta.focus()
    }, 0)
  }

  const handleObjectTypeChange = (val) => {
    setObjectType(val)
    setSelectedPromptuid('')
    setPromptDesc('')
    setPrompt('')
    setSelectedDatauid('')
    setColumns([])
    setPreviewResult(null)
  }

  const handlePromptSelect = (promptuid) => {
    if (!promptuid) {
      setSelectedPromptuid('')
      setPromptDesc('')
      setPrompt('')
      setSelectedDatauid('')
      setColumns([])
      setPreviewResult(null)
      return
    }
    const p = allPrompts.find(x => String(x.promptuid) === String(promptuid))
    if (!p) return
    setSelectedPromptuid(p.promptuid)
    setPromptDesc(p.desc || '')
    setPrompt(p.prompt || '')
    setSelectedDatauid(p.datauid ? String(p.datauid) : '')
    setPreviewResult(null)
  }

  const handlePreview = async () => {
    if (!prompt.trim()) { alert('프롬프트를 입력해주세요.'); return }
    if (!selectedDatauid) { alert('샘플 프롬프트를 먼저 선택해주세요.'); return }
    setPreviewLoading(true)
    setPreviewResult(null)
    try {
      const res = await publicClient.post('/llm/experience/preview', {
        prompt,
        objecttypecd: objectType,
        datauid:      selectedDatauid,
        displaytype:  allPrompts.find(p => String(p.promptuid) === String(selectedPromptuid))?.displaytype || null,
      })
      setPreviewResult(res.data)
    } catch (e) {
      setPreviewResult({
        message_type: 'error',
        message: e?.response?.data?.detail || '미리보기 오류가 발생했습니다.',
      })
    } finally {
      setPreviewLoading(false)
    }
  }

  return (
    <div style={{ overflowY: 'auto' }}>

      <div className="page-title">
        <div className="filter-item">
          <div className="gradient-bar" />
          AI 체험하기
        </div>
      </div>

      {/* 높이 제한 컨테이너 */}
      <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 240px - 20px)', boxSizing: 'border-box', gap: 10, overflow: 'hidden' }}>

        {/* 상단 필터: 2개 드롭다운 */}
        <div style={{ display: 'flex', gap: 20, flexShrink: 0 }}>

          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center' }}>
              <label style={{ width: 120, flexShrink: 0 }}><strong>개체 유형 :</strong></label>
              <select
                style={{ flex: 1, marginRight: 20 }}
                value={objectType}
                onChange={e => handleObjectTypeChange(e.target.value)}
              >
                <option value="CA">차트 (Chart)</option>
                <option value="SA">문장 (Sentence)</option>
                <option value="TA">테이블 (Table)</option>
              </select>
            </div>
          </div>

          <div style={{ flex: 2 }}>
            <div style={{ display: 'flex', alignItems: 'center' }}>
              <label style={{ width: 180, flexShrink: 0 }}><strong>샘플 프롬프트 선택 :</strong></label>
              <select
                style={{ flex: 1, marginRight: 20 }}
                value={selectedPromptuid}
                onChange={e => handlePromptSelect(e.target.value)}
                disabled={loading}
              >
                <option value="">--- 선택 ---</option>
                {filteredPrompts.map(p => (
                  <option key={p.promptuid} value={p.promptuid}>
                    {getDisplayName(p)}
                  </option>
                ))}
              </select>
            </div>
          </div>

        </div>

        {/* 열이름 + 작성방법 */}
        <div style={{ marginTop: 10, marginBottom: 10, display: 'flex', flexDirection: 'column', flexWrap: 'wrap', flexShrink: 0 }}>
          <div style={{ color: '#333' }}>
            <strong>열이름&nbsp;&nbsp;</strong>
            {columns.map((col, idx) => (
              <span
                key={col}
                onClick={() => insertAtCursor(col)}
                style={{
                  cursor: 'pointer',
                  padding: '4px 4px',
                  marginRight: 4,
                  display: 'inline-block',
                  marginBottom: 4,
                  marginLeft: idx === 0 ? 20 : 0,
                }}
                onMouseEnter={e => {
                  e.target.style.textDecoration = 'underline'
                  e.target.style.textDecorationColor = 'silver'
                  e.target.style.color = 'black'
                  e.target.style.fontWeight = 'bold'
                }}
                onMouseLeave={e => {
                  e.target.style.textDecoration = 'none'
                  e.target.style.color = 'inherit'
                  e.target.style.fontWeight = 'normal'
                }}
              >
                {col}
              </span>
            ))}
          </div>
          <div style={{ marginTop: 2, color: '#333' }}>
            <strong>작성방법&nbsp;&nbsp;</strong>&nbsp;&nbsp;
            <span style={{ color: 'darkblue' }}>
              프롬프트를 수정하고 "미리보기"로 실행하면 결과를 확인할 수 있습니다. 프롬프트는 설명과 열 이름을 참조하여 수정하십시요.
            </span>
          </div>
        </div>

        {/* 3분할 본문 */}
        <div style={{ flex: 8, display: 'flex', flexDirection: 'row', gap: 20, minHeight: 0 }}>

          {/* 프롬프트 설명 + 색상/컬러맵 */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <h4 style={{ marginBottom: 10, fontWeight: 'bold', flexShrink: 0 }}>프롬프트 설명</h4>
            <textarea
              style={{ flex: 1, minHeight: 0, width: '100%', padding: 8, fontSize: '1rem', boxSizing: 'border-box', resize: 'none', border: '1px solid #ccc', borderRadius: 4, backgroundColor: 'transparent' }}
              value={promptDesc}
              readOnly
            />

            <div style={{ marginTop: 8, display: 'flex', gap: 24, alignItems: 'center', flexShrink: 0 }}>
              <label style={{ width: 80, flexShrink: 0 }}>색 참조</label>
              <button
                type="button"
                style={{ width: 100, padding: '6px 10px', borderRadius: 6, border: '1px solid #ccc', background: '#fff', cursor: 'pointer' }}
                onClick={() => setShowColors(v => !v)}
              >
                {showColors ? '색상 숨기기' : '색상 보기'}
              </button>
              <button
                type="button"
                style={{ width: 120, padding: '6px 10px', borderRadius: 6, border: '1px solid #ccc', background: '#fff', cursor: 'pointer' }}
                onClick={() => setShowColormap(v => !v)}
              >
                {showColormap ? '컬러맵 숨기기' : '컬러맵 보기'}
              </button>
            </div>

            {showColors && (
              <div style={{ marginTop: 10, padding: 10, borderRadius: 8, border: '1px solid #ddd', background: '#fff', maxHeight: 180, overflow: 'auto', flexShrink: 0 }}>
                <div style={{ fontWeight: 'bold', marginBottom: 10 }}>색상 샘플</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 8 }}>
                  {CSS_COLORS.map(({ name, hex }) => (
                    <div key={name} style={{ cursor: 'pointer' }} onClick={() => insertAtCursor(`${name}(${hex})`)}>
                      <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>{name}</div>
                      <div style={{ height: 28, borderRadius: 6, border: '1px solid #ccc', background: hex }} />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {showColormap && (
              <div style={{ marginTop: 10, padding: 10, borderRadius: 8, border: '1px solid #ddd', background: '#fff', maxHeight: 180, overflow: 'auto', flexShrink: 0 }}>
                <div style={{ fontWeight: 'bold', marginBottom: 10 }}>컬러맵 샘플</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12 }}>
                  {CONTINUOUS_COLORMAPS.map(({ name, colors }) => (
                    <div key={name} style={{ cursor: 'pointer' }} onClick={() => insertAtCursor(name)}>
                      <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>{name}</div>
                      <div style={{ height: 28, borderRadius: 6, border: '1px solid #ccc', background: `linear-gradient(to right, ${colors.join(',')})` }} />
                    </div>
                  ))}
                  {CATEGORICAL_COLORMAPS.map(({ name, colors }) => (
                    <div key={name} style={{ cursor: 'pointer' }} onClick={() => insertAtCursor(name)}>
                      <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>{name}</div>
                      <div style={{ display: 'flex', gap: 2 }}>
                        {colors.map((c, i) => (
                          <div key={i} style={{ flex: 1, height: 28, background: c, border: '1px solid #ccc', borderRadius: 2 }} />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* 프롬프트 */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <h4 style={{ marginBottom: 10, fontWeight: 'bold', flexShrink: 0 }}>프롬프트</h4>
            <textarea
              ref={promptRef}
              style={{ flex: 1, minHeight: 0, width: '100%', padding: 8, fontSize: '1rem', boxSizing: 'border-box', resize: 'none', border: '1px solid #ccc', borderRadius: 4 }}
              placeholder="예: 2024년 월별 생산수량에 대해 그래프를 그려주세요(표를 만들어 주세요, 분석해주세요)."
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              onClick={trackCursor}
              onKeyUp={trackCursor}
              onFocus={trackCursor}
            />
          </div>

          {/* 미리보기 결과 */}
          <div style={{ flex: 1.5, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <h4 style={{ marginBottom: 10, fontWeight: 'bold', flexShrink: 0 }}>미리보기 결과</h4>
            <div style={{ flex: 1, width: '100%', overflow: 'auto', padding: 8, boxSizing: 'border-box', border: '1px solid #ccc', borderRadius: 4, backgroundColor: '#f8f9fa', whiteSpace: 'pre-wrap', minHeight: 0 }}>
              {previewResult && (() => {
                const { message_type, message: msg, image_data, data } = previewResult
                if (message_type === 'image') {
                  return <img src={`data:image/png;base64,${image_data}`} alt="미리보기" style={{ maxWidth: '100%' }} />
                }
                if (message_type === 'table' && Array.isArray(data) && data.length > 0) {
                  const cols = Object.keys(data[0])
                  return (
                    <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
                      <thead>
                        <tr>{cols.map(c => (
                          <th key={c} style={{ border: '1px solid #ccc', padding: '4px 8px', background: '#f0f0f0', whiteSpace: 'nowrap' }}>{c}</th>
                        ))}</tr>
                      </thead>
                      <tbody>
                        {data.map((row, i) => (
                          <tr key={i}>{cols.map(c => (
                            <td key={c} style={{ border: '1px solid #ccc', padding: '4px 8px' }}>{row[c] ?? ''}</td>
                          ))}</tr>
                        ))}
                      </tbody>
                    </table>
                  )
                }
                if (message_type === 'error') {
                  return <div style={{ color: 'red' }}>오류: {msg}</div>
                }
                return <span>{msg}</span>
              })()}
            </div>
          </div>

        </div>
      </div>

      {/* 버튼 영역 — 높이 제한 컨테이너 바깥 */}
      <div className="button-group">
        <button type="button" className="icon-btn" onClick={handlePreview} disabled={previewLoading}>
          <div className="icon-wrapper">
            <img src="/icons/view.svg" className="icon-img config-icon" title="미리보기" alt="미리보기" />
            <span className="icon-label">미리보기</span>
          </div>
        </button>
      </div>

      {/* 전체 화면 로딩 오버레이 */}
      {previewLoading && (
        <div style={{ display: 'flex', position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', justifyContent: 'center', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 9999 }}>
          <div className="loading-content" style={{ background: 'var(--loadingback-color, #fff)', padding: '15px 25px', borderRadius: 8, color: 'var(--gray-600, #555)', fontSize: 16, fontWeight: 'bold', boxShadow: '0 2px 6px var(--black-shadow, rgba(0,0,0,0.3))' }}>
            <div className="spinner" />
            <div style={{ textAlign: 'center', marginTop: 8 }}>잠시만 기다려 주세요.</div>
          </div>
        </div>
      )}

    </div>
  )
}
