/**
 * MasterTablesPage — UI 테이블 설정
 * Django master_tables.html 구조 그대로 반영
 * 3열: 데이터 목록 | 머리글 설정+정렬 | 값 설정(컬럼별)  + 미리보기 모달
 */
import { useEffect, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { App } from 'antd'
import apiClient from '@/api/client'
import { useChapterDatas, useDatacols } from '@/hooks/useDatas'
import { useTable, useSaveTable, useDeleteTable } from '@/hooks/useTables'

const ALIGN_OPTIONS = ['left', 'center', 'right']

export default function MasterTablesPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const chapteruid = searchParams.get('chapteruid') || ''
  const objectnm   = searchParams.get('objectnm')   || ''
  const objectuid  = searchParams.get('objectuid')  || ''
  const chapternm  = searchParams.get('chapternm')  || ''

  const { data: allDatas = [], isLoading: datasLoading } = useChapterDatas(chapteruid)
  const { data: tableData }     = useTable(chapteruid, objectnm)
  const saveTable   = useSaveTable()
  const deleteTable = useDeleteTable()

  const [selectedDatauid, setSelectedDatauid] = useState('')
  const { data: rawDatacols = [] } = useDatacols(selectedDatauid)

  // 컬럼 순서 (drag 대신 up/down)
  const [colOrder, setColOrder] = useState([])

  // 머리글(tablejson) 상태
  const [tablejson, setTablejson] = useState({
    row_visible:    true,
    row_bgcolor:    '#ffffff',
    row_color:      '#000000',
    row_align:      'center',
    row_fontweight: 'bold',
    row_fontsize:   14,
    row_bordercolor:'#000000',
    sort:           [],
  })

  // 컬럼별(coljson) 상태
  const [coljson, setColjson] = useState({})

  // 기본값 행 상태
  const [defBg,       setDefBg]       = useState('#ffffff')
  const [defColor,    setDefColor]    = useState('#000000')
  const [defFontsize, setDefFontsize] = useState(14)
  const [defWidth,    setDefWidth]    = useState(100)

  // 미리보기 모달
  const [previewHtml,    setPreviewHtml]    = useState('')
  const [previewOpen,    setPreviewOpen]    = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)

  // 기존 설정 로드
  useEffect(() => {
    if (!tableData) return
    if (tableData.datauid) setSelectedDatauid(tableData.datauid)
    if (tableData.tablejson && Object.keys(tableData.tablejson).length)
      setTablejson((p) => ({ ...p, ...tableData.tablejson }))
    if (tableData.coljson && Object.keys(tableData.coljson).length)
      setColjson(tableData.coljson)
  }, [tableData])

  // datacols → colOrder + coljson 초기화
  useEffect(() => {
    if (!rawDatacols.length) return
    setColOrder(rawDatacols.map((c) => c.dispcolnm || c.querycolnm))
    setColjson((prev) => {
      const next = { ...prev }
      rawDatacols.forEach((col, i) => {
        const key = col.dispcolnm || col.querycolnm
        if (!next[key]) {
          next[key] = {
            order:      i,
            enabled:    'y',
            bgcolor:    '#ffffff',
            color:      '#000000',
            align:      col.datatypecd === 'I' ? 'right' : 'left',
            fontweight: 'normal',
            fontsize:   14,
            width:      100,
            ...(col.measureyn ? { measureyn: 'y', unityn: 'y', decimal: 0 } : {}),
          }
        }
      })
      return next
    })
  }, [rawDatacols])

  // coljson에서 order가 있으면 그 순서로 colOrder 세팅
  useEffect(() => {
    if (!rawDatacols.length || !Object.keys(coljson).length) return
    const sorted = rawDatacols
      .map((c) => c.dispcolnm || c.querycolnm)
      .sort((a, b) => (coljson[a]?.order ?? 999) - (coljson[b]?.order ?? 999))
    setColOrder(sorted)
  }, [coljson, rawDatacols])

  const updateTablejson = (key, val) => setTablejson((p) => ({ ...p, [key]: val }))
  const updateColjson   = (colKey, field, val) =>
    setColjson((p) => ({ ...p, [colKey]: { ...(p[colKey] || {}), [field]: val } }))

  const moveRow = (idx, dir) => {
    setColOrder((prev) => {
      const next = [...prev]
      const swap = idx + dir
      if (swap < 0 || swap >= next.length) return prev
      ;[next[idx], next[swap]] = [next[swap], next[idx]]
      return next
    })
  }

  const handleApplyAll = () => {
    setColjson((prev) => {
      const next = { ...prev }
      Object.keys(next).forEach((k) => {
        next[k] = { ...next[k], bgcolor: defBg, color: defColor, fontsize: defFontsize, width: defWidth }
      })
      return next
    })
  }

  const buildFinalColjson = () => {
    const result = {}
    colOrder.forEach((key, i) => {
      result[key] = { ...(coljson[key] || {}), order: i }
    })
    return result
  }

  const buildFinalTablejson = () => ({
    ...tablejson,
    sort: [1, 2, 3]
      .map((i) => ({ column: tablejson[`sort_col_${i}`] || '', direction: tablejson[`sort_dir_${i}`] || 'asc' }))
      .filter((s) => s.column),
  })

  const handleSave = () => {
    if (!selectedDatauid || !chapteruid || !objectnm || !objectuid) {
      message.warning('데이터를 선택해주세요.')
      return
    }
    saveTable.mutate({
      objectuid, chapteruid, objectnm,
      datauid:   selectedDatauid,
      tablejson: buildFinalTablejson(),
      coljson:   buildFinalColjson(),
    })
  }

  const handleDelete = () => {
    if (!window.confirm('정말 삭제하시겠습니까?')) return
    deleteTable.mutate({ chapteruid, objectnm })
    setSelectedDatauid('')
    setColjson({})
    setColOrder([])
  }

  const handleReset = () => {
    const url = new URL(window.location.href)
    url.searchParams.delete('datauid')
    window.location.href = url.toString()
  }

  const handlePreview = async () => {
    if (!selectedDatauid) { message.warning('데이터를 선택해주세요.'); return }
    setPreviewLoading(true)
    try {
      const resp = await apiClient.post('/tables/preview', {
        selected_datauid: selectedDatauid,
        tablejson: buildFinalTablejson(),
        coljson:   buildFinalColjson(),
      })
      setPreviewHtml(resp.data.preview_html || '')
      setPreviewOpen(true)
    } catch (e) {
      message.error('미리보기 실패: ' + (e.response?.data?.detail || e.message))
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleBack = () => {
    const ct = sessionStorage.getItem('chapter_template_chapteruid')
    const co = sessionStorage.getItem('chapter_objects_read_genchapteruid')
    if (ct) navigate(`/master/chapters?chapteruid=${ct}`)
    else if (co) navigate(`/req/chapter-objects?genchapteruid=${co}`)
    else if (chapteruid && objectuid) navigate(`/master/object?chapteruid=${chapteruid}&objectuid=${objectuid}`)
    else if (chapteruid) navigate(`/master/object?chapteruid=${chapteruid}`)
    else navigate('/master/object')
  }

  const tdStyle = { border: '1px solid #ddd', padding: '4px 6px', textAlign: 'center', verticalAlign: 'middle' }
  const thStyle = { ...tdStyle, backgroundColor: '#f5f5f5', fontWeight: 'bold', whiteSpace: 'nowrap' }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 200px)', overflow: 'hidden' }}>

      {/* 헤더 */}
      <div className="page-title" style={{ flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>테이블 관리 - {objectnm}{chapternm ? `(${chapternm})` : ''}</div>
        </div>
        <button type="button" className="icon-btn" onClick={handleBack}>
          <img src="/icons/back.svg" alt="뒤로가기" className="icon-img config-icon" />
        </button>
      </div>

      {/* 3열 */}
      <div style={{ flex: 1, display: 'flex', gap: 16, overflow: 'hidden', minHeight: 0, paddingRight: 10 }}>

        {/* 영역1: 데이터 목록 */}
        <div style={{ flex: '0 0 13%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <h4 style={{ flexShrink: 0, marginBottom: 8 }}>데이터 목록</h4>
          <div className="chapter-card-container" style={{ flex: 1, overflowY: 'auto' }}>
            {datasLoading ? (
              <div style={{ fontSize: 12, color: '#aaa', padding: 8 }}>로딩 중...</div>
            ) : allDatas.length === 0 ? (
              <div style={{ fontSize: 12, color: '#aaa', padding: 8 }}>데이터가 없습니다.</div>
            ) : allDatas.map((d) => (
              <div
                key={d.datauid}
                className={`chapter-card${selectedDatauid === d.datauid ? ' selected' : ''}`}
                onClick={() => setSelectedDatauid(d.datauid)}
              >
                <div className="card-title">{d.datanm}</div>
              </div>
            ))}
          </div>
        </div>

        {/* 영역2: 머리글 설정 + 정렬 */}
        <div style={{ flex: '0 0 18%', display: 'flex', flexDirection: 'column', minHeight: 0, overflowY: 'auto', paddingLeft: 8 }}>
          <h4 style={{ flexShrink: 0, marginBottom: 8 }}>머리글 설정</h4>

          <div className="form-group-left" style={{ display: 'block' }}>
            <label>사용:</label>
            <input type="checkbox" style={{ marginLeft: 30 }}
              checked={tablejson.row_visible !== false && tablejson.row_visible !== 'n'}
              onChange={(e) => updateTablejson('row_visible', e.target.checked)} />
          </div>
          <div className="form-group-left">
            <label style={{ minWidth: 70 }}>채우기 색:</label>
            <input type="color" value={tablejson.row_bgcolor}
              onChange={(e) => updateTablejson('row_bgcolor', e.target.value)} />
          </div>
          <div className="form-group-left">
            <label style={{ minWidth: 70 }}>글꼴 색:</label>
            <input type="color" value={tablejson.row_color}
              onChange={(e) => updateTablejson('row_color', e.target.value)} />
          </div>
          <div className="form-group-left">
            <label style={{ minWidth: 70 }}>맞춤:</label>
            <select value={tablejson.row_align} onChange={(e) => updateTablejson('row_align', e.target.value)} style={{ flex: 1 }}>
              <option value="left">좌측</option>
              <option value="center">중앙</option>
              <option value="right">우측</option>
            </select>
          </div>
          <div className="form-group-left" style={{ display: 'block' }}>
            <label>굵게:</label>
            <input type="checkbox" style={{ marginLeft: 30 }}
              checked={tablejson.row_fontweight === 'bold'}
              onChange={(e) => updateTablejson('row_fontweight', e.target.checked ? 'bold' : 'normal')} />
          </div>
          <div className="form-group-left">
            <label style={{ minWidth: 70 }}>글꼴크기:</label>
            <input type="number" min={8} max={72} value={tablejson.row_fontsize} style={{ width: 60 }}
              onChange={(e) => updateTablejson('row_fontsize', Number(e.target.value))} />
          </div>
          <div className="form-group-left">
            <label style={{ minWidth: 70 }}>테두리색:</label>
            <input type="color" value={tablejson.row_bordercolor}
              onChange={(e) => updateTablejson('row_bordercolor', e.target.value)} />
          </div>

          {/* 정렬 옵션 */}
          <div style={{ marginTop: 20 }}>
            {[1, 2, 3].map((i) => (
              <div key={i} className="form-group-left" style={{ marginBottom: 6 }}>
                <label style={{ minWidth: 50 }}>정렬 {i}:</label>
                <select
                  value={tablejson[`sort_col_${i}`] || ''}
                  onChange={(e) => updateTablejson(`sort_col_${i}`, e.target.value)}
                  style={{ flex: 0.7 }}
                >
                  <option value="">-- 선택 --</option>
                  {colOrder.map((col) => <option key={col} value={col}>{col}</option>)}
                </select>
                <select
                  value={tablejson[`sort_dir_${i}`] || 'asc'}
                  onChange={(e) => updateTablejson(`sort_dir_${i}`, e.target.value)}
                  style={{ flex: 0.3, marginLeft: 4 }}
                >
                  <option value="asc">ASC</option>
                  <option value="desc">DESC</option>
                </select>
              </div>
            ))}
          </div>
        </div>

        {/* 영역3: 값 설정 */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, paddingLeft: 8 }}>
          <h4 style={{ flexShrink: 0, marginBottom: 8 }}>값 설정</h4>

          <div style={{ flex: 1, overflowY: 'auto' }}>
            {/* 기본값 행 */}
            <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12, tableLayout: 'fixed', marginBottom: 12 }}>
              <thead>
                <tr>
                  <th style={{ ...thStyle, width: '14%' }}>컬럼명</th>
                  <th style={{ ...thStyle, width: '5%' }}>사용</th>
                  <th style={{ ...thStyle, width: '8%' }}>채우기</th>
                  <th style={{ ...thStyle, width: '8%' }}>글꼴 색</th>
                  <th style={{ ...thStyle, width: '8%' }}>맞춤</th>
                  <th style={{ ...thStyle, width: '5%' }}>굵게</th>
                  <th style={{ ...thStyle, width: '7%' }}>크기</th>
                  <th style={{ ...thStyle, width: '9%' }}>너비(px)</th>
                  <th style={{ ...thStyle, width: '6%' }}>쉼표</th>
                  <th style={{ ...thStyle, width: '9%' }}>소수점</th>
                  <th style={{ ...thStyle, width: '11%' }}>적용</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={tdStyle}>기본값</td>
                  <td style={tdStyle} />
                  <td style={tdStyle}><input type="color" value={defBg} onChange={(e) => setDefBg(e.target.value)} style={{ width: '100%' }} /></td>
                  <td style={tdStyle}><input type="color" value={defColor} onChange={(e) => setDefColor(e.target.value)} style={{ width: '100%' }} /></td>
                  <td style={tdStyle} />
                  <td style={tdStyle} />
                  <td style={tdStyle}><input type="number" min={8} max={72} value={defFontsize} style={{ width: '100%' }} onChange={(e) => setDefFontsize(Number(e.target.value))} /></td>
                  <td style={tdStyle}><input type="number" min={1} max={2000} value={defWidth} style={{ width: '100%' }} onChange={(e) => setDefWidth(Number(e.target.value))} /></td>
                  <td style={tdStyle} />
                  <td style={tdStyle} />
                  <td style={tdStyle}>
                    <button type="button" className="icon-btn" onClick={handleApplyAll}>
                      <img src="/icons/apply.svg" className="icon-img config-icon" alt="적용" />
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>

            {/* 컬럼별 설정 */}
            {colOrder.length > 0 && (
              <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12, tableLayout: 'fixed' }}>
                <thead>
                  <tr>
                    <th style={{ ...thStyle, width: '14%' }}>컬럼명</th>
                    <th style={{ ...thStyle, width: '5%' }}>사용</th>
                    <th style={{ ...thStyle, width: '8%' }}>채우기</th>
                    <th style={{ ...thStyle, width: '8%' }}>글꼴 색</th>
                    <th style={{ ...thStyle, width: '8%' }}>맞춤</th>
                    <th style={{ ...thStyle, width: '5%' }}>굵게</th>
                    <th style={{ ...thStyle, width: '7%' }}>크기</th>
                    <th style={{ ...thStyle, width: '9%' }}>너비(px)</th>
                    <th style={{ ...thStyle, width: '6%' }}>쉼표</th>
                    <th style={{ ...thStyle, width: '9%' }}>소수점</th>
                    <th style={{ ...thStyle, width: '11%' }}>이동</th>
                  </tr>
                </thead>
                <tbody>
                  {colOrder.map((colKey, idx) => {
                    const cf = coljson[colKey] || {}
                    const hasMeasure = cf.measureyn === 'y'
                    return (
                      <tr key={colKey}>
                        <td style={{ ...tdStyle, textAlign: 'left' }}>{colKey}</td>
                        <td style={tdStyle}>
                          <input type="checkbox" checked={cf.enabled !== 'n'}
                            onChange={(e) => updateColjson(colKey, 'enabled', e.target.checked ? 'y' : 'n')} />
                        </td>
                        <td style={tdStyle}>
                          <input type="color" value={cf.bgcolor || '#ffffff'} style={{ width: '100%' }}
                            onChange={(e) => updateColjson(colKey, 'bgcolor', e.target.value)} />
                        </td>
                        <td style={tdStyle}>
                          <input type="color" value={cf.color || '#000000'} style={{ width: '100%' }}
                            onChange={(e) => updateColjson(colKey, 'color', e.target.value)} />
                        </td>
                        <td style={tdStyle}>
                          <select value={cf.align || 'left'} style={{ width: '100%' }}
                            onChange={(e) => updateColjson(colKey, 'align', e.target.value)}>
                            {ALIGN_OPTIONS.map((a) => <option key={a} value={a}>{a === 'left' ? '좌측' : a === 'center' ? '중앙' : '우측'}</option>)}
                          </select>
                        </td>
                        <td style={tdStyle}>
                          <input type="checkbox" checked={cf.fontweight === 'bold'}
                            onChange={(e) => updateColjson(colKey, 'fontweight', e.target.checked ? 'bold' : 'normal')} />
                        </td>
                        <td style={tdStyle}>
                          <input type="number" min={8} max={72} value={cf.fontsize || 14} style={{ width: '100%' }}
                            onChange={(e) => updateColjson(colKey, 'fontsize', Number(e.target.value))} />
                        </td>
                        <td style={tdStyle}>
                          <input type="number" min={50} max={2000} value={cf.width || 100} style={{ width: '100%' }}
                            onChange={(e) => updateColjson(colKey, 'width', Number(e.target.value))} />
                        </td>
                        <td style={tdStyle}>
                          {hasMeasure
                            ? <input type="checkbox" checked={cf.unityn === 'y'}
                                onChange={(e) => updateColjson(colKey, 'unityn', e.target.checked ? 'y' : 'n')} />
                            : <span>-</span>}
                        </td>
                        <td style={tdStyle}>
                          {hasMeasure
                            ? <input type="number" min={0} max={10} value={cf.decimal || 0} style={{ width: '100%' }}
                                onChange={(e) => updateColjson(colKey, 'decimal', Number(e.target.value))} />
                            : <span>-</span>}
                        </td>
                        <td style={tdStyle}>
                          <button type="button" className="icon-btn" onClick={() => moveRow(idx, -1)} disabled={idx === 0}>
                            <img src="/icons/up.svg" className="icon-img-tbl config-icon" alt="위로" />
                          </button>
                          <button type="button" className="icon-btn" onClick={() => moveRow(idx, 1)} disabled={idx === colOrder.length - 1}>
                            <img src="/icons/down.svg" className="icon-img-tbl config-icon" alt="아래로" />
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>

          {/* 버튼 */}
          {selectedDatauid && (
            <div className="button-group" style={{ flexShrink: 0, marginTop: 8 }}>
              <button type="button" className="icon-btn" onClick={handleReset}>
                <div className="icon-wrapper">
                  <img src="/icons/new.svg" className="icon-img new-icon" alt="신규" />
                  <span className="icon-label">신규</span>
                </div>
              </button>
              <button type="button" className="icon-btn" onClick={handleSave} disabled={saveTable.isPending}>
                <div className="icon-wrapper">
                  <img src="/icons/save.svg" className="icon-img save-icon" alt="저장" />
                  <span className="icon-label">저장</span>
                </div>
              </button>
              <button type="button" className="icon-btn" onClick={handleDelete} disabled={deleteTable.isPending}>
                <div className="icon-wrapper">
                  <img src="/icons/delete.svg" className="icon-img del-icon" alt="삭제" />
                  <span className="icon-label">삭제</span>
                </div>
              </button>
              <button type="button" className="icon-btn" onClick={handlePreview} disabled={previewLoading}>
                <div className="icon-wrapper">
                  <img src="/icons/view.svg" className="icon-img config-icon" alt="미리보기" />
                  <span className="icon-label">미리보기</span>
                </div>
              </button>
            </div>
          )}
        </div>

      </div>

      {/* 미리보기 모달 */}
      {previewOpen && (
        <div style={{
          position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
          background: 'rgba(0,0,0,0.5)', display: 'flex',
          justifyContent: 'center', alignItems: 'center', zIndex: 9999,
        }}>
          <div style={{
            background: '#fff', borderRadius: 8, padding: 24,
            width: '80%', maxHeight: '80vh',
            display: 'flex', flexDirection: 'column',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>미리보기 결과</h3>
              <button type="button" onClick={() => setPreviewOpen(false)} style={{ fontSize: 20, background: 'none', border: 'none', cursor: 'pointer' }}>×</button>
            </div>
            <p style={{ fontSize: 12, color: '#888', marginBottom: 8 }}>* 미리보기 결과는 15개의 행만 보입니다.</p>
            <div style={{ flex: 1, overflowY: 'auto' }}
              dangerouslySetInnerHTML={{ __html: previewHtml }}
            />
          </div>
        </div>
      )}

    </div>
  )
}
