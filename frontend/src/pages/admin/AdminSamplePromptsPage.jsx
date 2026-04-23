import { useEffect, useRef, useState } from 'react'
import { App } from 'antd'
import {
  useAdminSamplePrompts,
  useSaveSamplePrompt,
  useDeleteSamplePrompt,
} from '@/hooks/useAdmin'
import apiClient from '@/api/client'
import { CSS_COLORS, CONTINUOUS_COLORMAPS, CATEGORICAL_COLORMAPS } from '@/utils/colorData'

const SUB_TYPE_OPTIONS = {
  CA: [
    { value: 'bar',       label: 'Bar Chart' },
    { value: 'line',      label: 'Line Chart' },
    { value: 'pie',       label: 'Pie Chart' },
    { value: 'scatter',   label: 'Scatter' },
    { value: 'boxplot',   label: 'Box Plot' },
    { value: 'histogram', label: 'Histogram' },
    { value: 'dual_axis', label: 'Dual Axis' },
    { value: 'heatmap',   label: 'Heatmap' },
    { value: 'subplot',   label: 'Subplot' },
  ],
  SA: [
    { value: 'simple_question', label: '단순 질의' },
    { value: 'summary',         label: '요약' },
    { value: 'report',          label: '보고서' },
    { value: 'predict',         label: '예측' },
  ],
  TA: [{ value: 'table', label: '테이블' }],
}

const SUB_LABEL = { CA: '차트 유형', SA: '문장 유형', TA: '테이블 유형' }

export default function AdminSamplePromptsPage() {
  const { message, modal } = App.useApp()

  const [objectType,        setObjectType]        = useState('CA')
  const [displaytype,       setDisplaytype]        = useState('')
  const [selectedDatauid,   setSelectedDatauid]    = useState('')
  const [selectedPromptuid, setSelectedPromptuid]  = useState('')
  const [promptnmInput,     setPromptnmInput]      = useState('')
  const [promptDesc,        setPromptDesc]         = useState('')
  const [prompt,            setPrompt]             = useState('')
  const [previewResult,     setPreviewResult]      = useState(null)
  const [previewLoading,    setPreviewLoading]     = useState(false)

  // ── 열이름 ─────────────────────────────────────────────────────────────────
  const [columns, setColumns] = useState([])

  // ── 색상/컬러맵 패널 ─────────────────────────────────────────────────────────
  const [showColors,   setShowColors]   = useState(false)
  const [showColormap, setShowColormap] = useState(false)

  // ── 프롬프트 textarea 커서 추적 ───────────────────────────────────────────
  const promptRef = useRef(null)
  const cursorPos = useRef(0)

  const { data = {}, isLoading, isError, error } = useAdminSamplePrompts(objectType, displaytype || undefined)
  const saveMutation   = useSaveSamplePrompt()
  const deleteMutation = useDeleteSamplePrompt()

  const { prompts = [], datas = [] } = data

  // ── 데이터 선택 변경 → 열이름 로드 ──────────────────────────────────────────
  useEffect(() => {
    if (!selectedDatauid) { setColumns([]); return }
    apiClient.get('/llm/columns', { params: { datauid: selectedDatauid } })
      .then((r) => setColumns(r.data.columns || []))
      .catch(() => setColumns([]))
  }, [selectedDatauid])

  // ── 커서 추적 ────────────────────────────────────────────────────────────────
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
    setDisplaytype('')
    handleNew()
  }

  const handlePromptSelect = (promptuid) => {
    if (!promptuid) { handleNew(); return }
    const p = prompts.find((x) => String(x.promptuid) === String(promptuid))
    if (!p) return
    setSelectedPromptuid(p.promptuid)
    setPromptnmInput(p.promptnm)
    setSelectedDatauid(p.datauid?.toString() || '')
    setPromptDesc(p.desc || '')
    setPrompt(p.prompt || '')
  }

  const handleNew = () => {
    setSelectedPromptuid('')
    setPromptnmInput('')
    setSelectedDatauid('')
    setPromptDesc('')
    setPrompt('')
    setPreviewResult(null)
  }

  const handlePreview = async () => {
    if (!prompt.trim()) { modal.warning({ title: '프롬프트를 입력해주세요.' }); return }
    setPreviewLoading(true)
    setPreviewResult(null)
    try {
      const res = await apiClient.post('/admin/sample-prompts/preview', {
        prompt,
        objecttypecd: objectType,
        datauid:      selectedDatauid || null,
        displaytype:  displaytype || null,
      })
      setPreviewResult(res.data)
    } catch (e) {
      setPreviewResult({ message_type: 'error', message: e?.response?.data?.detail || '미리보기 오류가 발생했습니다.' })
    } finally {
      setPreviewLoading(false)
    }
  }

  const doSave = (forceUpdate = false) => {
    saveMutation.mutate(
      {
        promptuid:    selectedPromptuid || null,
        objecttypecd: objectType,
        datauid:      selectedDatauid || null,
        promptnm:     promptnmInput,
        prompt,
        promptdesc:   promptDesc,
        displaytype:  displaytype || null,
        force_update: forceUpdate,
      },
      {
        onSuccess: (res) => {
          if (res?.error === 'confirm_update') {
            modal.confirm({
              title: '수정 확인',
              content: res.message,
              okText: '저장', cancelText: '취소',
              onOk: () => doSave(true),
            })
          } else if (res?.success) {
            handleNew()
          }
        },
      },
    )
  }

  const handleSave = () => {
    if (!promptnmInput.trim()) { modal.warning({ title: '샘플 프롬프트 이름을 입력해주세요.' }); return }
    doSave(false)
  }

  const handleDelete = () => {
    if (!selectedPromptuid) { modal.warning({ title: '삭제할 프롬프트를 선택해주세요.' }); return }
    modal.confirm({
      title: '삭제 확인',
      content: '정말 삭제하시겠습니까?',
      okText: '삭제', cancelText: '취소', okButtonProps: { danger: true },
      onOk: () => deleteMutation.mutate(selectedPromptuid, { onSuccess: handleNew }),
    })
  }

  const subTypeOpts  = SUB_TYPE_OPTIONS[objectType] || []
  const filterStyle  = { display: 'flex', alignItems: 'center', gap: 8 }
  const labelStyle   = { width: 180, flexShrink: 0, fontWeight: 600 }

  return (
    <div>
      <div className="page-title" style={{ marginBottom: 8 }}>
        <div className="filter-item">
          <div className="gradient-bar" />
          샘플 프롬프트 관리
        </div>
      </div>

      {isError && (
        <div style={{ color: 'red', marginBottom: 8 }}>
          데이터 로드 실패: {error?.response?.data?.detail || error?.message || '알 수 없는 오류'}
        </div>
      )}

      {/* 전체 래퍼 — 버튼은 이 안에서 height 영역 바깥에 위치 */}
      <div style={{ overflowY: 'auto' }}>

        {/* 높이 제한 컨테이너 */}
        <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 260px)', boxSizing: 'border-box', gap: 10, overflow: 'hidden' }}>

          {/* 상단 필터 영역 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 15, flexShrink: 0 }}>

            {/* 첫 번째 줄: 개체 유형 / 하위 유형 / 샘플 프롬프트 불러오기 */}
            <div style={{ display: 'flex', gap: 20 }}>
              <div style={{ flex: 1 }}>
                <div style={filterStyle}>
                  <label style={{ ...labelStyle, width: 120 }}>개체 유형 :</label>
                  <select
                    style={{ flex: 1, marginRight: 20 }}
                    value={objectType}
                    onChange={(e) => handleObjectTypeChange(e.target.value)}
                  >
                    <option value="CA">차트 (Chart)</option>
                    <option value="SA">문장 (Sentence)</option>
                    <option value="TA">테이블 (Table)</option>
                  </select>
                </div>
              </div>

              <div style={{ flex: 1 }}>
                <div style={filterStyle}>
                  <label style={labelStyle}>{SUB_LABEL[objectType]} :</label>
                  <select
                    style={{ flex: 1, marginRight: 20 }}
                    value={displaytype}
                    onChange={(e) => { setDisplaytype(e.target.value); handleNew() }}
                  >
                    <option value="">--- 선택 ---</option>
                    {subTypeOpts.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div style={{ flex: 1 }}>
                <div style={filterStyle}>
                  <label style={labelStyle}>샘플 프롬프트 불러오기 :</label>
                  <select
                    style={{ flex: 1, marginRight: 20 }}
                    value={selectedPromptuid}
                    onChange={(e) => handlePromptSelect(e.target.value)}
                    disabled={isLoading}
                  >
                    <option value="">--- 선택 ---</option>
                    {prompts.map((p) => (
                      <option key={p.promptuid} value={p.promptuid}>{p.promptnm}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>

            {/* 두 번째 줄: 데이터 목록 / 샘플 프롬프트 이름 */}
            <div style={{ display: 'flex', gap: 20 }}>
              <div style={{ flex: 1 }}>
                <div style={filterStyle}>
                  <label style={{ ...labelStyle, width: 120 }}>데이터 목록 :</label>
                  <select
                    style={{ flex: 1, marginRight: 20 }}
                    value={selectedDatauid}
                    onChange={(e) => setSelectedDatauid(e.target.value)}
                  >
                    <option value="">--- 선택 ---</option>
                    {datas.map((d) => (
                      <option key={d.datauid} value={String(d.datauid)}>{d.datanm}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div style={{ flex: 1 }}>
                <div style={filterStyle}>
                  <label style={labelStyle}>샘플 프롬프트 이름 :</label>
                  <input
                    type="text"
                    style={{ flex: 1, marginRight: 20, padding: 6, border: '1px solid #ccc', borderRadius: 4 }}
                    value={promptnmInput}
                    placeholder="신규 프롬프트 이름 입력"
                    onChange={(e) => setPromptnmInput(e.target.value)}
                  />
                </div>
              </div>

              <div style={{ flex: 1 }} />
            </div>
          </div>

          {/* 열이름 행 */}
          <div style={{ flexShrink: 0, color: '#333' }}>
            <strong>열이름&nbsp;&nbsp;</strong>
            {columns.map((col, idx) => (
              <span
                key={col}
                onClick={() => insertAtCursor(col)}
                style={{
                  display: 'inline-block',
                  padding: '2px 4px',
                  marginRight: 4,
                  marginBottom: 4,
                  marginLeft: idx === 0 ? 20 : 0,
                  cursor: 'pointer',
                  fontSize: 13,
                }}
                onMouseEnter={(e) => {
                  e.target.style.textDecoration = 'underline'
                  e.target.style.textDecorationColor = 'silver'
                  e.target.style.color = 'black'
                  e.target.style.fontWeight = 'bold'
                }}
                onMouseLeave={(e) => {
                  e.target.style.textDecoration = 'none'
                  e.target.style.color = 'inherit'
                  e.target.style.fontWeight = 'normal'
                }}
              >
                {col}
              </span>
            ))}
          </div>

          {/* 3분할 텍스트 영역 */}
          <div style={{ flex: 8, display: 'flex', flexDirection: 'row', gap: 20, minHeight: 0 }}>

            {/* 프롬프트 설명 + 색상/컬러맵 */}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <h4 style={{ marginBottom: 10, fontWeight: 'bold', flexShrink: 0 }}>프롬프트 설명</h4>
              <textarea
                style={{ flex: 1, minHeight: 0, width: '100%', padding: 8, fontSize: '1rem', boxSizing: 'border-box', resize: 'none', border: '1px solid #ccc', backgroundColor: '#f8f9fa', borderRadius: 4 }}
                value={promptDesc}
                onChange={(e) => setPromptDesc(e.target.value)}
              />

              {/* 색상/컬러맵 참조 영역 */}
              {objectType !== 'SA' && (
                <div style={{ flexShrink: 0, marginTop: 8 }}>
                  <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 4 }}>
                    <label style={{ width: 60, fontSize: 13 }}>색 참조</label>
                    <button type="button" className="btn" onClick={() => setShowColors((v) => !v)}>
                      {showColors ? '색상 숨기기' : '색상 보기'}
                    </button>
                    {objectType === 'CA' && (
                      <button type="button" className="btn" onClick={() => setShowColormap((v) => !v)}>
                        {showColormap ? '컬러맵 숨기기' : '컬러맵 보기'}
                      </button>
                    )}
                  </div>
                  {showColors && (
                    <div style={{ maxHeight: 180, overflow: 'auto', border: '1px solid #ddd', borderRadius: 4, padding: 8, marginBottom: 4 }}>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 6 }}>
                        {CSS_COLORS.map(({ name, hex }) => (
                          <div
                            key={name}
                            style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 3 }}
                            onClick={() => insertAtCursor(`${name}(${hex})`)}
                          >
                            <div style={{ fontSize: '0.8rem', fontWeight: 600 }}>{name}</div>
                            <div style={{ height: 20, borderRadius: 4, border: '1px solid #ccc', background: hex }} title={hex} />
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {showColormap && (
                    <div style={{ maxHeight: 180, overflow: 'auto', border: '1px solid #ddd', borderRadius: 4, padding: 8 }}>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 6 }}>
                        {CONTINUOUS_COLORMAPS.map(({ name, colors }) => (
                          <div key={name} style={{ cursor: 'pointer' }} onClick={() => insertAtCursor(name)}>
                            <div style={{ fontSize: '0.8rem', fontWeight: 600 }}>{name}</div>
                            <div style={{ height: 20, background: `linear-gradient(to right, ${colors.join(',')})`, border: '1px solid #ccc', borderRadius: 4 }} />
                          </div>
                        ))}
                        {CATEGORICAL_COLORMAPS.map(({ name, colors }) => (
                          <div key={name} style={{ cursor: 'pointer' }} onClick={() => insertAtCursor(name)}>
                            <div style={{ fontSize: '0.8rem', fontWeight: 600 }}>{name}</div>
                            <div style={{ display: 'flex', gap: 2 }}>
                              {colors.map((c, i) => (
                                <div key={i} style={{ flex: 1, height: 20, background: c, border: '1px solid #ccc', borderRadius: 2 }} />
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* 프롬프트 */}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <h4 style={{ marginBottom: 10, fontWeight: 'bold', flexShrink: 0 }}>프롬프트</h4>
              <textarea
                ref={promptRef}
                style={{ flex: 1, minHeight: 0, width: '100%', padding: 8, fontSize: '1rem', boxSizing: 'border-box', resize: 'none', border: '1px solid #ccc', backgroundColor: '#f8f9fa', borderRadius: 4 }}
                placeholder="예: 2024년 월별 생산수량에 대해 그래프를 그려주세요."
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onClick={trackCursor}
                onKeyUp={trackCursor}
                onFocus={trackCursor}
              />
            </div>

            {/* 미리보기 결과 */}
            <div style={{ flex: 1.5, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <h4 style={{ marginBottom: 10, fontWeight: 'bold', flexShrink: 0 }}>미리보기 결과</h4>
              <div style={{ flex: 1, padding: 8, border: '1px solid #ccc', backgroundColor: '#f8f9fa', borderRadius: 4, overflowY: 'auto', fontSize: 13, color: '#555', position: 'relative', minHeight: 0 }}>
                {previewLoading && (
                  <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(255,255,255,0.7)' }}>
                    <div className="spinner" />
                  </div>
                )}
                {!previewLoading && previewResult && (() => {
                  const { message_type, message: msg, image_data, data } = previewResult
                  if (message_type === 'image') {
                    return <img src={`data:image/png;base64,${image_data}`} alt="미리보기" style={{ maxWidth: '100%' }} />
                  }
                  if (message_type === 'table' && Array.isArray(data) && data.length > 0) {
                    const cols = Object.keys(data[0])
                    return (
                      <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
                        <thead>
                          <tr>{cols.map((c) => (
                            <th key={c} style={{ border: '1px solid #ccc', padding: '4px 8px', background: '#f0f0f0', whiteSpace: 'nowrap' }}>{c}</th>
                          ))}</tr>
                        </thead>
                        <tbody>
                          {data.map((row, i) => (
                            <tr key={i}>{cols.map((c) => (
                              <td key={c} style={{ border: '1px solid #ccc', padding: '4px 8px' }}>{row[c] ?? ''}</td>
                            ))}</tr>
                          ))}
                        </tbody>
                      </table>
                    )
                  }
                  if (message_type === 'error') {
                    return <span style={{ color: 'red' }}>{msg}</span>
                  }
                  return <span style={{ whiteSpace: 'pre-wrap' }}>{msg}</span>
                })()}
              </div>
            </div>
          </div>

        </div>

        {/* 버튼 영역 — 높이 제한 컨테이너 바깥 */}
        <div className="button-group" style={{ marginTop: 8 }}>
          <button type="button" className="icon-btn" onClick={handleNew}>
            <div className="icon-wrapper">
              <img src="/icons/new.svg" className="icon-img new-icon" title="신규" alt="신규" />
              <span className="icon-label">신규</span>
            </div>
          </button>
          <button type="button" className="icon-btn" onClick={handleSave} disabled={saveMutation.isPending}>
            <div className="icon-wrapper">
              <img src="/icons/save.svg" className="icon-img save-icon" title="저장" alt="저장" />
              <span className="icon-label">저장</span>
            </div>
          </button>
          <button type="button" className="icon-btn" onClick={handleDelete} disabled={deleteMutation.isPending || !selectedPromptuid}>
            <div className="icon-wrapper">
              <img src="/icons/delete.svg" className="icon-img del-icon" title="삭제" alt="삭제" />
              <span className="icon-label">삭제</span>
            </div>
          </button>
          <button type="button" className="icon-btn" onClick={handlePreview} disabled={previewLoading}>
            <div className="icon-wrapper">
              <img src="/icons/view.svg" className="icon-img config-icon" title="미리보기" alt="미리보기" />
              <span className="icon-label">미리보기</span>
            </div>
          </button>
        </div>

      </div>
    </div>
  )
}
