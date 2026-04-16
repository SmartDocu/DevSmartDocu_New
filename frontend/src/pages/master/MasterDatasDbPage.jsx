import { useState, useEffect, useRef } from 'react'
import { App, Modal, Popconfirm } from 'antd'
import {
  useDatasDb, useDbConnectors, useSaveDbData, useDeleteData,
  useDatacols, useCreateDatacols, useSaveDatacols,
} from '@/hooks/useDatas'
import { useDocs } from '@/hooks/useDocs'

const EMPTY_FORM = { datauid: '', projectid: '', connectid: '', datanm: '', query: '' }

export default function MasterDatasDbPage() {
  const { message } = App.useApp()
  const { data: datas = [], isLoading } = useDatasDb()
  const { data: docs = [] } = useDocs()
  const { data: connectors = [] } = useDbConnectors()
  const saveData     = useSaveDbData()
  const deleteData   = useDeleteData('db')
  const createCols   = useCreateDatacols()
  const saveCols     = useSaveDatacols()

  const [form,        setForm]        = useState(EMPTY_FORM)
  const [selectedUid, setSelectedUid] = useState(null)
  const [colsLocal,   setColsLocal]   = useState([])

  const queryRef = useRef(null)

  // 프로젝트 목록 (docs에서 deduplicate)
  const projects = docs
    .map((d) => ({ projectid: d.projectid, projectnm: d.projectnm }))
    .filter((p, i, arr) => p.projectid && arr.findIndex((x) => x.projectid === p.projectid) === i)

  // 선택된 데이터의 컬럼 조회
  const { data: datacols = [] } = useDatacols(selectedUid)

  // datacols가 변경되면 로컬 상태 갱신
  useEffect(() => {
    setColsLocal(datacols.map((c) => ({ ...c })))
  }, [datacols])

  const autoResize = (el) => {
    if (!el) return
    el.style.height = 'auto'
    el.style.height = (el.scrollHeight + 10 || 40) + 'px'
  }

  const handleRowClick = (row) => {
    setSelectedUid(row.datauid)
    setForm({
      datauid:   row.datauid || '',
      projectid: row.projectid || '',
      connectid: row.connectid || '',
      datanm:    row.datanm || '',
      query:     row.query || '',
    })
    // textarea 높이 조정 (다음 렌더 후)
    setTimeout(() => autoResize(queryRef.current), 0)
  }

  const handleNew = () => {
    setSelectedUid(null)
    setForm(EMPTY_FORM)
    setColsLocal([])
    setTimeout(() => autoResize(queryRef.current), 0)
  }

  const handleSave = () => {
    if (!form.datanm.trim() || !form.connectid || !form.projectid) {
      message.warning('데이터명, 서버정보, 프로젝트는 필수입니다.')
      return
    }
    const body = {
      datauid:   form.datauid || null,
      datanm:    form.datanm,
      connectid: form.connectid,
      projectid: form.projectid,
      query:     form.query,
    }
    saveData.mutate(body, {
      onSuccess: (result) => {
        const savedUid = result?.datauid || form.datauid
        if (savedUid) {
          createCols.mutate({ datauid: savedUid }, {
            onSuccess: () => {
              message.success('저장 및 컬럼 생성 완료')
              setSelectedUid(savedUid)
            },
            onError: () => message.warning('데이터는 저장되었으나 컬럼 생성에 실패했습니다.'),
          })
        } else {
          message.success('저장되었습니다.')
        }
      },
      onError: (err) => message.error(err.response?.data?.detail || '저장 실패'),
    })
  }

  const handleDelete = () => {
    if (!form.datauid) { message.warning('삭제할 데이터를 선택해주세요.'); return }
    Modal.confirm({
      title: '삭제 확인', content: '삭제하시겠습니까?',
      okText: '삭제', cancelText: '취소', okButtonProps: { danger: true },
      onOk: () => deleteData.mutate(form.datauid, {
        onSuccess: () => { message.success('삭제 완료'); handleNew() },
        onError: (err) => message.error(err.response?.data?.detail || '삭제 실패'),
      }),
    })
  }

  const handleSaveCols = () => {
    if (colsLocal.length === 0) { message.warning('저장할 컬럼 데이터가 없습니다.'); return }
    const payload = colsLocal.map((c) => ({
      datauid:    c.datauid || selectedUid,
      querycolnm: c.querycolnm,
      dispcolnm:  c.dispcolnm || '',
      datatypecd: c.datatypecd || 'C',
      measureyn:  !!c.measureyn,
    }))
    saveCols.mutate(payload, {
      onSuccess: () => message.success('모든 컬럼이 성공적으로 저장되었습니다.'),
      onError: (err) => message.error(err.response?.data?.detail || '저장 실패'),
    })
  }

  const updateCol = (i, field, value) => {
    setColsLocal((cols) => cols.map((c, idx) => idx === i ? { ...c, [field]: value } : c))
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>DB 데이터</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>

        {/* 왼쪽: 데이터 목록 (30%) */}
        <div style={{ flex: '30%' }}>
          <h3>데이터 목록</h3>
          <div className="table-container">
            <table id="docs-table" style={{ cursor: 'pointer' }}>
              <thead>
                <tr>
                  <th>프로젝트명</th>
                  <th>서버정보</th>
                  <th>데이터명</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center' }}>로딩 중...</td></tr>
                ) : datas.length === 0 ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center', color: '#888' }}>등록된 데이터가 없습니다.</td></tr>
                ) : datas.map((d) => (
                  <tr key={d.datauid}
                    className={selectedUid === d.datauid ? 'selected-row' : ''}
                    onClick={() => handleRowClick(d)}
                  >
                    <td>{d.projectnm || ''}</td>
                    <td>{d.connectnm || ''}</td>
                    <td>{d.datanm}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 가운데: 데이터 상세 (30%) */}
        <div style={{ flex: '30%' }}>
          <h3>데이터 상세</h3>
          <div style={{ paddingTop: 15 }}>

            <div className="form-group">
              <label htmlFor="data-projectid">프로젝트</label>
              <select id="data-projectid" value={form.projectid}
                onChange={(e) => setForm(f => ({ ...f, projectid: e.target.value }))}>
                <option value="">-- 프로젝트 선택 --</option>
                {projects.map((p) => (
                  <option key={p.projectid} value={p.projectid}>{p.projectnm}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="data-connectid">서버정보</label>
              <select id="data-connectid" value={form.connectid}
                onChange={(e) => setForm(f => ({ ...f, connectid: e.target.value }))}>
                <option value="">-- 서버 선택 --</option>
                {connectors.map((c) => (
                  <option key={c.connectid} value={c.connectid}>{c.connectnm}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>데이터명</label>
              <input type="text" value={form.datanm}
                onChange={(e) => setForm(f => ({ ...f, datanm: e.target.value }))} />
            </div>

            {/* 안 보이는 더미 필드 (브라우저 자동완성 방지) */}
            <input type="text" style={{ position: 'absolute', left: -9999, top: -9999 }} autoComplete="off" readOnly />

            <div className="form-group">
              <label htmlFor="data-query">쿼리</label>
              <textarea
                id="data-query"
                ref={queryRef}
                rows={1}
                value={form.query}
                style={{ resize: 'none', overflow: 'hidden', minHeight: 40 }}
                onChange={(e) => {
                  setForm(f => ({ ...f, query: e.target.value }))
                  autoResize(e.target)
                }}
              />
            </div>

            <div className="button-group">
              <button type="button" className="icon-btn" onClick={handleNew}>
                <div className="icon-wrapper">
                  <img src="/icons/new.svg" className="icon-img new-icon" alt="신규" />
                  <span className="icon-label">신규</span>
                </div>
              </button>
              <button type="button" className="icon-btn" onClick={handleSave}
                disabled={saveData.isPending || createCols.isPending}>
                <div className="icon-wrapper">
                  <img src="/icons/save.svg" className="icon-img save-icon" alt="저장" />
                  <span className="icon-label">저장</span>
                </div>
              </button>
              <Popconfirm title="삭제하시겠습니까?" onConfirm={handleDelete}
                okText="삭제" cancelText="취소" okButtonProps={{ danger: true }}
                disabled={!form.datauid}>
                <button type="button" className="icon-btn" disabled={deleteData.isPending}>
                  <div className="icon-wrapper">
                    <img src="/icons/delete.svg" className="icon-img del-icon" alt="삭제" />
                    <span className="icon-label">삭제</span>
                  </div>
                </button>
              </Popconfirm>
            </div>
          </div>
        </div>

        {/* 오른쪽: 데이터 컬럼 (35%) */}
        <div style={{ flex: '35%' }}>
          <h3>데이터 컬럼</h3>
          <table>
            <thead>
              <tr>
                <th>원본컬럼</th>
                <th>표현컬럼</th>
                <th>타입</th>
                <th>측정값여부</th>
              </tr>
            </thead>
            <tbody>
              {colsLocal.length === 0 ? (
                <tr><td colSpan={4} style={{ textAlign: 'center' }}>데이터를 선택해주세요</td></tr>
              ) : colsLocal.map((col, i) => (
                <tr key={i}>
                  <td>{col.querycolnm || ''}</td>
                  <td>
                    <input type="text" value={col.dispcolnm || ''}
                      onChange={(e) => updateCol(i, 'dispcolnm', e.target.value)} />
                  </td>
                  <td>
                    <select value={col.datatypecd || 'C'}
                      onChange={(e) => updateCol(i, 'datatypecd', e.target.value)}>
                      <option value="D">일자</option>
                      <option value="C">문자</option>
                      <option value="I">숫자</option>
                    </select>
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    <input type="checkbox" checked={!!col.measureyn}
                      onChange={(e) => updateCol(i, 'measureyn', e.target.checked)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="button-group">
            <button type="button" className="icon-btn" onClick={handleSaveCols}
              disabled={saveCols.isPending || colsLocal.length === 0}>
              <div className="icon-wrapper">
                <img src="/icons/save.svg" className="icon-img save-icon" alt="컬럼 전체 저장" />
                <span className="icon-label">컬럼 전체 저장</span>
              </div>
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}
