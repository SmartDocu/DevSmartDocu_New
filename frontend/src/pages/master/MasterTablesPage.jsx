/**
 * MasterTablesPage — UI 테이블 설정
 * Django master_tables.html 구조 그대로 반영
 * 3열: 데이터 목록 | 머리글 설정+정렬 | 값 설정(컬럼별)  + 미리보기 모달
 */
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { App } from 'antd'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useChapterDatas, useDatacols } from '@/hooks/useDatas'
import { useTable, useSaveTable, useDeleteTable, useObjectFilterDatauid } from '@/hooks/useTables'

const ALIGN_OPTIONS = ['left', 'center', 'right']

export default function MasterTablesPage() {
  useLangStore((s) => s.translations)
  const { message } = App.useApp()
  const [searchParams] = useSearchParams()
  const chapteruid = searchParams.get('chapteruid') || ''
  const objectnm   = searchParams.get('objectnm')   || ''
  const objectuid  = searchParams.get('objectuid')  || ''
  const chapternm  = searchParams.get('chapternm')  || ''
  const user  = useAuthStore((s) => s.user)
  const docnm = user?.docnm
  const isEditYn = user?.editbuttonyn === 'Y'

  const { data: allDatas = [], isLoading: datasLoading } = useChapterDatas(chapteruid)
  const { data: tableData, isSuccess: tableSuccess } = useTable(chapteruid, objectnm)
  const saveTable   = useSaveTable()
  const deleteTable = useDeleteTable()

  const { data: filterDatauid } = useObjectFilterDatauid(objectuid, tableSuccess && tableData === null)

  const [selectedDatauid, setSelectedDatauid] = useState('')
  const [isFilterDefault, setIsFilterDefault] = useState(false)
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

  // tables 저장 없을 때 objectfilters.objectdatauid 로 기본 데이터 선택
  useEffect(() => {
    if (!filterDatauid) return
    setSelectedDatauid(filterDatauid)
    setIsFilterDefault(true)
  }, [filterDatauid])

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
      message.warning(t('msg.select.data'))
      return
    }
    saveTable.mutate(
      {
        objectuid, chapteruid, objectnm,
        datauid:   selectedDatauid,
        tablejson: buildFinalTablejson(),
        coljson:   buildFinalColjson(),
      },
      {
        onSuccess: () => message.success(t('msg.save.success')),
        onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
      }
    )
  }

  const handleDelete = () => {
    if (!window.confirm(t('msg.confirm.delete'))) return
    deleteTable.mutate(
      { chapteruid, objectnm },
      {
        onSuccess: () => {
          message.success(t('msg.delete.success'))
          setSelectedDatauid('')
          setColjson({})
          setColOrder([])
        },
        onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
      }
    )
  }

  const handleReset = () => {
    const url = new URL(window.location.href)
    url.searchParams.delete('datauid')
    window.location.href = url.toString()
  }

  const handlePreview = async () => {
    if (!selectedDatauid) { message.warning(t('msg.select.data')); return }
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
      message.error(t('msg.preview.error') + ': ' + (e.response?.data?.detail || e.message))
    } finally {
      setPreviewLoading(false)
    }
  }

  const tdCenter = { textAlign: 'center' }

  return (
    <div>

      {/* 헤더 */}
      <div className="page-title" style={{ marginBottom: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.table.manage')}{docnm ? ` - ${docnm}` : ''}</div>
        </div>
      </div>
      <div style={{ marginBottom: 16, paddingLeft: 16, fontSize: 15, fontWeight: 500, color: 'var(--gray-700)' }}>
        {chapternm && <span>{t('lbl.chapternm')}: {chapternm}</span>}
        {chapternm && objectnm && <span style={{ margin: '0 14px', color: '#d9d9d9' }}>|</span>}
        {objectnm && <span>{t('lbl.objectnm_lbl')}: {objectnm}</span>}
      </div>
      {isFilterDefault && (
        <div style={{ marginBottom: 12, padding: '8px 14px', background: '#fff7e6', border: '1px solid #ffd591', borderRadius: 6, color: '#d46b08', fontSize: 13 }}>
          {t('msg.dataset.filter.readonly')}
        </div>
      )}

      {/* 3열 */}
      <div style={{ display: 'flex', gap: 20, paddingRight: 10 }}>

        {/* 영역1: 데이터 목록 */}
        <div style={{ flex: 2 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.data.list')}</h3>
            <div />
          </div>
          <div className="chapter-card-container" style={{ overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
            {datasLoading ? (
              <div style={{ fontSize: 12, color: '#aaa', padding: 8 }}>{t('msg.loading')}</div>
            ) : allDatas.length === 0 ? (
              <div style={{ fontSize: 12, color: '#aaa', padding: 8 }}>{t('msg.no.data')}</div>
            ) : allDatas.map((d) => (
              <div
                key={d.datauid}
                className={`chapter-card${selectedDatauid === d.datauid ? ' selected' : ''}`}
                onClick={() => { if (!isFilterDefault) setSelectedDatauid(d.datauid) }}
                style={isFilterDefault ? { cursor: 'not-allowed', opacity: 0.6 } : {}}
              >
                <div className="card-title">{d.datanm}</div>
              </div>
            ))}
          </div>
        </div>

        {/* 영역2: 머리글 설정 + 정렬 */}
        <div style={{ flex: 3, paddingLeft: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.header.settings')}</h3>
            <div />
          </div>
          <div style={{ overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
            <div className="form-group-left">
              <label style={{ minWidth: 70 }}>{t('lbl.useyn_lbl')}:</label>
              <input type="checkbox" style={{ flex: '0 0 auto' }}
                checked={tablejson.row_visible !== false && tablejson.row_visible !== 'n'}
                onChange={(e) => updateTablejson('row_visible', e.target.checked)} />
            </div>
            <div className="form-group-left">
              <label style={{ minWidth: 70 }}>{t('lbl.bgcolor')}:</label>
              <input type="color" value={tablejson.row_bgcolor}
                onChange={(e) => updateTablejson('row_bgcolor', e.target.value)} />
            </div>
            <div className="form-group-left">
              <label style={{ minWidth: 70 }}>{t('lbl.fontcolor')}:</label>
              <input type="color" value={tablejson.row_color}
                onChange={(e) => updateTablejson('row_color', e.target.value)} />
            </div>
            <div className="form-group-left">
              <label style={{ minWidth: 70 }}>{t('lbl.align')}:</label>
              <select value={tablejson.row_align} onChange={(e) => updateTablejson('row_align', e.target.value)} style={{ flex: 1 }}>
                <option value="left">{t('cod.align_left')}</option>
                <option value="center">{t('cod.align_center')}</option>
                <option value="right">{t('cod.align_right')}</option>
              </select>
            </div>
            <div className="form-group-left">
              <label style={{ minWidth: 70 }}>{t('lbl.bold')}:</label>
              <input type="checkbox" style={{ flex: '0 0 auto' }}
                checked={tablejson.row_fontweight === 'bold'}
                onChange={(e) => updateTablejson('row_fontweight', e.target.checked ? 'bold' : 'normal')} />
            </div>
            <div className="form-group-left">
              <label style={{ minWidth: 70 }}>{t('lbl.fontsize')}:</label>
              <input type="number" min={8} max={72} value={tablejson.row_fontsize} style={{ width: 60 }}
                onChange={(e) => updateTablejson('row_fontsize', Number(e.target.value))} />
            </div>
            <div className="form-group-left">
              <label style={{ minWidth: 70 }}>{t('lbl.bordercolor')}:</label>
              <input type="color" value={tablejson.row_bordercolor}
                onChange={(e) => updateTablejson('row_bordercolor', e.target.value)} />
            </div>

            {/* 정렬 옵션 */}
            <div style={{ marginTop: 20 }}>
              {[1, 2, 3].map((i) => (
                <div key={i} className="form-group-left" style={{ marginBottom: 6 }}>
                  <label style={{ minWidth: 50 }}>{t('lbl.sort')} {i}:</label>
                  <select
                    value={tablejson[`sort_col_${i}`] || ''}
                    onChange={(e) => updateTablejson(`sort_col_${i}`, e.target.value)}
                    style={{ flex: 0.7 }}
                  >
                    <option value="">{t('msg.select.placeholder')}</option>
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
        </div>

        {/* 영역3: 값 설정 */}
        <div style={{ flex: 10, paddingLeft: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.value.settings')}</h3>
            {selectedDatauid && (
              <div style={{ display: 'flex', gap: 8 }}>
                <button type="button" className="btn btn-primary" onClick={handleReset}>{t('btn.new')}</button>
                {isEditYn && (
                  <>
                    <button type="button" className="btn btn-primary" onClick={handleSave} disabled={saveTable.isPending}>{t('btn.save')}</button>
                    <button type="button" className="btn btn-danger" onClick={handleDelete} disabled={deleteTable.isPending}>{t('btn.delete')}</button>
                  </>
                )}
                <button type="button" className="btn btn-primary" onClick={handlePreview} disabled={previewLoading}>{t('btn.preview_btn')}</button>
              </div>
            )}
          </div>

          <div style={{ overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
            {/* 기본값 행 */}
            <table style={{ fontSize: 12, tableLayout: 'fixed', marginBottom: 12 }}>
              <thead>
                <tr>
                  <th style={{ width: '14%' }}>{t('thd.colnm')}</th>
                  <th style={{ width: '5%' }}>{t('thd.useyn_thd')}</th>
                  <th style={{ width: '8%' }}>{t('thd.bgcolor_thd')}</th>
                  <th style={{ width: '8%' }}>{t('thd.fontcolor_thd')}</th>
                  <th style={{ width: '8%' }}>{t('thd.align_thd')}</th>
                  <th style={{ width: '5%' }}>{t('thd.bold_thd')}</th>
                  <th style={{ width: '7%' }}>{t('thd.fontsize_thd')}</th>
                  <th style={{ width: '9%' }}>{t('thd.width_px')}</th>
                  <th style={{ width: '6%' }}>{t('thd.comma')}</th>
                  <th style={{ width: '9%' }}>{t('thd.decimal')}</th>
                  <th style={{ width: '11%' }}>{t('btn.apply')}</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{t('lbl.default_name_lbl')}</td>
                  <td />
                  <td style={tdCenter}><input type="color" value={defBg} onChange={(e) => setDefBg(e.target.value)} style={{ width: '100%' }} /></td>
                  <td style={tdCenter}><input type="color" value={defColor} onChange={(e) => setDefColor(e.target.value)} style={{ width: '100%' }} /></td>
                  <td />
                  <td />
                  <td style={tdCenter}><input type="number" min={8} max={72} value={defFontsize} style={{ width: '100%' }} onChange={(e) => setDefFontsize(Number(e.target.value))} /></td>
                  <td style={tdCenter}><input type="number" min={1} max={2000} value={defWidth} style={{ width: '100%' }} onChange={(e) => setDefWidth(Number(e.target.value))} /></td>
                  <td />
                  <td />
                  <td style={tdCenter}>
                    <button type="button" className="btn btn-primary" style={{ padding: '2px 8px', fontSize: 11 }} onClick={handleApplyAll}>{t('btn.apply')}</button>
                  </td>
                </tr>
              </tbody>
            </table>

            {/* 컬럼별 설정 */}
            {colOrder.length > 0 && (
              <table style={{ fontSize: 12, tableLayout: 'fixed' }}>
                <thead>
                  <tr>
                    <th style={{ width: '14%' }}>{t('thd.colnm')}</th>
                    <th style={{ width: '5%' }}>{t('thd.useyn_thd')}</th>
                    <th style={{ width: '8%' }}>{t('thd.bgcolor_thd')}</th>
                    <th style={{ width: '8%' }}>{t('thd.fontcolor_thd')}</th>
                    <th style={{ width: '8%' }}>{t('thd.align_thd')}</th>
                    <th style={{ width: '5%' }}>{t('thd.bold_thd')}</th>
                    <th style={{ width: '7%' }}>{t('thd.fontsize_thd')}</th>
                    <th style={{ width: '9%' }}>{t('thd.width_px')}</th>
                    <th style={{ width: '6%' }}>{t('thd.comma')}</th>
                    <th style={{ width: '9%' }}>{t('thd.decimal')}</th>
                    <th style={{ width: '11%' }}>{t('thd.move')}</th>
                  </tr>
                </thead>
                <tbody>
                  {colOrder.map((colKey, idx) => {
                    const cf = coljson[colKey] || {}
                    const hasMeasure = cf.measureyn === 'y'
                    return (
                      <tr key={colKey}>
                        <td>{colKey}</td>
                        <td style={tdCenter}>
                          <input type="checkbox" checked={cf.enabled !== 'n'}
                            onChange={(e) => updateColjson(colKey, 'enabled', e.target.checked ? 'y' : 'n')} />
                        </td>
                        <td style={tdCenter}>
                          <input type="color" value={cf.bgcolor || '#ffffff'} style={{ width: '100%' }}
                            onChange={(e) => updateColjson(colKey, 'bgcolor', e.target.value)} />
                        </td>
                        <td style={tdCenter}>
                          <input type="color" value={cf.color || '#000000'} style={{ width: '100%' }}
                            onChange={(e) => updateColjson(colKey, 'color', e.target.value)} />
                        </td>
                        <td style={tdCenter}>
                          <select value={cf.align || 'left'} style={{ width: '100%' }}
                            onChange={(e) => updateColjson(colKey, 'align', e.target.value)}>
                            {ALIGN_OPTIONS.map((a) => <option key={a} value={a}>{a === 'left' ? t('cod.align_left') : a === 'center' ? t('cod.align_center') : t('cod.align_right')}</option>)}
                          </select>
                        </td>
                        <td style={tdCenter}>
                          <input type="checkbox" checked={cf.fontweight === 'bold'}
                            onChange={(e) => updateColjson(colKey, 'fontweight', e.target.checked ? 'bold' : 'normal')} />
                        </td>
                        <td style={tdCenter}>
                          <input type="number" min={8} max={72} value={cf.fontsize || 14} style={{ width: '100%' }}
                            onChange={(e) => updateColjson(colKey, 'fontsize', Number(e.target.value))} />
                        </td>
                        <td style={tdCenter}>
                          <input type="number" min={50} max={2000} value={cf.width || 100} style={{ width: '100%' }}
                            onChange={(e) => updateColjson(colKey, 'width', Number(e.target.value))} />
                        </td>
                        <td style={tdCenter}>
                          {hasMeasure
                            ? <input type="checkbox" checked={cf.unityn === 'y'}
                                onChange={(e) => updateColjson(colKey, 'unityn', e.target.checked ? 'y' : 'n')} />
                            : <span>-</span>}
                        </td>
                        <td style={tdCenter}>
                          {hasMeasure
                            ? <input type="number" min={0} max={10} value={cf.decimal || 0} style={{ width: '100%' }}
                                onChange={(e) => updateColjson(colKey, 'decimal', Number(e.target.value))} />
                            : <span>-</span>}
                        </td>
                        <td style={tdCenter}>
                          <button type="button" className="btn btn-primary" style={{ padding: '2px 6px', fontSize: 11, marginRight: 2 }} onClick={() => moveRow(idx, -1)} disabled={idx === 0}>↑</button>
                          <button type="button" className="btn btn-primary" style={{ padding: '2px 6px', fontSize: 11 }} onClick={() => moveRow(idx, 1)} disabled={idx === colOrder.length - 1}>↓</button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>

      </div>

      {/* 미리보기 모달 */}
      {previewOpen && (
        <div style={{
          position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
          background: 'rgba(0,0,0,0.6)', display: 'flex',
          justifyContent: 'center', alignItems: 'flex-start',
          overflowY: 'auto', zIndex: 9999, padding: '40px 0',
        }}
          onClick={(e) => { if (e.target === e.currentTarget) setPreviewOpen(false) }}
        >
          <div style={{
            background: '#fff',
            width: 794,
            minHeight: 1123,
            padding: '40px 60px',
            boxShadow: '0 4px 32px rgba(0,0,0,0.35)',
            flexShrink: 0,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h3 style={{ margin: 0 }}>{t('ttl.preview_ttl')}</h3>
              <button type="button" onClick={() => setPreviewOpen(false)} style={{ fontSize: 20, background: 'none', border: 'none', cursor: 'pointer' }}>×</button>
            </div>
            <p style={{ fontSize: 12, color: '#888', marginBottom: 12 }}>* {t('inf.preview.rows')}</p>
            <div dangerouslySetInnerHTML={{ __html: previewHtml }} />
          </div>
        </div>
      )}

    </div>
  )
}
