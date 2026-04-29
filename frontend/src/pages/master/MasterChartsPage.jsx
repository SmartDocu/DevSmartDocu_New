/**
 * MasterChartsPage — UI 차트 설정
 * Django master_charts.html 구조 그대로 반영
 * 4열: 데이터 목록 | 차트 유형 | 차트 설정 | 미리보기
 */
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { App } from 'antd'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useChapterDatas } from '@/hooks/useDatas'
import { useChart, useSaveChart, useDeleteChart } from '@/hooks/useCharts'
import { useObjectFilterDatauid } from '@/hooks/useTables'

const COLOR_PALETTE_OPTIONS = [
  { value: 'pastel', label: 'Pastel' },
  { value: 'bold',   label: 'Bold' },
  { value: 'earth',  label: 'Earth' },
  { value: 'ocean',  label: 'Ocean' },
  { value: 'sunset', label: 'Sunset' },
]

export default function MasterChartsPage() {
  useLangStore((s) => s.translations)
  const { message } = App.useApp()
  const [searchParams] = useSearchParams()
  const chapteruid = searchParams.get('chapteruid') || ''
  const objectnm   = searchParams.get('objectnm')   || ''
  const objectuid  = searchParams.get('objectuid')  || ''
  const chapternm  = searchParams.get('chapternm')  || ''
  const user     = useAuthStore((s) => s.user)
  const docnm    = user?.docnm
  const isEditYn = user?.editbuttonyn === 'Y'

  // ── 데이터 ─────────────────────────────────────────────────────────────────
  const { data: allDatas = [], isLoading: datasLoading } = useChapterDatas(chapteruid)
  const { data: chartData, isSuccess: chartSuccess } = useChart(chapteruid, objectnm)
  const saveChart   = useSaveChart()
  const deleteChart = useDeleteChart()

  const { data: filterDatauid } = useObjectFilterDatauid(objectuid, chartSuccess && chartData === null)

  // ── 차트 타입 상세 ──────────────────────────────────────────────────────────
  const [chartTypesDetail, setChartTypesDetail] = useState([])
  useEffect(() => {
    apiClient.get('/charts/types/detail')
      .then((r) => setChartTypesDetail(r.data.chart_types || []))
      .catch(() => {})
  }, [])

  // ── 선택 상태 ───────────────────────────────────────────────────────────────
  const [selectedDatauid,   setSelectedDatauid]   = useState('')
  const [isFilterDefault,   setIsFilterDefault]   = useState(false)
  const [selectedChartType, setSelectedChartType] = useState('')
  const [chartConfig,       setChartConfig]       = useState({})
  const [chartWidth,        setChartWidth]        = useState(500)
  const [chartHeight,       setChartHeight]       = useState(250)

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
    if (chartData.datauid)      setSelectedDatauid(chartData.datauid)
    if (chartData.displaytype)  setSelectedChartType(chartData.displaytype)
    if (chartData.chart_width)  setChartWidth(chartData.chart_width)
    if (chartData.chart_height) setChartHeight(chartData.chart_height)
    if (chartData.chartjson && Object.keys(chartData.chartjson).length)
      setChartConfig(chartData.chartjson)
  }, [chartData])

  // ── objectfilters 기본 데이터 적용 ─────────────────────────────────────────
  useEffect(() => {
    if (!filterDatauid) return
    setSelectedDatauid(filterDatauid)
    setIsFilterDefault(true)
  }, [filterDatauid])

  // ── 현재 선택된 차트 타입의 properties ─────────────────────────────────────
  const selectedTypeDetail = chartTypesDetail.find((ct) => ct.code === selectedChartType)
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
      message.warning(t('msg.chart.select.required'))
      return
    }
    saveChart.mutate(
      {
        objectuid, chapteruid, objectnm,
        datauid: selectedDatauid,
        displaytype: selectedChartType,
        chartjson: chartConfig,
        chart_width: chartWidth,
        chart_height: chartHeight,
      },
      {
        onSuccess: () => message.success(t('msg.save.success')),
        onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
      }
    )
  }

  const handleDelete = () => {
    if (!window.confirm(t('msg.confirm.delete'))) return
    deleteChart.mutate(
      { chapteruid, objectnm },
      {
        onSuccess: () => {
          message.success(t('msg.delete.success'))
          handleReset()
        },
        onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
      }
    )
  }

  const handlePreview = async () => {
    if (!selectedDatauid || !selectedChartType) {
      message.warning(t('msg.chart.select.required'))
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
      message.error(t('msg.preview.error') + ': ' + (e.response?.data?.detail || e.message))
    } finally {
      setPreviewLoading(false)
    }
  }

  const setCfg = (key, val) => setChartConfig((p) => ({ ...p, [key]: val }))

  // ── 렌더 ─────────────────────────────────────────────────────────────────
  return (
    <div>

      {/* 헤더 */}
      <div className="page-title" style={{ marginBottom: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.chart.manage')}{docnm ? ` - ${docnm}` : ''}</div>
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

      {/* 4열 레이아웃 */}
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
                onClick={() => { if (!isFilterDefault) handleDataSelect(d.datauid) }}
                style={isFilterDefault ? { cursor: 'not-allowed', opacity: 0.6 } : {}}
              >
                <div className="card-title">{d.datanm}</div>
              </div>
            ))}
          </div>
        </div>

        {/* 영역2: 차트 유형 */}
        <div style={{ flex: 2 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.chart.type')}</h3>
            <div />
          </div>
          <div className="chapter-card-container" style={{ overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
            {chartTypesDetail.map((ct) => (
              <div
                key={ct.code}
                className={`chapter-card${selectedChartType === ct.code ? ' selected' : ''}`}
                onClick={() => handleChartTypeSelect(ct.code)}
              >
                <div className="card-title">{ct.name}</div>
              </div>
            ))}
          </div>
        </div>

        {/* 영역3: 차트 설정 (차트 유형 선택 시에만 표시) */}
        {selectedChartType && (
          <div style={{ flex: 4 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
              <h3 style={{ margin: 0 }}>{t('ttl.chart.settings')}</h3>
              <div style={{ display: 'flex', gap: 8 }}>
                <button type="button" className="btn btn-primary" onClick={handleReset}>{t('btn.new')}</button>
                {isEditYn && (
                  <>
                    <button type="button" className="btn btn-primary" onClick={handleSave} disabled={saveChart.isPending}>{t('btn.save')}</button>
                    <button type="button" className="btn btn-danger" onClick={handleDelete} disabled={deleteChart.isPending}>{t('btn.delete')}</button>
                  </>
                )}
                <button type="button" className="btn btn-primary" onClick={handlePreview} disabled={previewLoading}>{t('btn.preview_btn')}</button>
              </div>
            </div>
            <div style={{ overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
              <p style={{ fontSize: 12, color: '#888', marginBottom: 8 }}>* {t('inf.chart.required.hint')}</p>

              {/* 차트 크기 */}
              <div className="form-group-left">
                <label style={{ width: 130 }}>{t('lbl.chart.size')} :</label>
                <div style={{ display: 'flex', gap: 8, flex: 1 }}>
                  <input
                    type="number"
                    value={chartWidth}
                    onChange={(e) => setChartWidth(Number(e.target.value))}
                    style={{ flex: 1 }}
                  />
                  <input
                    type="number"
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
                        {!field.required && <option value="">{t('msg.select.placeholder')}</option>}
                        {optList.map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    </div>
                  )
                }
                return null
              })}
            </div>
          </div>
        )}

        {/* 영역4: 미리보기 */}
        <div style={{ flex: 3 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.preview_ttl')}</h3>
            <div />
          </div>
          <div style={{ overflowY: 'auto', maxHeight: 'calc(100vh - 224px)', border: '1px solid #ddd', borderRadius: 4, padding: 8, backgroundColor: '#fafafa' }}>
            {previewLoading
              ? <div style={{ textAlign: 'center', padding: 20 }}>{t('msg.loading')}</div>
              : previewUrl
                ? <img src={previewUrl} alt="chart" style={{ maxWidth: '100%' }} />
                : <div style={{ color: '#aaa', fontSize: 13, paddingTop: 20, textAlign: 'center' }}>{t('inf.preview.empty')}</div>
            }
          </div>
        </div>

      </div>
    </div>
  )
}
