/**
 * AiLlmPage — AI 항목 설정 공통 컴포넌트
 * Django ai_common.html + ai_actions.js 구조를 그대로 반영.
 *
 * 사용:
 *   <AiLlmPage objecttypecd="CA" pageTitle="ttl.ai.chart.manage" />
 *   <AiLlmPage objecttypecd="SA" pageTitle="ttl.ai.sentence.manage" />
 *   <AiLlmPage objecttypecd="TA" pageTitle="ttl.ai.table.manage" />
 */
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { App, Modal, Spin, Table } from 'antd'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useObjectFilterDatauid } from '@/hooks/useTables'
import { useChapterDatas } from '@/hooks/useDatas'
import { CSS_COLORS, CONTINUOUS_COLORMAPS, CATEGORICAL_COLORMAPS } from '@/utils/colorData'


export default function AiLlmPage({ objecttypecd, pageTitle }) {
  useLangStore((s) => s.translations)
  const { message } = App.useApp()
  const [searchParams] = useSearchParams()
  const user = useAuthStore((s) => s.user)
  const docnm = user?.docnm
  const isEditYn = user?.editbuttonyn === 'Y'

  const chapteruid   = searchParams.get('chapteruid')  || ''
  const objectuid    = searchParams.get('objectuid')   || ''
  const objectnm     = searchParams.get('objectnm')    || ''
  const chapternmUrl = searchParams.get('chapternm')   || ''

  // ── 초기 데이터 ─────────────────────────────────────────────────────────────
  const [initLoading,   setInitLoading]   = useState(true)
  const [chapternm,     setChapternm]     = useState(chapternmUrl)
  const [displayTypes,  setDisplayTypes]  = useState([])
  const [prompts,       setPrompts]       = useState([])

  const { data: allDatas = [] } = useChapterDatas(chapteruid)

  // ── 폼 상태 ─────────────────────────────────────────────────────────────────
  const [selectedDatauid,     setSelectedDatauid]     = useState('')
  const [selectedDisplayType, setSelectedDisplayType] = useState('')
  const [promptText,          setPromptText]          = useState('')

  // ── 열이름 ─────────────────────────────────────────────────────────────────
  const [columns, setColumns] = useState([])

  // ── 색상/컬러맵 패널 ─────────────────────────────────────────────────────────
  const [showColors,   setShowColors]   = useState(false)
  const [showColormap, setShowColormap] = useState(false)

  // ── 샘플 프롬프트 모달 ───────────────────────────────────────────────────────
  const [modalOpen,      setModalOpen]      = useState(false)
  const [selectedPrompt, setSelectedPrompt] = useState(null)

  // ── 미리보기 ─────────────────────────────────────────────────────────────────
  const [previewResult,  setPreviewResult]  = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  // ── 저장/삭제 ─────────────────────────────────────────────────────────────
  const [saveLoading,   setSaveLoading]   = useState(false)
  const [deleteLoading, setDeleteLoading] = useState(false)

  // ── ObjectFilters 기본값 ──────────────────────────────────────────────────
  const [isFilterDefault, setIsFilterDefault] = useState(false)
  const { data: filterDatauid } = useObjectFilterDatauid(objectuid, !initLoading)

  // ── textarea ref (커서 위치 추적) ─────────────────────────────────────────
  const promptRef = useRef(null)
  const cursorPos = useRef(0)

  // ─────────────────────────────────────────────────────────────────────────
  // 초기 데이터 로드
  // ─────────────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!chapteruid) { setInitLoading(false); return }
    setInitLoading(true)
    apiClient.get('/llm/init', {
      params: { chapteruid, objectnm: objectnm || undefined, objectuid: objectuid || undefined, objecttypecd },
    }).then((r) => {
      const data = r.data
      if (!chapternmUrl && data.chapter?.chapternm) setChapternm(data.chapter.chapternm)
      setPrompts(data.prompts || [])
      setDisplayTypes(data.display_types || [])

      const ex = data.existing || {}
      if (ex.datauid) setSelectedDatauid(ex.datauid)
      if (ex.displaytype !== undefined) setSelectedDisplayType(ex.displaytype || '')
      if (ex.gptq !== undefined)        setPromptText(ex.gptq || '')
    }).catch((e) => {
      const detail = e.response?.data?.detail || e.message || '알 수 없는 오류'
      message.error(`${t('msg.init.load.error')}: ${detail}`)
    })
      .finally(() => setInitLoading(false))
  }, [chapteruid, objecttypecd])

  // ─────────────────────────────────────────────────────────────────────────
  // 데이터 선택 변경 → 열이름 로드
  // ─────────────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!selectedDatauid) { setColumns([]); return }
    apiClient.get('/llm/columns', { params: { datauid: selectedDatauid } })
      .then((r) => setColumns(r.data.columns || []))
      .catch(() => setColumns([]))
  }, [selectedDatauid])

  // filterDatauid → 기본 데이터 자동 선택
  useEffect(() => {
    if (!filterDatauid) return
    setSelectedDatauid(filterDatauid)
    setIsFilterDefault(true)
  }, [filterDatauid])

  // ─────────────────────────────────────────────────────────────────────────
  // textarea 커서 추적
  // ─────────────────────────────────────────────────────────────────────────
  const trackCursor = () => {
    if (promptRef.current) cursorPos.current = promptRef.current.selectionStart
  }

  const insertAtCursor = (text) => {
    const ta = promptRef.current
    if (!ta) return
    const pos = cursorPos.current
    const newVal = promptText.substring(0, pos) + text + promptText.substring(pos)
    setPromptText(newVal)
    const newPos = pos + text.length
    cursorPos.current = newPos
    setTimeout(() => {
      ta.setSelectionRange(newPos, newPos)
      ta.focus()
    }, 0)
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 버튼 핸들러
  // ─────────────────────────────────────────────────────────────────────────
  const handleReset = () => {
    setPromptText('')
    setPreviewResult(null)
  }

  const handlePreview = async () => {
    if (!objectnm || !selectedDatauid || !promptText.trim()) {
      message.warning(t('msg.ai.input.required'))
      return
    }
    setPreviewLoading(true)
    setPreviewResult(null)
    try {
      const res = await apiClient.post('/llm/preview', {
        chapteruid,
        objectnm,
        datauid:     selectedDatauid,
        prompt:      promptText,
        displaytype: selectedDisplayType || '',
        objecttypecd,
      })
      setPreviewResult(res.data)
    } catch (e) {
      message.error(e.response?.data?.detail || t('msg.preview.error'))
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleSave = async () => {
    if (!objectnm || !selectedDatauid || !promptText.trim()) {
      message.warning(t('msg.ai.input.required'))
      return
    }
    setSaveLoading(true)
    try {
      await apiClient.post('/llm/save', {
        chapteruid,
        objectnm,
        datauid:     selectedDatauid,
        gptq:        promptText,
        displaytype: selectedDisplayType || '',
        objecttypecd,
      })
      message.success(t('msg.save.success'))
    } catch (e) {
      message.error(e.response?.data?.detail || t('msg.save.error'))
    } finally {
      setSaveLoading(false)
    }
  }

  const handleDelete = async () => {
    if (!window.confirm(t('msg.confirm.delete'))) return
    setDeleteLoading(true)
    try {
      await apiClient.delete('/llm/delete', {
        data: { chapteruid, objectnm, objecttypecd },
      })
      message.success(t('msg.delete.success'))
      handleReset()
      setSelectedDatauid('')
      setSelectedDisplayType('')
    } catch (e) {
      message.error(e.response?.data?.detail || t('msg.delete.error'))
    } finally {
      setDeleteLoading(false)
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 렌더
  // ─────────────────────────────────────────────────────────────────────────
  const CONTENT_HEIGHT = 'calc(100vh - 100px)'

  return (
    <div style={{ height: CONTENT_HEIGHT, display: 'flex', flexDirection: 'column', overflow: 'hidden', boxSizing: 'border-box' }}>

      {/* ── 헤더 ── */}
      <div className="page-title" style={{ flexShrink: 0, marginBottom: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t(pageTitle)}{docnm ? ` - ${docnm}` : ''}</div>
        </div>
      </div>

      {/* ── 서브타이틀: 챕터명 | 항목명 ── */}
      <div style={{ marginBottom: 16, paddingLeft: 16, fontSize: 15, fontWeight: 500, color: 'var(--gray-700)', flexShrink: 0 }}>
        {chapternm && <span>{t('lbl.chapternm')}: {chapternm}</span>}
        {chapternm && objectnm && <span style={{ margin: '0 14px', color: '#d9d9d9' }}>|</span>}
        {objectnm && <span>{t('lbl.objectnm_lbl')}: {objectnm}</span>}
      </div>

      {/* ── 필터 기본값 경고 배너 ── */}
      {isFilterDefault && (
        <div style={{ marginBottom: 12, padding: '8px 14px', background: '#fff7e6', border: '1px solid #ffd591', borderRadius: 6, color: '#d46b08', fontSize: 13, flexShrink: 0 }}>
          {t('msg.dataset.filter.readonly')}
        </div>
      )}

      {/* ── 로딩 중 ── */}
      {initLoading && (
        <div style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
          <Spin size="large" />
        </div>
      )}

      {/* ── 본문 (로딩 완료 후) ── */}
      {!initLoading && (
        <>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6, overflow: 'hidden', minHeight: 0 }}>

            {/* ── 데이터 선택 행 ── */}
            <div style={{ display: 'flex', gap: 20, alignItems: 'center', marginBottom: 4, flexShrink: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <label style={{ whiteSpace: 'nowrap', fontWeight: 500 }}>{t('ttl.data.list')}:</label>
                <select
                  value={selectedDatauid}
                  onChange={(e) => { if (!isFilterDefault) setSelectedDatauid(e.target.value) }}
                  disabled={isFilterDefault}
                  style={{ minWidth: 200, ...(isFilterDefault ? { cursor: 'not-allowed', opacity: 0.6 } : {}) }}
                >
                  <option value="">{t('msg.select.placeholder')}</option>
                  {allDatas.map((d) => (
                    <option key={d.datauid} value={d.datauid}>{d.datanm}</option>
                  ))}
                </select>
              </div>
              {(objecttypecd === 'CA' || objecttypecd === 'SA') && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <label style={{ whiteSpace: 'nowrap', fontWeight: 500 }}>
                    {objecttypecd === 'CA' ? t('lbl.chart.type_lbl') : t('lbl.sentence.type')}
                  </label>
                  <select
                    value={selectedDisplayType}
                    onChange={(e) => setSelectedDisplayType(e.target.value)}
                    style={{ minWidth: 150 }}
                  >
                    <option value="">{t('msg.select.placeholder')}</option>
                    {displayTypes.map((dt) => (
                      <option key={dt.value} value={dt.value}>{dt.label}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            {/* ── 열이름 ── */}
            <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', flexShrink: 0, gap: 4 }}>
              <span style={{ fontWeight: 600, fontSize: 14, color: '#333', marginRight: 8 }}>{t('lbl.colnames')}</span>
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

            {/* ── 하단: 프롬프트 입력 | 미리보기 결과 ── */}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>

              {/* 공유 타이틀 행 — 한 행으로 묶어 textarea / preview 시작 위치 통일 */}
              <div style={{ display: 'flex', gap: 20, alignItems: 'center', marginBottom: 8, flexShrink: 0 }}>
                <div style={{ flex: 1 }}>
                  <h3 style={{ margin: 0 }}>{t('ttl.prompt_ttl')}</h3>
                </div>
                <div style={{ flex: 1.5, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h3 style={{ margin: 0 }}>{t('ttl.preview.result')}</h3>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <button type="button" className="btn btn-primary" onClick={() => setModalOpen(true)} disabled={prompts.length === 0}>{t('btn.sample.prompt')}</button>
                    <button type="button" className="btn btn-primary" onClick={handlePreview} disabled={previewLoading}>{t('btn.preview_btn')}</button>
                    <span style={{ color: '#d9d9d9', margin: '0 12px' }}>|</span>
                    <button type="button" className="btn btn-primary" onClick={handleReset}>{t('btn.new')}</button>
                    {isEditYn && (
                      <>
                        <button type="button" className="btn btn-primary" onClick={handleSave} disabled={saveLoading}>{t('btn.save')}</button>
                        <button type="button" className="btn btn-danger" onClick={handleDelete} disabled={deleteLoading}>{t('btn.delete')}</button>
                      </>
                    )}
                  </div>
                </div>
              </div>

              {/* 내용 행 */}
              <div style={{ flex: 1, display: 'flex', gap: 20, minHeight: 0, overflow: 'hidden' }}>

              {/* 왼쪽: 프롬프트 입력 + 색상/컬러맵 */}
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
                <textarea
                  ref={promptRef}
                  value={promptText}
                  onChange={(e) => setPromptText(e.target.value)}
                  onClick={trackCursor}
                  onKeyUp={trackCursor}
                  onFocus={trackCursor}
                  placeholder={t('msg.ph.prompt')}
                  style={{
                    flex: 1,
                    width: '100%',
                    padding: 8,
                    fontSize: '1rem',
                    boxSizing: 'border-box',
                    resize: 'none',
                    border: '1px solid #ccc',
                    backgroundColor: '#f8f9fa',
                    borderRadius: 4,
                    minHeight: 0,
                  }}
                />

                {/* 색상/컬러맵 참조 영역 */}
                {objecttypecd !== 'SA' && (
                  <div style={{ flexShrink: 0, marginTop: 8 }}>
                    <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 4 }}>
                      <label style={{ width: 60, fontSize: 13 }}>{t('lbl.color.ref')}</label>
                      <button type="button" className="btn btn-primary" style={{ fontSize: 12, padding: '2px 8px' }} onClick={() => setShowColors((v) => !v)}>
                        {showColors ? t('btn.color.hide') : t('btn.color.show')}
                      </button>
                      {objecttypecd === 'CA' && (
                        <button type="button" className="btn btn-primary" style={{ fontSize: 12, padding: '2px 8px' }} onClick={() => setShowColormap((v) => !v)}>
                          {showColormap ? t('btn.colormap.hide') : t('btn.colormap.show')}
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

              {/* 오른쪽: 미리보기 결과 */}
              <div style={{ flex: 1.5, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
                <div
                  style={{
                    flex: 1,
                    overflow: 'auto',
                    padding: 8,
                    border: '1px solid #ccc',
                    borderRadius: 4,
                    backgroundColor: '#f8f9fa',
                    minHeight: 0,
                    minWidth: 0,
                    boxSizing: 'border-box',
                  }}
                >
                  {previewResult ? <PreviewDisplay result={previewResult} /> : null}
                </div>
              </div>

              </div>{/* 내용 행 end */}
            </div>

          </div>

        </>
      )}

      {/* ── 미리보기 로딩 오버레이 ── */}
      {previewLoading && (
        <div style={{
          position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
          background: 'rgba(0,0,0,0.5)',
          display: 'flex', justifyContent: 'center', alignItems: 'center',
          zIndex: 9999,
        }}>
          <div style={{
            background: '#fafae5', padding: '20px 30px', borderRadius: 8,
            fontSize: 16, fontWeight: 'bold', color: '#6c757d',
            boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
            display: 'flex', alignItems: 'center', gap: 12,
          }}>
            <Spin />
            <span>{t('msg.loading.wait')}</span>
          </div>
        </div>
      )}

      {/* ── 샘플 프롬프트 모달 ── */}
      <SamplePromptModal
        open={modalOpen}
        prompts={prompts}
        onClose={() => setModalOpen(false)}
        onApply={(text) => {
          setPromptText(text)
          setModalOpen(false)
        }}
      />
    </div>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// 미리보기 결과 표시
// ─────────────────────────────────────────────────────────────────────────────
function PreviewDisplay({ result }) {
  if (!result) return null

  if (result.message_type === 'image') {
    return (
      <img
        src={`data:image/png;base64,${result.image_data}`}
        alt="preview"
        style={{ display: 'block', maxWidth: '100%', height: 'auto' }}
      />
    )
  }

  if (result.message_type === 'text') {
    return (
      <div style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>{result.message}</div>
    )
  }

  if (result.message_type === 'table' && Array.isArray(result.data) && result.data.length > 0) {
    const cols = Object.keys(result.data[0]).map((k) => ({
      title: k, dataIndex: k, key: k, ellipsis: true, width: 120,
    }))
    return (
      <div style={{ width: '100%', overflow: 'hidden' }}>
        <Table
          columns={cols}
          dataSource={result.data.map((row, i) => ({ ...row, _key: i }))}
          rowKey="_key"
          size="small"
          pagination={false}
          scroll={{ x: true, y: 300 }}
          style={{ width: '100%' }}
        />
      </div>
    )
  }

  if (result.message_type === 'error') {
    return <div style={{ color: 'red' }}>{result.message}</div>
  }

  return null
}


// ─────────────────────────────────────────────────────────────────────────────
// 샘플 프롬프트 모달 (Django ai_common.html 모달과 동일한 3분할 구조)
// ─────────────────────────────────────────────────────────────────────────────
function SamplePromptModal({ open, prompts, onClose, onApply }) {
  useLangStore((s) => s.translations)
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    if (open) setSelected(null)
  }, [open])

  const handleApply = () => {
    if (!selected) return
    onApply(selected.prompt || '')
  }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      title={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>{t('ttl.sample.prompt')}</span>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleApply}
            disabled={!selected}
            style={{ marginRight: 30 }}
          >
            {t('btn.prompt.replace')}
          </button>
        </div>
      }
      width="90%"
      styles={{ body: { height: '70vh', display: 'flex', flexDirection: 'column', padding: 0 } }}
    >
      <div style={{ display: 'flex', flex: 1, gap: 15, minHeight: 0, padding: '10px 20px 20px' }}>

        {/* 왼쪽: 샘플 목록 */}
        <div style={{ flex: '0 0 20%', borderRight: '1px solid #ccc', paddingRight: 10, overflowY: 'auto' }}>
          <h6 style={{ fontSize: 16, marginBottom: 6 }}><strong>{t('ttl.sample.list')}</strong></h6>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, fontSize: 14 }}>
            {prompts.map((p) => (
              <li
                key={p.promptuid}
                onClick={() => setSelected(p)}
                style={{
                  padding: '8px',
                  cursor: 'pointer',
                  borderBottom: '1px solid #eee',
                  backgroundColor: selected?.promptuid === p.promptuid ? '#e6f0fa' : 'transparent',
                }}
                onMouseEnter={(e) => { if (selected?.promptuid !== p.promptuid) e.currentTarget.style.backgroundColor = '#f5f5f5' }}
                onMouseLeave={(e) => { if (selected?.promptuid !== p.promptuid) e.currentTarget.style.backgroundColor = 'transparent' }}
              >
                {p.promptnm}
              </li>
            ))}
          </ul>
        </div>

        {/* 중앙: 프롬프트 설명 */}
        <div style={{ flex: '0 0 40%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <h6 style={{ fontSize: 16, marginBottom: 6 }}><strong>{t('ttl.prompt.desc')}</strong></h6>
          <textarea
            readOnly
            value={selected?.desc || ''}
            style={{
              flex: 1, width: '100%', resize: 'none', padding: 8,
              border: '1px solid #ccc', fontSize: 14, whiteSpace: 'pre-wrap', minHeight: 0,
            }}
          />
        </div>

        {/* 오른쪽: 프롬프트 내용 */}
        <div style={{ flex: '0 0 40%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <h6 style={{ fontSize: 16, marginBottom: 6 }}><strong>{t('ttl.prompt_ttl')}</strong></h6>
          <textarea
            readOnly
            value={selected?.prompt || ''}
            style={{
              flex: 1, width: '100%', resize: 'none', padding: 8,
              border: '1px solid #ccc', fontSize: 14, whiteSpace: 'pre-wrap', minHeight: 0,
            }}
          />
        </div>
      </div>
    </Modal>
  )
}
