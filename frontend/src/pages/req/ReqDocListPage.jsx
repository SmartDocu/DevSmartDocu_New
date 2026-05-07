/**
 * ReqDocListPage — 문서
 * _old_ref/pages/templates/pages/req_doc_list.html 구조 그대로 반영
 */
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, Button, DatePicker, Spin } from 'antd'
import dayjs from 'dayjs'
import apiClient from '@/api/client'
import { useGendocs, useDataparams, useCreateGendoc, useDeleteGendoc, useUpdateGendocParams } from '@/hooks/useGendocs'
import { useAuthStore } from '@/stores/authStore'

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
    if (!selRow) { alert('값을 선택해주세요.'); return }
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

        <h3 style={{ textAlign: 'center', marginBottom: 0 }}>값 선택</h3>

        {/* 검색 */}
        <div style={{ marginTop: 10 }}>
          <input
            autoFocus
            type="text"
            placeholder="검색어 입력"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: '97%', padding: 8, borderRadius: 6, border: '1px solid #ccc', fontSize: 14 }}
          />
        </div>

        {/* 로딩/없음 메시지 */}
        {rows.length === 0 && (
          <p style={{ marginTop: 10 }}>데이터가 없습니다.</p>
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
          <button type="button" className="icon-btn" onClick={handleOk}>
            <img src="/icons/ok.svg" className="icon-img config-icon" alt="확인" />
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
  const { message } = App.useApp()
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const editbuttonyn   = user?.editbuttonyn === 'Y'
  const projectmanager = user?.projectmanager === 'Y'

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
    if (!docnmInput.trim()) { message.warning('문서명을 입력해주세요.'); return }

    const params = dataparams.map((dp) => ({
      paramuid:   dp.paramuid,
      paramnm:    dp.paramnm,
      orderno:    dp.orderno,
      paramvalue: (paramValues[dp.paramuid]?.value)   || '',
      finalnm:    (paramValues[dp.paramuid]?.finalnm) || (paramValues[dp.paramuid]?.value) || '',
    }))

    const emptyParams = params.filter((p) => !p.paramvalue || !p.paramvalue.trim())
    if (emptyParams.length > 0) {
      message.warning(`입력되지 않은 매개변수:\n${emptyParams.map((p) => `• ${p.paramnm}`).join('\n')}`)
      return
    }

    if (selectedGendocuid) {
      // 기존 문서 수정
      showLoading('파라미터 값 변경 중')
      updateParams.mutate(
        { gendocuid: selectedGendocuid, gendocnm: docnmInput, params },
        { onSuccess: () => { hideLoading(); refetch() }, onError: () => hideLoading() },
      )
    } else {
      // 신규 문서 생성
      if (!docid) { message.error('문서 ID를 불러오지 못했습니다. 페이지를 새로고침 후 다시 시도해주세요.'); return }
      showLoading('문서 생성 중')
      try {
        const objChk = await apiClient.post('/gendocs/check-objects', { docid })
        if (objChk.data.unset_objects?.length > 0) {
          const msgs = objChk.data.unset_objects.map((o) => o.text).join('\n')
          hideLoading()
          message.warning(`미설정 항목이 있습니다:\n${msgs}`)
          return
        }

        const chk = await apiClient.post('/gendocs/params/check', { docid, params })
        if (chk.data.exists) {
          hideLoading()
          if (!window.confirm('문서명 및 매개변수 값이 이미 존재하고 있습니다.\n그래도 진행하시겠습니까?')) return
          showLoading('문서 생성 중')
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
        message.error(e.response?.data?.detail || '오류가 발생했습니다.')
      }
    }
  }

  // 삭제 (이전앱: window.confirm 사용)
  const handleDelete = () => {
    if (!selectedGendocuid) { message.warning('선택된 문서가 없습니다.'); return }
    if (!window.confirm('선택하신 문서를 삭제하시겠습니까?\n삭제 후 되돌릴 수 없습니다.')) return
    showLoading('문서 삭제 중')
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
    if (!selectedGendocuid) { message.warning('선택된 문서가 없습니다.'); return }
    saveSession()
    navigate(`/req/doc-read?gendocs=${selectedGendocuid}`)
  }

  const handleChapterRead = () => {
    if (!selectedGendocuid) { message.warning('선택된 문서가 없습니다.'); return }
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
        <div id="formatLoading" style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(255,255,255,0.6)', zIndex: 9999,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <div className="loading-content">
            <div className="spinner" />
            <div style={{ textAlign: 'center' }}>{loadingText}</div>
            <div>잠시만 기다려 주세요.</div>
          </div>
        </div>
      )}

      {/* 페이지 타이틀 */}
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>문서: {docnm_base}</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <button type="button" className="icon-btn" title="도움말">
            <img src="/icons/help.svg" className="icon-img config-icon" alt="도움말" />
          </button>
        </div>
      </div>

      {/* 날짜 필터 */}
      <div className="page-title" style={{ marginBottom: 20 }}>
        <div className="filter-item" style={{ gap: 12, flexWrap: 'wrap' }}>
          <label style={{ fontWeight: 'bold' }}>생성 기간:</label>
          <RangePicker value={dates} onChange={setDates} />
          <Button size="small" className="btn btn-link" onClick={() => setDates([today.subtract(3, 'month'), today])}>3개월</Button>
          <Button size="small" className="btn btn-link" onClick={() => setDates([today.subtract(12, 'month'), today])}>1년</Button>
          <button type="button" className="icon-btn" onClick={() => { setAppliedDates(dates); setTimeout(refetch, 0) }} title="조회">
            <img src="/icons/search.svg" className="icon-img config-icon" alt="조회" />
          </button>
        </div>
      </div>

      {/* 2패널 */}
      <div style={{ display: 'flex', marginTop: 20, gap: 20 }}>

        {/* 왼쪽: 문서 목록 */}
        <div style={{ flex: 1 }}>
          <h3>문서 목록</h3>
          <div style={{ overflowX: 'auto' }}>
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th style={{ width: '18%' }}>작성문서명</th>
                  <th style={{ width: '15%' }}>매개변수</th>
                  <th style={{ width:  '7%', textAlign: 'center' }}>작성자</th>
                  <th style={{ width:  '7%', textAlign: 'center' }}>업로더</th>
                  <th style={{ width: '10%', textAlign: 'center' }}>작성일시</th>
                  <th style={{ width: '10%', textAlign: 'center' }}>업로드일시</th>
                  <th style={{ width:  '5%', textAlign: 'center' }}>마감</th>
                  <th style={{ width:  '7%', textAlign: 'center' }}>마감자</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={8} style={{ textAlign: 'center', padding: 16 }}><Spin /></td></tr>
                ) : gendocs.length === 0 ? (
                  <tr><td colSpan={8} style={{ textAlign: 'center', padding: 16 }}>생성된 문서가 없습니다.</td></tr>
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

        {/* 오른쪽: 문서 구성 + 매개변수 + 버튼 */}
        <div style={{ flex: 0.75 }}>

          {/* 문서 구성 */}
          <h3>문서 구성</h3>
          <div className="form-group-left">
            <label style={{ width: 60 }}>문서명</label>
            <input
              id="docnm"
              value={docnmInput}
              onChange={(e) => setDocnmInput(e.target.value)}
              disabled={!editbuttonyn}
              placeholder="문서명을 입력하시오."
              style={{ height: 25 }}
            />
          </div>

          {/* 매개변수 입력 */}
          <h3>매개변수 입력</h3>
          <table className="table table-bordered table-sm" style={{ marginBottom: 12 }}>
            <thead>
              <tr>
                <th style={{ width: '30%' }}>매개변수명</th>
                <th style={{ width: '35%' }}>예시값</th>
                <th style={{ width: '35%' }}>입력값</th>
              </tr>
            </thead>
            <tbody>
              {dataparams.length === 0 ? (
                <tr><td colSpan={3} style={{ textAlign: 'center', padding: 12 }}>매개변수가 없습니다.</td></tr>
              ) : dataparams.map((dp) => (
                <tr key={dp.paramuid}>
                  <td>{dp.paramnm}</td>
                  <td>{dp.samplevalue || ''}</td>
                  <td>
                    {dp.datauid ? (
                      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                        {/* 직접 입력 가능한 input */}
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
                        {/* 값 찾기 아이콘 버튼 */}
                        {editbuttonyn && (
                          <button
                            type="button"
                            className="icon-btn search-btn"
                            onClick={() => openSearchModal(dp)}
                          >
                            <div className="icon-wrapper">
                              <img src="/icons/search.svg" className="icon-img-tbl new-icon" alt="값 찾기" />
                              <span className="icon-label">값 찾기</span>
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

          {/* 액션 버튼 */}
          <div className="button-group" style={{ gap: 35 }}>
            {editbuttonyn && (
              <div className="button-group">
                <button type="button" className="icon-btn" onClick={handleNew}>
                  <div className="icon-wrapper">
                    <img src="/icons/new.svg" className="icon-img new-icon" alt="신규" />
                    <span className="icon-label">신규</span>
                  </div>
                </button>
                <button type="button" className="icon-btn" onClick={handleSave}>
                  <div className="icon-wrapper">
                    <img src="/icons/save.svg" className="icon-img save-icon" alt="저장" />
                    <span className="icon-label">저장</span>
                  </div>
                </button>
                <button type="button" className="icon-btn" onClick={handleDelete} disabled={deleteGendoc.isPending}>
                  <div className="icon-wrapper">
                    <img src="/icons/delete.svg" className="icon-img del-icon" alt="삭제" />
                    <span className="icon-label">삭제</span>
                  </div>
                </button>
              </div>
            )}
            <div className="button-group">
              <button type="button" className="icon-btn" onClick={handleDocRead}>
                <div className="icon-wrapper">
                  <img src="/icons/doc-preview.svg" className="icon-img config-icon" alt="문서 조회" />
                  <span className="icon-label">문서 조회</span>
                </div>
              </button>
              <button type="button" className="icon-btn" onClick={handleChapterRead}>
                <div className="icon-wrapper">
                  <img src="/icons/chapter-preview.svg" className="icon-img config-icon" alt="챕터 조회" />
                  <span className="icon-label">챕터 조회</span>
                </div>
              </button>
            </div>
          </div>

        </div>
      </div>
    </div>
  )
}
