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
import { BulbOutlined, EyeOutlined, RedoOutlined, SaveOutlined, DeleteOutlined } from '@ant-design/icons'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useObjectFilterDatauid } from '@/hooks/useTables'
import { useChapterDatas } from '@/hooks/useDatas'
import { CSS_COLORS, CONTINUOUS_COLORMAPS, CATEGORICAL_COLORMAPS } from '@/utils/colorData'
import { getErrorMessage, getErrorDetail } from '@/utils/apiError'


export default function AiLlmPage({ objecttypecd, pageTitle }) {
  useLangStore((s) => s.translations)
  const { message, modal } = App.useApp()
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
      const detail = getErrorDetail(e) || e.message || t('msg.unknown.error')
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
      const warnings = res.data?.data_warnings || []
      if (warnings.length > 0) {
        modal.warning({
          title: t('ttl.data.type.warning'),
          content: (
            <div>
              {warnings.map((w) => (
                <div key={w.column} style={{ marginBottom: 8 }}>
                  <div>{t('msg.data.type.warning.detail').replace('{column}', w.column).replace('{count}', w.invalid_count)}</div>
                  <div style={{ color: '#888', fontSize: 12 }}>{t('lbl.examples')}: {w.examples.join(', ')}</div>
                </div>
              ))}
            </div>
          ),
        })
      }
    } catch (e) {
      message.error(getErrorMessage(e, 'msg.preview.error'))
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
      message.error(getErrorMessage(e, 'msg.save.error'))
    } finally {
      setSaveLoading(false)
    }
  }

  const handleDelete = () => {
    modal.confirm({
      content: t('msg.confirm.delete'),
      onOk: async () => {
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
          message.error(getErrorMessage(e, 'msg.delete.error'))
        } finally {
          setDeleteLoading(false)
        }
      },
    })
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 렌더
  // ─────────────────────────────────────────────────────────────────────────
  const CONTENT_HEIGHT = 'calc(100vh - 145px)'

  return (
    <div style={{ height: CONTENT_HEIGHT, display: 'flex', flexDirection: 'column', overflow: 'hidden', boxSizing: 'border-box' }}>

      {/* ── 헤더 ── */}
      <div className="page-title" style={{ flexShrink: 0, marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t(pageTitle)}{docnm ? ` - ${docnm}` : ''}</div>
        </div>
      </div>

      {/* ── 서브타이틀: 챕터명 | 항목명 ── */}
      <div className="panel-section" style={{ display: 'flex', alignItems: 'center', fontSize: 13, marginBottom: 16, flexShrink: 0 }}>
        <span style={{ color: '#888', flexShrink: 0 }}>{t('thd.chapternm')}: </span>
        <span style={{ flexShrink: 0 }}>{chapternm || '-'}</span>
        <span style={{ margin: '0 10px', color: '#d9d9d9', flexShrink: 0 }}>|</span>
        <span style={{ color: '#888', flexShrink: 0 }}>{t('lbl.objectnm_lbl')}: </span>
        <span style={{ flexShrink: 0 }}>{objectnm || '-'}</span>
      </div>

      {/* ── 필터 기본값 경고 배너 ── */}
      {isFilterDefault && (
        <div className="panel-section" style={{ marginBottom: 16, background: '#fff7e6', border: '1px solid #ffd591', color: '#d46b08', fontSize: 13, padding: '13px 18px', flexShrink: 0 }}>
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
        <div className="panel-section" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0 }}>

          {/* 카드 헤더: 액션 버튼 */}
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', height: 60, flexShrink: 0,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.prompt_ttl')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button type="button" className="btn btn-secondary" onClick={() => setModalOpen(true)} disabled={prompts.length === 0}>
                <BulbOutlined style={{ marginRight: 6 }} />{t('btn.sample.prompt')}
              </button>
              <button type="button" className="btn btn-secondary" onClick={handlePreview} disabled={previewLoading}>
                <EyeOutlined style={{ marginRight: 6 }} />{t('btn.preview_btn')}
              </button>
              <button type="button" className="btn btn-secondary" onClick={handleReset}>
                <RedoOutlined style={{ marginRight: 6 }} />{t('btn.new')}
              </button>
              {isEditYn && (
                <>
                  <span style={{ color: '#d9d9d9' }}>|</span>
                  <button type="button" className="btn btn-primary" onClick={handleSave} disabled={saveLoading}>
                    <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger"
                    onClick={handleDelete}
                    disabled={deleteLoading}
                    title={t('btn.delete')}
                    style={{ width: 32, height: 32, padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                  >
                    <DeleteOutlined />
                  </button>
                </>
              )}
            </div>
          </div>

          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6, overflow: 'hidden', minHeight: 0 }}>

            {/* ── 데이터 선택 행 ── */}
            <div style={{ display: 'flex', gap: 20, alignItems: 'center', marginBottom: 4, flexShrink: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <label style={{ whiteSpace: 'nowrap', fontWeight: 500 }}><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('ttl.data.list')}:</label>
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
                      <option key={dt.value} value={dt.value}>{t(dt.term_key)}</option>
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
              <div style={{ display: 'flex', gap: 24, alignItems: 'center', marginBottom: 8, flexShrink: 0 }}>
                <div style={{ flex: 1 }}>
                  <h4 style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>{t('ttl.prompt_ttl')}</h4>
                </div>
                <div style={{ flex: 1.5 }}>
                  <h4 style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>{t('ttl.preview.result')}</h4>
                </div>
              </div>

              {/* 내용 행 */}
              <div style={{ flex: 1, display: 'flex', gap: 24, minHeight: 0, overflow: 'hidden' }}>

              {/* 왼쪽: 프롬프트 입력 */}
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
                    fontSize: 13,
                    boxSizing: 'border-box',
                    resize: 'none',
                    border: '1px solid #ccc',
                    backgroundColor: '#f8f9fa',
                    borderRadius: 4,
                    minHeight: 0,
                  }}
                />
              </div>

              {/* 오른쪽: 미리보기 결과 */}
              <div style={{ flex: 1.5, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
                <div
                  style={{
                    flex: 1,
                    overflow: 'auto',
                    padding: 8,
                    fontSize: 13,
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

              {/* 색상/컬러맵 참조 영역 */}
              {objecttypecd !== 'SA' && (
                <div style={{ flexShrink: 0, marginTop: 8 }}>
                  <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 4 }}>
                    <label style={{ width: 60, fontSize: 13 }}>{t('lbl.color.ref')}</label>
                    <button type="button" className="btn btn-secondary" onClick={() => setShowColors((v) => !v)}>
                      {showColors ? t('btn.color.hide') : t('btn.color.show')}
                    </button>
                    {objecttypecd === 'CA' && (
                      <button type="button" className="btn btn-secondary" onClick={() => setShowColormap((v) => !v)}>
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

          </div>

        </div>
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
// AI 테이블 스타일(JSON) → React 인라인 style 변환
// backend가 [양식지정] 프롬프트를 해석해 내려주는 컬럼별 스타일(bgcolor/color/
// fontweight/fontsize/align)을 그대로 셀에 적용한다. 값이 없으면 undefined를
// 반환해 AntD Table 기본 스타일을 그대로 쓰게 둔다.
// ─────────────────────────────────────────────────────────────────────────────
function sizeToCss(value) {
  if (value === undefined || value === null || value === '') return undefined
  const str = String(value).trim()
  if (/^-?\d+(\.\d+)?(pt|px|em|rem|%)$/i.test(str)) return str
  if (/^-?\d+(\.\d+)?$/.test(str)) return `${str}pt`
  return undefined
}

function tableCellStyle(conf) {
  if (!conf || typeof conf !== 'object') return undefined
  const style = {}
  if (conf.bgcolor) style.backgroundColor = conf.bgcolor
  if (conf.color) style.color = conf.color
  if (conf.fontweight) style.fontWeight = conf.fontweight
  if (conf.align) style.textAlign = conf.align
  const fontSize = sizeToCss(conf.fontsize)
  if (fontSize) style.fontSize = fontSize
  return style
}

// 선 모양(style)별·굵기(weight)별 실제 두께(px). double은 두 줄이 보이도록 더 두껍게 잡는다.
// utilsPrj/chapter_making_ai_table.py의 BORDER_WIDTH_PX와 동일하게 맞춰야 미리보기와
// 최종 DOCX의 선 굵기가 일치한다.
const BORDER_WIDTH_PX = {
  solid: { thin: 1, normal: 2, thick: 4 },
  dashed: { thin: 1, normal: 2, thick: 4 },
  double: { thin: 3, normal: 4, thick: 6 },
}
const BORDER_DEFAULT_CONF = { color: '#000000', style: 'solid', weight: 'normal' }

function normalizeBorderConf(conf) {
  if (typeof conf === 'string') return { ...BORDER_DEFAULT_CONF, color: conf }
  if (conf && typeof conf === 'object') {
    const merged = { ...BORDER_DEFAULT_CONF }
    if (conf.color) merged.color = conf.color
    if (conf.style) merged.style = conf.style
    if (conf.weight) merged.weight = conf.weight
    return merged
  }
  return { ...BORDER_DEFAULT_CONF }
}

// {color, style, weight} → "2px dashed #ff1493" 같은 CSS 변 선언 값
function borderCss(conf) {
  const widths = BORDER_WIDTH_PX[conf.style] || BORDER_WIDTH_PX.solid
  const width = widths[conf.weight] ?? widths.normal
  return `${width}px ${conf.style} ${conf.color}`
}

// 테두리: idx번째 경계선(0=맨 앞 바깥, total=맨 뒤 바깥, sepIdx=구분선)의 스타일을 반환
function edgeConf(idx, total, sepIdx, sepConf, outerConf, innerConf) {
  if (idx === 0 || idx === total) return outerConf
  if (idx === sepIdx) return sepConf
  return innerConf
}

// rowIdx/colIdx(0-based, 헤더 행 포함) 위치의 셀에 적용할 4변 테두리 스타일.
// borders: {outer, header_sep, col_sep, inner} — 각 값은 {color, style, weight}.
// backend가 [양식지정]에서 테두리를 요청한 경우에만 채워서 내려준다. 프롬프트에
// 테두리 언급이 전혀 없으면 borders가 빈 객체로 오므로, 이때는 undefined를 반환해
// AntD 기본 테두리를 그대로 둔다.
function cellBorderStyle(rowIdx, colIdx, totalRows, totalCols, borders) {
  if (!borders || Object.keys(borders).length === 0) return undefined
  const outer = normalizeBorderConf(borders.outer)
  const headerSep = normalizeBorderConf(borders.header_sep)
  const colSep = normalizeBorderConf(borders.col_sep)
  const inner = normalizeBorderConf(borders.inner)
  const top = edgeConf(rowIdx, totalRows, 1, headerSep, outer, inner)
  const bottom = edgeConf(rowIdx + 1, totalRows, 1, headerSep, outer, inner)
  const left = edgeConf(colIdx, totalCols, 1, colSep, outer, inner)
  const right = edgeConf(colIdx + 1, totalCols, 1, colSep, outer, inner)
  return {
    borderTop: borderCss(top),
    borderBottom: borderCss(bottom),
    borderLeft: borderCss(left),
    borderRight: borderCss(right),
  }
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
    let headerStyles = {}
    let dataStyles = {}
    let borders = {}
    try { headerStyles = JSON.parse(result.table_header_json || '{}') } catch { /* ignore */ }
    try { dataStyles = JSON.parse(result.table_data_json || '{}') } catch { /* ignore */ }
    try { borders = JSON.parse(result.table_border_json || '{}') } catch { /* ignore */ }

    const columnKeys = Object.keys(result.data[0])
    const totalCols = columnKeys.length
    const totalRows = 1 + result.data.length // 헤더 1행 + 데이터 행

    const cols = columnKeys.map((k, colIdx) => ({
      title: k, dataIndex: k, key: k, ellipsis: true, width: 120,
      onHeaderCell: () => ({
        style: { ...tableCellStyle(headerStyles[k]), ...cellBorderStyle(0, colIdx, totalRows, totalCols, borders) },
      }),
      onCell: (_record, rowIdx) => ({
        style: { ...tableCellStyle(dataStyles[k]), ...cellBorderStyle(rowIdx + 1, colIdx, totalRows, totalCols, borders) },
      }),
    }))
    return (
      <div style={{ width: '100%', overflow: 'hidden' }}>
        <Table
          columns={cols}
          dataSource={result.data.map((row, i) => ({ ...row, _key: i }))}
          rowKey="_key"
          size="small"
          pagination={false}
          scroll={{ x: true }}
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


// 포맷: prm.chart_bar_title / prm.chart_bar_text1 / prm.chart_bar_text2
function promptTermKey(p, suffix) {
  return `${p.prompttypecd}.${p.promptkey}_${suffix}`
}

// 프롬프트 전용: translations → key (defaults 건너뜀)
function tPrompt(key) {
  const val = t(key)
  return val === key ? '' : val
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
    onApply(tPrompt(promptTermKey(selected, 'text1')))
  }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      title={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>{t('ttl.sample.prompt_ttl')}</span>
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
                key={p.promptkey}
                onClick={() => setSelected(p)}
                style={{
                  padding: '8px',
                  cursor: 'pointer',
                  borderBottom: '1px solid #eee',
                  backgroundColor: selected?.promptkey === p.promptkey ? '#e6f0fa' : 'transparent',
                }}
                onMouseEnter={(e) => { if (selected?.promptkey !== p.promptkey) e.currentTarget.style.backgroundColor = '#f5f5f5' }}
                onMouseLeave={(e) => { if (selected?.promptkey !== p.promptkey) e.currentTarget.style.backgroundColor = 'transparent' }}
              >
                {tPrompt(promptTermKey(p, 'title'))}
              </li>
            ))}
          </ul>
        </div>

        {/* 중앙: 프롬프트 설명 */}
        <div style={{ flex: '0 0 40%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <h6 style={{ fontSize: 16, marginBottom: 6 }}><strong>{t('ttl.prompt.desc')}</strong></h6>
          <textarea
            readOnly
            value={selected ? tPrompt(promptTermKey(selected, 'text2')) : ''}
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
            value={selected ? tPrompt(promptTermKey(selected, 'text1')) : ''}
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
