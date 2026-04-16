/**
 * MasterChartsPage — UI 차트 설정
 * Django master_charts.html 구조 그대로 반영
 * 3열: 데이터 목록 | 차트 유형 | 차트 설정  + 미리보기
 */
import { useEffect, useRef, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { App, Spin } from 'antd'
import apiClient from '@/api/client'
import { useChapterDatas } from '@/hooks/useDatas'
import { useChart, useSaveChart, useDeleteChart } from '@/hooks/useCharts'

const COLOR_PALETTE_OPTIONS = [
  { value: 'pastel', label: '파스텔' },
  { value: 'bold', label: '진한색' },
  { value: 'earth', label: '어스' },
  { value: 'ocean', label: '오션' },
  { value: 'sunset', label: '선셋' },
]

export default function MasterChartsPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const chapteruid = searchParams.get('chapteruid') || ''
  const objectnm   = searchParams.get('objectnm')   || ''
  const objectuid  = searchParams.get('objectuid')  || ''
  const chapternm  = searchParams.get('chapternm')  || ''

  // ── 데이터 ─────────────────────────────────────────────────────────────────
  const { data: allDatas = [], isLoading: datasLoading } = useChapterDatas(chapteruid)
  const { data: chartData }     = useChart(chapteruid, objectnm)
  const saveChart   = useSaveChart()
  const deleteChart = useDeleteChart()

  // ── 차트 타입 상세 ──────────────────────────────────────────────────────────
  const [chartTypesDetail, setChartTypesDetail] = useState([])
  useEffect(() => {
    apiClient.get('/charts/types/detail')
      .then((r) => setChartTypesDetail(r.data.chart_types || []))
      .catch(() => {})
  }, [])

  // ── 선택 상태 ───────────────────────────────────────────────────────────────
  const [selectedDatauid,  setSelectedDatauid]  = useState('')
  const [selectedChartType, setSelectedChartType] = useState('')
  const [chartConfig, setChartConfig]  = useState({})
  const [chartWidth,  setChartWidth]   = useState(500)
  const [chartHeight, setChartHeight]  = useState(250)

  // ── datacols (X/Y 필드 옵션) ────────────────────────────────────────────────
  const [datacols, setDatacols] = useState([])
  useEffect(() => {
    if (!selectedDatauid) { setDatacols([]); return }
    apiClient.get('/datas/datacols', { params: { datauid: selectedDatauid } })
      .then((r) => setDatacols(r.data.columns || []))
      .catch(() => setDatacols([]))
  }, [selectedDatauid])

  // ── 미리보기 ────────────────────────────────────────────────────────────────
  const [previewUrl,     setPreviewUrl]     = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  // ── 기존 설정 로드 ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!chartData) return
    if (chartData.datauid)     setSelectedDatauid(chartData.datauid)
    if (chartData.displaytype) setSelectedChartType(chartData.displaytype)
    if (chartData.chart_width) setChartWidth(chartData.chart_width)
    if (chartData.chart_height) setChartHeight(chartData.chart_height)
    if (chartData.chartjson && Object.keys(chartData.chartjson).length)
      setChartConfig(chartData.chartjson)
  }, [chartData])

  // ── 현재 선택된 차트 타입의 properties ─────────────────────────────────────
  const selectedTypeDetail = chartTypesDetail.find((t) => t.code === selectedChartType)
  const properties = selectedTypeDetail?.properties || []

  const categoryFields = datacols.filter((c) => !c.measureyn).map((c) => c.dispcolnm || c.querycolnm)
  const numericFields  = datacols.filter((c) => c.measureyn).map((c) => c.dispcolnm || c.querycolnm)
  const allFields      = datacols.map((c) => c.dispcolnm || c.querycolnm)

  const getFieldOptions = (field) => {
    if (field.fieldFilter === 'category') return categoryFields
    if (field.fieldFilter === 'numeric')  return numericFields
    if (field.options) return field.options
    return allFields
  }

  // ── 핸들러 ─────────────────────────────────────────────────────────────────
  const handleDataSelect = (datauid) => {
    setSelectedDatauid(datauid)
    setChartConfig({})
    setPreviewUrl(null)
  }

  const handleChartTypeSelect = (code) => {
    setSelectedChartType(code)
    setChartConfig({})
    setPreviewUrl(null)
  }

  const handleReset = () => {
    setSelectedDatauid('')
    setSelectedChartType('')
    setChartConfig({})
    setChartWidth(500)
    setChartHeight(250)
    setPreviewUrl(null)
  }

  const handleSave = () => {
    if (!selectedDatauid || !selectedChartType || !chapteruid || !objectnm || !objectuid) {
      message.warning('데이터, 차트 유형을 모두 선택해주세요.')
      return
    }
    saveChart.mutate({
      objectuid, chapteruid, objectnm,
      datauid: selectedDatauid,
      displaytype: selectedChartType,
      chartjson: chartConfig,
      chart_width: chartWidth,
      chart_height: chartHeight,
    })
  }

  const handleDelete = () => {
    if (!window.confirm('정말 삭제하시겠습니까?')) return
    deleteChart.mutate({ chapteruid, objectnm })
    handleReset()
  }

  const handlePreview = async () => {
    if (!selectedDatauid || !selectedChartType) {
      message.warning('데이터, 차트 유형을 모두 선택해주세요.')
      return
    }
    setPreviewLoading(true)
    try {
      const resp = await apiClient.post(
        '/charts/preview',
        {
          chapteruid, objectnm,
          selected_datauid: selectedDatauid,
          selected_chart_type: selectedChartType,
          properties: { ...chartConfig, chart_width: chartWidth, chart_height: chartHeight },
          chart_width: chartWidth,
          chart_height: chartHeight,
        },
        { responseType: 'blob' },
      )
      const url = URL.createObjectURL(new Blob([resp.data], { type: 'image/png' }))
      setPreviewUrl(url)
    } catch (e) {
      message.error('차트 생성 실패: ' + (e.response?.data?.detail || e.message))
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

  const setCfg = (key, val) => setChartConfig((p) => ({ ...p, [key]: val }))

  // ── 렌더 ─────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 200px)', overflow: 'hidden' }}>

      {/* 헤더 */}
      <div className="page-title" style={{ flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>차트 설정 - {objectnm}{chapternm ? `(${chapternm})` : ''}</div>
        </div>
        <button type="button" className="icon-btn" onClick={handleBack}>
          <img src="/icons/back.svg" alt="뒤로가기" className="icon-img config-icon" />
        </button>
      </div>

      {/* 3열 레이아웃 */}
      <div style={{ flex: 1, display: 'flex', gap: 20, overflow: 'hidden', minHeight: 0, paddingRight: 10 }}>

        {/* 영역1: 데이터 목록 */}
        <div style={{ flex: '0 0 15%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
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
                onClick={() => handleDataSelect(d.datauid)}
              >
                <div className="card-title">{d.datanm}</div>
              </div>
            ))}
          </div>
        </div>

        {/* 영역2: 차트 유형 */}
        <div style={{ flex: '0 0 15%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <h4 style={{ flexShrink: 0, marginBottom: 8 }}>차트 유형</h4>
          <div className="chapter-card-container" style={{ flex: 1, overflowY: 'auto' }}>
            {chartTypesDetail.map((t) => (
              <div
                key={t.code}
                className={`chapter-card${selectedChartType === t.code ? ' selected' : ''}`}
                onClick={() => handleChartTypeSelect(t.code)}
              >
                <div className="card-title">{t.name}</div>
              </div>
            ))}
          </div>
        </div>

        {/* 영역3: 차트 설정 */}
        {selectedChartType && (
          <div style={{ flex: '0 0 35%', display: 'flex', flexDirection: 'column', minHeight: 0, overflowY: 'auto' }}>
            <h4 style={{ flexShrink: 0, marginBottom: 4 }}>차트 설정</h4>
            <p style={{ fontSize: 12, color: '#888', flexShrink: 0, marginBottom: 8 }}>* 붉은 글씨는 필수값입니다.</p>

            {/* 차트 크기 */}
            <div className="form-group-left">
              <label style={{ width: 130 }}>차트 크기 :</label>
              <div style={{ display: 'flex', gap: 8, flex: 1 }}>
                <input
                  type="number" placeholder="가로 (px)"
                  value={chartWidth}
                  onChange={(e) => setChartWidth(Number(e.target.value))}
                  style={{ flex: 1 }}
                />
                <input
                  type="number" placeholder="세로 (px)"
                  value={chartHeight}
                  onChange={(e) => setChartHeight(Number(e.target.value))}
                  style={{ flex: 1 }}
                />
              </div>
            </div>

            {/* 동적 필드 */}
            {properties.map((field) => {
              const opts = getFieldOptions(field)
              const labelStyle = field.required
                ? { color: 'red', width: 130, display: 'inline-block' }
                : { width: 130, display: 'inline-block' }

              if (field.type === 'text') return (
                <div key={field.key} className="form-group-left">
                  <label style={labelStyle}>{field.label}</label>
                  <input
                    type="text"
                    value={chartConfig[field.key] || ''}
                    onChange={(e) => setCfg(field.key, e.target.value)}
                    style={{ flex: 1 }}
                  />
                </div>
              )

              if (field.type === 'number') return (
                <div key={field.key} className="form-group-left">
                  <label style={labelStyle}>{field.label}</label>
                  <input
                    type="number"
                    value={chartConfig[field.key] ?? field.default ?? ''}
                    onChange={(e) => setCfg(field.key, Number(e.target.value))}
                    style={{ flex: 1 }}
                  />
                </div>
              )

              if (field.type === 'boolean') return (
                <div key={field.key} className="form-group-left" style={{ display: 'block' }}>
                  <label style={labelStyle}>{field.label}</label>
                  <input
                    type="checkbox"
                    style={{ marginLeft: 8 }}
                    checked={chartConfig[field.key] ?? field.default ?? false}
                    onChange={(e) => setCfg(field.key, e.target.checked)}
                  />
                </div>
              )

              if (field.type === 'select') {
                const isColorPalette = field.key === 'colorPalette'
                const optList = isColorPalette ? COLOR_PALETTE_OPTIONS : (
                  Array.isArray(opts)
                    ? (typeof opts[0] === 'string' ? opts.map((v) => ({ value: v, label: v })) : opts)
                    : []
                )
                return (
                  <div key={field.key} className="form-group-left">
                    <label style={labelStyle}>{field.label}</label>
                    <select
                      value={chartConfig[field.key] || ''}
                      onChange={(e) => setCfg(field.key, e.target.value)}
                      style={{ flex: 1 }}
                    >
                      {!field.required && <option value="">-- 선택하세요 --</option>}
                      {optList.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </div>
                )
              }
              return null
            })}

            {/* 버튼 */}
            <div className="button-group" style={{ flexShrink: 0, marginTop: 12 }}>
              <button type="button" className="icon-btn" onClick={handleReset}>
                <div className="icon-wrapper">
                  <img src="/icons/new.svg" className="icon-img new-icon" alt="신규" />
                  <span className="icon-label">신규</span>
                </div>
              </button>
              <button type="button" className="icon-btn" onClick={handleSave} disabled={saveChart.isPending}>
                <div className="icon-wrapper">
                  <img src="/icons/save.svg" className="icon-img save-icon" alt="저장" />
                  <span className="icon-label">저장</span>
                </div>
              </button>
              <button type="button" className="icon-btn" onClick={handleDelete} disabled={deleteChart.isPending}>
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
          </div>
        )}

        {/* 영역4: 미리보기 */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <h4 style={{ flexShrink: 0, marginBottom: 8 }}>미리보기 결과</h4>
          <div style={{ flex: 1, overflowY: 'auto', border: '1px solid #ddd', borderRadius: 4, padding: 8, backgroundColor: '#fafafa' }}>
            {previewLoading
              ? <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}><Spin /></div>
              : previewUrl
                ? <img src={previewUrl} alt="차트 미리보기" style={{ maxWidth: '100%' }} />
                : <div style={{ color: '#aaa', fontSize: 13, paddingTop: 20, textAlign: 'center' }}>미리보기 버튼을 클릭하면 차트가 표시됩니다.</div>
            }
          </div>
        </div>

      </div>
    </div>
  )
}
