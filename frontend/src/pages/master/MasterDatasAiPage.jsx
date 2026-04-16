import { useEffect, useState } from 'react'
import {
  useDatasAi, useSaveAiData, useDeleteData,
  useDatasSource, useDatacols, useSaveDatacols,
} from '@/hooks/useDatas'
import { useDocs } from '@/hooks/useDocs'
import { useAuthStore } from '@/stores/authStore'

const DATATYPE_LABELS = { D: '일자', C: '문자', I: '숫자' }
const DATATYPE_OPTIONS = [
  { value: 'D', label: '일자' },
  { value: 'C', label: '문자' },
  { value: 'I', label: '숫자' },
]

export default function MasterDatasAiPage() {
  const user = useAuthStore((s) => s.user)
  const { data: datas = [] } = useDatasAi()
  const { data: docs = [] } = useDocs()
  const { data: sourceDatas = [] } = useDatasSource()
  const saveData = useSaveAiData()
  const deleteData = useDeleteData('df')
  const saveCols = useSaveDatacols()

  const projects = docs
    .map((d) => ({ projectid: d.projectid, projectnm: d.projectnm, rolecd: d.rolecd }))
    .filter((p, i, arr) => p.projectid && arr.findIndex((x) => x.projectid === p.projectid) === i)

  const [selectedData, setSelectedData] = useState(null)
  const [form, setForm] = useState({
    datauid: '', datanm: '', projectid: '', projectnm: '',
    sourcedatauid: '', sentence: '',
  })

  // Source data columns (read-only)
  const { data: sourceCols = [] } = useDatacols(form.sourcedatauid || null)
  // AI data columns (editable)
  const { data: rawCols = [] } = useDatacols(form.datauid || null)
  const [editCols, setEditCols] = useState([])

  useEffect(() => {
    setEditCols(rawCols.map((c) => ({ ...c })))
  }, [rawCols])

  // Filtered source datas by project (sourceDatas: { datauid, datanm, projectid })
  const filteredSources = sourceDatas.filter(
    (s) => !form.projectid || String(s.projectid) === String(form.projectid),
  )

  const isManager = (projectid) => {
    const p = projects.find((x) => String(x.projectid) === String(projectid))
    return p?.rolecd === 'M'
  }

  const selectData = (d) => {
    setSelectedData(d)
    setForm({
      datauid: d.datauid, datanm: d.datanm,
      projectid: d.projectid, projectnm: d.projectnm,
      sourcedatauid: d.sourcedatauid || '',
      sentence: d.gensentence || '',
    })
  }

  const handleNew = () => {
    setSelectedData(null)
    setForm({
      datauid: '', datanm: '',
      projectid: projects[0]?.projectid || '', projectnm: '',
      sourcedatauid: '', sentence: '',
    })
    setEditCols([])
  }

  const handleSave = () => {
    if (!form.datanm || !form.sourcedatauid) { alert('데이터명, 연결정보는 필수입니다.'); return }
    saveData.mutate({
      datauid: form.datauid || null,
      datanm: form.datanm,
      sourcedatauid: form.sourcedatauid,
      sentence: form.sentence,
      projectid: form.projectid,
    })
  }

  const handleDelete = () => {
    if (!form.datauid) { alert('삭제할 데이터를 선택해주세요.'); return }
    if (!window.confirm('삭제하시겠습니까?')) return
    deleteData.mutate(form.datauid, { onSuccess: handleNew })
  }

  const handleSaveCols = () => {
    if (editCols.length === 0) { alert('저장할 데이터가 없습니다.'); return }
    saveCols.mutate(editCols.map((c) => ({ ...c, datauid: form.datauid })))
  }

  const updateCol = (idx, field, value) => {
    setEditCols((prev) => prev.map((c, i) => i === idx ? { ...c, [field]: value } : c))
  }

  const showSaveDelete = isManager(form.projectid)

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>AI 데이터</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* Left: data cards */}
        <div style={{ flex: '15%' }}>
          <h3>데이터 목록</h3>
          <div className="chapter-card-container" style={{ flexDirection: 'column' }}>
            {datas.map((d) => (
              <div
                key={d.datauid}
                className={`chapter-card${selectedData?.datauid === d.datauid ? ' selected' : ''}`}
                onClick={() => selectData(d)}
              >
                <div className="card-title">{d.datanm}</div>
                <div className="card-subtitle">{d.projectnm}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Middle: data detail */}
        <div style={{ flex: '25%' }}>
          <h3>데이터 상세</h3>
          <div style={{ paddingTop: 15 }}>
            <div className="form-group">
              <label htmlFor="ai-datanm">데이터명</label>
              <input
                id="ai-datanm"
                type="text"
                value={form.datanm}
                onChange={(e) => setForm((f) => ({ ...f, datanm: e.target.value }))}
              />
            </div>

            <div className="form-group">
              <label htmlFor="ai-projectid">프로젝트명</label>
              {form.datauid ? (
                <span style={{ padding: '6px 4px', fontWeight: 600 }}>{form.projectnm}</span>
              ) : (
                <select
                  id="ai-projectid"
                  value={form.projectid}
                  onChange={(e) => setForm((f) => ({ ...f, projectid: e.target.value, sourcedatauid: '' }))}
                >
                  {projects.map((p) => <option key={p.projectid} value={p.projectid}>{p.projectnm}</option>)}
                </select>
              )}
            </div>

            <div className="form-group">
              <label htmlFor="ai-source">원본 데이터</label>
              <select
                id="ai-source"
                value={form.sourcedatauid}
                onChange={(e) => setForm((f) => ({ ...f, sourcedatauid: e.target.value }))}
              >
                <option value="">선택하세요</option>
                {filteredSources.map((s) => (
                  <option key={s.datauid} value={s.datauid}>{s.datanm}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="ai-sentence">프롬프트</label>
              <textarea
                id="ai-sentence"
                rows={10}
                value={form.sentence}
                onChange={(e) => setForm((f) => ({ ...f, sentence: e.target.value }))}
                style={{ width: '100%', resize: 'vertical' }}
              />
            </div>

            <div className="button-group">
              <button className="icon-btn" type="button" onClick={handleNew}>
                <div className="icon-wrapper">
                  <img src="/icons/new.svg" className="icon-img new-icon" alt="신규" />
                  <span className="icon-label">신규</span>
                </div>
              </button>
              {showSaveDelete && (
                <>
                  <button className="icon-btn" type="button" onClick={handleSave} disabled={saveData.isPending}>
                    <div className="icon-wrapper">
                      <img src="/icons/save.svg" className="icon-img save-icon" alt="저장" />
                      <span className="icon-label">저장</span>
                    </div>
                  </button>
                  {form.datauid && (
                    <button className="icon-btn" type="button" onClick={handleDelete} disabled={deleteData.isPending}>
                      <div className="icon-wrapper">
                        <img src="/icons/delete.svg" className="icon-img del-icon" alt="삭제" />
                        <span className="icon-label">삭제</span>
                      </div>
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        </div>

        {/* Right-left: source columns (read-only) */}
        <div style={{ flex: '30%' }}>
          <h3>원본 데이터 컬럼</h3>
          <div className="table-container">
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th style={{ width: '25%' }}>원본컬럼</th>
                  <th style={{ width: '40%' }}>표현컬럼</th>
                  <th style={{ width: '20%' }}>타입</th>
                  <th style={{ width: '15%' }}>측정값여부</th>
                </tr>
              </thead>
              <tbody>
                {sourceCols.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center' }}>데이터를 선택해주세요</td></tr>
                ) : sourceCols.map((col) => (
                  <tr key={col.querycolnm}>
                    <td>{col.querycolnm || ''}</td>
                    <td>{col.dispcolnm || ''}</td>
                    <td>{DATATYPE_LABELS[col.datatypecd] || col.datatypecd || ''}</td>
                    <td style={{ textAlign: 'center' }}>{col.measureyn ? '☑' : '☐'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right-right: AI data columns (editable) */}
        <div style={{ flex: '30%' }}>
          <h3>데이터 컬럼</h3>
          <div className="table-container">
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th style={{ width: '25%' }}>원본컬럼</th>
                  <th style={{ width: '40%' }}>표현컬럼</th>
                  <th style={{ width: '20%' }}>타입</th>
                  <th style={{ width: '15%' }}>측정값여부</th>
                </tr>
              </thead>
              <tbody>
                {editCols.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center' }}>데이터를 선택해주세요</td></tr>
                ) : editCols.map((col, idx) => (
                  <tr key={col.querycolnm}>
                    <td>{col.querycolnm || ''}</td>
                    <td>
                      <input
                        type="text"
                        value={col.dispcolnm || ''}
                        onChange={(e) => updateCol(idx, 'dispcolnm', e.target.value)}
                        style={{ width: '100%', padding: '2px 4px' }}
                      />
                    </td>
                    <td>
                      <select
                        value={col.datatypecd || 'C'}
                        onChange={(e) => updateCol(idx, 'datatypecd', e.target.value)}
                      >
                        {DATATYPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                      </select>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <input
                        type="checkbox"
                        checked={!!col.measureyn}
                        onChange={(e) => updateCol(idx, 'measureyn', e.target.checked)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {editCols.length > 0 && (
            <div className="button-group">
              <button className="icon-btn" type="button" onClick={handleSaveCols} disabled={saveCols.isPending}>
                <div className="icon-wrapper">
                  <img src="/icons/save.svg" className="icon-img save-icon" alt="저장" />
                  <span className="icon-label">컬럼 전체 저장</span>
                </div>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
