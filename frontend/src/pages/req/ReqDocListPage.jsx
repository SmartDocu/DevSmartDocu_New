/**
 * ReqDocListPage — 문서
 * _old_ref/pages/templates/pages/req_doc_list.html 구조 그대로 반영
 */
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, DatePicker, Spin } from 'antd'
import dayjs from 'dayjs'
import apiClient from '@/api/client'
import { useGendocs, useDataparams, useCreateGendoc, useDeleteGendoc, useUpdateGendocParams } from '@/hooks/useGendocs'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'

const { RangePicker } = DatePicker

// sessionStorage 키
const SS_GENDOCUID = 'doc_list_gendocuid'
const SS_START     = 'doc_list_start_date'
const SS_END       = 'doc_list_end_date'

function initDates() {
  const s = sessionStorage.getItem(SS_START)
  const e = sessionStorage.getItem(SS_END)
  if (s && e) return [dayjs(s), dayjs(e)]
  const today = dayjs()
  return [today.subtract(10, 'day'), today]
}

/* ──────────────────────────────────────────────────────
   값 찾기 모달 (modal_search_params.html 동일 구조)
────────────────────────────────────────────────────── */
function SearchParamsModal({ dp, rows, columns, onSelect, onClose }) {
  const [search,  setSearch]  = useState('')
  const [selRow,  setSelRow]  = useState(null)

  const keyCol = dp.keycolnm
  const nmCol  = dp.nmcolnm || dp.keycolnm

  const filtered = search
    ? rows.filter((r) =>
        Object.values(r).some((v) => String(v).toLowerCase().includes(search.toLowerCase()))
      )
    : rows

  // ESC 닫기
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const handleOk = () => {
    if (!selRow) { alert(t('msg.select')); return }
    onSelect(String(selRow[keyCol] ?? ''), String(selRow[nmCol] ?? selRow[keyCol] ?? ''))
    onClose()
  }

  return (
    <div style={{
      display: 'flex', position: 'fixed', inset: 0,
      background: 'rgba(0,0,0,0.4)', zIndex: 1000,
      justifyContent: 'center', alignItems: 'center',
    }}>
      <div style={{
        position: 'relative', background: '#fff', borderRadius: 10, padding: 20,
        width: 600, height: '90%', display: 'flex', flexDirection: 'column',
        boxShadow: '0 4px 20px rgba(0,0,0,0.25)', border: '1px solid #ccc',
      }}>
        {/* 닫기 × */}
        <button
          style={{ position: 'absolute', top: 10, right: 12, border: 'none', background: 'none', fontSize: 22, cursor: 'pointer' }}
          onClick={onClose}
        >&times;</button>

        <h3 style={{ textAlign: 'center', marginBottom: 0 }}>{t('ttl.value.select')}</h3>

        {/* 검색 */}
        <div style={{ marginTop: 10 }}>
          <input
            autoFocus
            type="text"
            placeholder={t('msg.ph.search')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: '97%', padding: 8, borderRadius: 6, border: '1px solid #ccc', fontSize: 14 }}
          />
        </div>

        {/* 로딩/없음 메시지 */}
        {rows.length === 0 && (
          <p style={{ marginTop: 10 }}>{t('msg.no.data')}</p>
        )}

        {/* 테이블 */}
        {rows.length > 0 && (
          <div style={{ flex: 1, overflowY: 'auto', marginTop: 10 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr>
                  {columns.map((col) => (
                    <th key={col} style={{
                      position: 'sticky', top: 0,
                      background: 'var(--primary-500, #245F97)', color: '#fff',
                      padding: 8, border: 'none', fontWeight: 600,
                    }}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((row, i) => {
                  const isSelected = selRow && String(selRow[keyCol]) === String(row[keyCol])
                  return (
                    <tr
                      key={i}
                      onClick={() => setSelRow(row)}
                      className={isSelected ? 'selected-row' : ''}
                      style={{ cursor: 'pointer' }}
                      onMouseEnter={(e) => { if (!isSelected) e.currentTarget.style.background = 'var(--tbody-hover, #CCDFEF)' }}
                      onMouseLeave={(e) => { if (!isSelected) e.currentTarget.style.background = '' }}
                    >
                      {columns.map((col) => (
                        <td key={col} style={{ padding: 8, borderBottom: '1px solid #eee' }}>
                          {row[col] ?? ''}
                        </td>
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* 확인 버튼 */}
        <div style={{ marginTop: 10, display: 'flex', justifyContent: 'center' }}>
          <button type="button" className="btn btn-primary" onClick={handleOk}>
            {t('btn.ok')}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ──────────────────────────────────────────────────────
   메인 페이지
────────────────────────────────────────────────────── */
export default function ReqDocListPage() {
  useLangStore((s) => s.translations)

  const { message } = App.useApp()
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const editbuttonyn   = user?.editbuttonyn === 'Y'

  const today = dayjs()
  const [dates,        setDates]        = useState(initDates)
  const [appliedDates, setAppliedDates] = useState(initDates)
  const [loading,      setLoading]      = useState(false)
  const [loadingText,  setLoadingText]  = useState('')

  const sd = appliedDates[0]?.format('YYYY-MM-DD')
  const ed = appliedDates[1]?.format('YYYY-MM-DD')

  const { data: listData = {}, isLoading, refetch } = useGendocs(sd, ed, user?.docid)
  const { data: paramData = {} } = useDataparams()

  const gendocs      = listData.gendocs    || []
  const docnm_base   = listData.docnm      || ''
  const dataparams   = listData.dataparams || []
  const paramsValue  = paramData.params_value || []
  const docid        = listData.docid      || null

  const createGendoc = useCreateGendoc()
  const deleteGendoc = useDeleteGendoc()
  const updateParams = useUpdateGendocParams()

  // 우측 패널 상태
  const [selectedGendocuid, setSelectedGendocuid] = useState(
    () => sessionStorage.getItem(SS_GENDOCUID) || ''
  )
  const [selectedRow, setSelectedRow] = useState(null)
  const [docnmInput,  setDocnmInput]  = useState('')
  const [paramValues, setParamValues] = useState({})  // paramuid → { value, finalnm }

  // 값 찾기 모달 상태
  const [searchModal, setSearchModal] = useState(null)  // null | { dp, rows, columns }

  // gendocs 로드 후 저장된 행 복원
  useEffect(() => {
    const saved = sessionStorage.getItem(SS_GENDOCUID)
    if (!saved || !gendocs.length) return
    const row = gendocs.find((r) => String(r.gendocuid) === saved)
    if (row && !selectedRow) handleRowClick(row)
  }, [gendocs]) // eslint-disable-line

  const showLoading = (txt) => { setLoading(true);  setLoadingText(txt) }
  const hideLoading = ()     => { setLoading(false); setLoadingText('') }

  // 값 찾기 모달 열기
  const openSearchModal = (dp) => {
    const pv = paramsValue.find((pv) => pv.datauid === dp.datauid)
    const rows    = pv?.value || []
    const columns = rows.length > 0 ? Object.keys(rows[0]) : []
    setSearchModal({ dp, rows, columns })
  }

  // 행 클릭
  const handleRowClick = (row) => {
    setSelectedGendocuid(row.gendocuid)
    setSelectedRow(row)
    setDocnmInput(row.gendocnm || '')
    const newVals = {}
    ;(row.params || []).forEach((p) => {
      newVals[p.paramuid] = { value: p.paramvalue || '', finalnm: p.finalnm || p.paramvalue || '' }
    })
    setParamValues(newVals)
  }

  // 신규
  const handleNew = () => {
    setSelectedGendocuid('')
    setSelectedRow(null)
    setDocnmInput(docnm_base ? `${docnm_base}_` : '')
    setParamValues({})
  }

  // 저장
  const handleSave = async () => {
    if (!docnmInput.trim()) { message.warning(t('msg.doc.required')); return }

    const params = dataparams.map((dp) => ({
      paramuid:   dp.paramuid,
      paramnm:    dp.paramnm,
      orderno:    dp.orderno,
      paramvalue: (paramValues[dp.paramuid]?.value)   || '',
      finalnm:    (paramValues[dp.paramuid]?.finalnm) || (paramValues[dp.paramuid]?.value) || '',
    }))

    const emptyParams = params.filter((p) => !p.paramvalue || !p.paramvalue.trim())
    if (emptyParams.length > 0) {
      message.warning(`${t('msg.param.required')}\n${emptyParams.map((p) => `• ${p.paramnm}`).join('\n')}`)
      return
    }

    if (selectedGendocuid) {
      // 기존 문서 수정
      showLoading(t('msg.loading.params'))
      updateParams.mutate(
        { gendocuid: selectedGendocuid, gendocnm: docnmInput, params },
        { onSuccess: () => { hideLoading(); refetch() }, onError: () => hideLoading() },
      )
    } else {
      // 신규 문서 생성
      if (!docid) { message.error(t('msg.docid.load.error')); return }
      showLoading(t('msg.loading.gendoc'))
      try {
        const objChk = await apiClient.post('/gendocs/check-objects', { docid })
        if (objChk.data.unset_objects?.length > 0) {
          const msgs = objChk.data.unset_objects.map((o) => o.text).join('\n')
          hideLoading()
          message.warning(`${t('msg.unset.objects')}:\n${msgs}`)
          return
        }

        const chk = await apiClient.post('/gendocs/params/check', { docid, params })
        if (chk.data.exists) {
          hideLoading()
          if (!window.confirm(t('msg.doc.param.duplicate'))) return
          showLoading(t('msg.loading.gendoc'))
        }

        createGendoc.mutate(
          { docid, docnm: docnmInput, params },
          {
            onSuccess: (data) => {
              hideLoading()
              saveSession(data.gendocuid)
              navigate(`/req/chapters-read?gendocs=${data.gendocuid}`)
            },
            onError: () => hideLoading(),
          },
        )
      } catch (e) {
        hideLoading()
        message.error(e.response?.data?.detail || t('msg.server.error'))
      }
    }
  }

  // 삭제
  const handleDelete = () => {
    if (!selectedGendocuid) { message.warning(t('msg.doc.select')); return }
    if (!window.confirm(t('msg.confirm.delete'))) return
    showLoading(t('msg.loading.gendoc.delete'))
    deleteGendoc.mutate(selectedGendocuid, {
      onSuccess: () => { hideLoading(); handleNew(); refetch() },
      onError:   () => hideLoading(),
    })
  }

  // 세션 저장
  const saveSession = (gendocuid) => {
    sessionStorage.setItem(SS_GENDOCUID, gendocuid || selectedGendocuid)
    sessionStorage.setItem(SS_START, appliedDates[0]?.format('YYYY-MM-DD') || '')
    sessionStorage.setItem(SS_END,   appliedDates[1]?.format('YYYY-MM-DD') || '')
    sessionStorage.setItem('path', 'req_doc_list')
  }

  const handleDocRead = () => {
    if (!selectedGendocuid) { message.warning(t('msg.doc.select')); return }
    saveSession()
    navigate(`/req/doc-read?gendocs=${selectedGendocuid}`)
  }

  const handleChapterRead = () => {
    if (!selectedGendocuid) { message.warning(t('msg.doc.select')); return }
    saveSession()
    navigate(`/req/chapters-read?gendocs=${selectedGendocuid}`)
  }

  // ── 렌더 ─────────────────────────────────────────────────────────────────────
  return (
    <div style={{ position: 'relative' }}>

      {/* 값 찾기 모달 */}
      {searchModal && (
        <SearchParamsModal
          dp={searchModal.dp}
          rows={searchModal.rows}
          columns={searchModal.columns}
          onSelect={(value, finalnm) => {
            setParamValues((prev) => ({
              ...prev,
              [searchModal.dp.paramuid]: { value, finalnm },
            }))
          }}
          onClose={() => setSearchModal(null)}
        />
      )}

      {/* 로딩 오버레이 */}
      {loading && (
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
            <span>{loadingText || t('msg.loading.wait')}</span>
          </div>
        </div>
      )}

      {/* 페이지 타이틀 */}
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('lbl.doc')} - {docnm_base}</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center' }}>
        </div>
      </div>

      {/* 날짜 필터 */}
      <div className="page-title" style={{ marginBottom: 20 }}>
        <div className="filter-item" style={{ gap: 12, flexWrap: 'wrap' }}>
          <label style={{ fontWeight: 'bold', marginRight: 35 }}>{t('lbl.create.period')}:</label>
          <RangePicker value={dates} onChange={setDates} />
          <button className="btn btn-link" onClick={() => setDates([today.subtract(3, 'month'), today])}>{t('btn.3months')}</button>
          <button className="btn btn-link" onClick={() => setDates([today.subtract(12, 'month'), today])}>{t('btn.1year')}</button>
          <button type="button" className="icon-btn" onClick={() => { setAppliedDates(dates); setTimeout(refetch, 0) }} title={t('btn.lookup')}>
            <img src="/icons/search.svg" className="icon-img config-icon" alt={t('btn.lookup')} />
          </button>
        </div>
      </div>

      {/* 2패널 */}
      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>

        {/* 왼쪽: 문서 목록 */}
        <div style={{ flex: 1, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.doc.list')}</h3>
            {editbuttonyn && (
              <button className="btn btn-primary" type="button" onClick={handleNew}>
                {t('btn.new')}
              </button>
            )}
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th style={{ width: '18%' }}>{t('thd.gendocnm')}</th>
                  <th style={{ width: '15%' }}>{t('thd.params')}</th>
                  <th style={{ width:  '7%', textAlign: 'center' }}>{t('thd.createuser')}</th>
                  <th style={{ width:  '7%', textAlign: 'center' }}>{t('thd.updateuser')}</th>
                  <th style={{ width: '10%', textAlign: 'center' }}>{t('thd.createfiledts')}</th>
                  <th style={{ width: '10%', textAlign: 'center' }}>{t('thd.updatefiledts')}</th>
                  <th style={{ width:  '5%', textAlign: 'center' }}>{t('thd.closeyn')}</th>
                  <th style={{ width:  '7%', textAlign: 'center' }}>{t('thd.closeuser')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={8} style={{ textAlign: 'center', padding: 16 }}><Spin /></td></tr>
                ) : gendocs.length === 0 ? (
                  <tr><td colSpan={8} style={{ textAlign: 'center', padding: 16 }}>{t('msg.no.data')}</td></tr>
                ) : gendocs.map((row) => (
                  <tr
                    key={row.gendocuid}
                    onClick={() => handleRowClick(row)}
                    className={selectedGendocuid === row.gendocuid ? 'selected-row' : ''}
                    style={{ cursor: 'pointer' }}
                  >
                    <td>{row.gendocnm}</td>
                    <td>{row.finalnm_joined || ''}</td>
                    <td style={{ textAlign: 'center' }}>{row.createuser  || ''}</td>
                    <td style={{ textAlign: 'center' }}>{row.updateuser  || ''}</td>
                    <td style={{ textAlign: 'center' }}>{row.createfiledts || ''}</td>
                    <td style={{ textAlign: 'center' }}>{row.updatefiledts || ''}</td>
                    <td style={{ textAlign: 'center' }}>{row.closeyn ? '√' : ''}</td>
                    <td style={{ textAlign: 'center' }}>{row.closeuser  || ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 오른쪽: 문서 구성 + 매개변수 */}
        <div style={{ flex: 0.75, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>

          {/* 문서 구성 소제목 */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.doc.config')}</h3>
            <div />
          </div>

          <div className="form-group-left">
            <label style={{ width: 60 }}>{t('lbl.docnm')}</label>
            <input
              id="docnm"
              value={docnmInput}
              onChange={(e) => setDocnmInput(e.target.value)}
              disabled={!editbuttonyn}
              placeholder={t('msg.ph.gendocnm')}
              style={{ height: 25 }}
            />
          </div>

          {/* 매개변수 입력 소제목 */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.param.input')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {selectedGendocuid && (
                <>
                  <button className="btn btn-primary" type="button" onClick={handleDocRead}>
                    {t('btn.doc.read')}
                  </button>
                  <button className="btn btn-primary" type="button" onClick={handleChapterRead}>
                    {t('btn.chapter.read')}
                  </button>
                  <span style={{ color: '#d9d9d9', margin: '0 12px' }}>|</span>
                </>
              )}
              {editbuttonyn && (
                <>
                  <button className="btn btn-primary" type="button" onClick={handleSave}>
                    {t('btn.save')}
                  </button>
                  {selectedGendocuid && (
                    <button className="btn btn-danger" type="button" onClick={handleDelete} disabled={deleteGendoc.isPending}>
                      {t('btn.delete')}
                    </button>
                  )}
                </>
              )}
            </div>
          </div>

          <table className="table table-bordered table-sm" style={{ marginBottom: 12 }}>
            <thead>
              <tr>
                <th style={{ width: '30%' }}>{t('thd.paramnm_thd')}</th>
                <th style={{ width: '35%' }}>{t('lbl.samplevalue')}</th>
                <th style={{ width: '35%' }}>{t('thd.inputvalue')}</th>
              </tr>
            </thead>
            <tbody>
              {dataparams.length === 0 ? (
                <tr><td colSpan={3} style={{ textAlign: 'center', padding: 12 }}>{t('msg.no.data')}</td></tr>
              ) : dataparams.map((dp) => (
                <tr key={dp.paramuid}>
                  <td>{dp.paramnm}</td>
                  <td>{dp.samplevalue || ''}</td>
                  <td>
                    {dp.datauid ? (
                      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                        <input
                          type="text"
                          value={paramValues[dp.paramuid]?.finalnm || ''}
                          onChange={(e) => setParamValues((prev) => ({
                            ...prev,
                            [dp.paramuid]: { value: e.target.value, finalnm: e.target.value },
                          }))}
                          disabled={!editbuttonyn}
                          style={{ flex: 1, height: 24, padding: '2px 6px', fontSize: 13 }}
                        />
                        {editbuttonyn && (
                          <button
                            type="button"
                            className="icon-btn search-btn"
                            onClick={() => openSearchModal(dp)}
                          >
                            <div className="icon-wrapper">
                              <img src="/icons/search.svg" className="icon-img-tbl new-icon" alt={t('btn.lookup')} />
                              <span className="icon-label">{t('btn.lookup')}</span>
                            </div>
                          </button>
                        )}
                      </div>
                    ) : (
                      <input
                        type="text"
                        value={paramValues[dp.paramuid]?.value || ''}
                        onChange={(e) => setParamValues((prev) => ({
                          ...prev,
                          [dp.paramuid]: { value: e.target.value, finalnm: e.target.value },
                        }))}
                        disabled={!editbuttonyn}
                        style={{ width: '100%', height: 24, padding: '2px 6px', fontSize: 13 }}
                      />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

        </div>
      </div>
    </div>
  )
}
