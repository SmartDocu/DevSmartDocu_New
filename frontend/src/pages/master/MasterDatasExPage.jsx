import { useEffect, useState } from 'react'
import {
  useDatasEx, useSaveExData, useDeleteData,
  useDatacols, useCreateDatacols, useSaveDatacols,
} from '@/hooks/useDatas'
import { useDocs } from '@/hooks/useDocs'
import { useAuthStore } from '@/stores/authStore'

const DATATYPE_OPTIONS = [
  { value: 'D', label: '일자' },
  { value: 'C', label: '문자' },
  { value: 'I', label: '숫자' },
]

export default function MasterDatasExPage() {
  const user = useAuthStore((s) => s.user)
  const { data: datas = [] } = useDatasEx()
  const { data: docs = [] } = useDocs()
  const saveData = useSaveExData()
  const deleteData = useDeleteData('ex')
  const createCols = useCreateDatacols()
  const saveCols = useSaveDatacols()

  // Derive project list with manager info from docs
  const projects = docs
    .map((d) => ({ projectid: d.projectid, projectnm: d.projectnm, rolecd: d.rolecd }))
    .filter((p, i, arr) => p.projectid && arr.findIndex((x) => x.projectid === p.projectid) === i)

  const [selectedData, setSelectedData] = useState(null)
  const [form, setForm] = useState({ datauid: '', datanm: '', projectid: '', projectnm: '', excelnm: '', excelurl: '' })
  const [excelFile, setExcelFile] = useState(null)
  const [fileName, setFileName] = useState('선택된 파일 없음')
  const [saving, setSaving] = useState(false)

  // Columns state (editable in-place)
  const [selectedColDatauid, setSelectedColDatauid] = useState(null)
  const { data: rawCols = [] } = useDatacols(selectedColDatauid)
  const [editCols, setEditCols] = useState([])

  useEffect(() => {
    setEditCols(rawCols.map((c) => ({ ...c })))
  }, [rawCols])

  const isManager = (projectid) => {
    const p = projects.find((x) => String(x.projectid) === String(projectid))
    return p?.rolecd === 'M'
  }

  const selectData = (d) => {
    setSelectedData(d)
    setForm({
      datauid: d.datauid, datanm: d.datanm,
      projectid: d.projectid, projectnm: d.projectnm,
      excelnm: d.excelnm || '', excelurl: d.excelurl || '',
    })
    setExcelFile(null)
    setFileName(d.excelnm || '선택된 파일 없음')
    setSelectedColDatauid(d.datauid)
  }

  const handleNew = () => {
    setSelectedData(null)
    setForm({ datauid: '', datanm: '', projectid: projects[0]?.projectid || '', projectnm: '', excelnm: '', excelurl: '' })
    setExcelFile(null)
    setFileName('선택된 파일 없음')
    setSelectedColDatauid(null)
    setEditCols([])
  }

  const handleSave = () => {
    if (!form.datanm) { alert('데이터명은 필수입니다.'); return }
    if (!excelFile && !form.datauid) { alert('첨부 파일을 선택해주세요.'); return }
    setSaving(true)
    const fd = new FormData()
    fd.append('projectid', form.projectid)
    fd.append('datanm', form.datanm)
    if (form.datauid) fd.append('datauid', form.datauid)
    if (excelFile) fd.append('excelfile', excelFile)
    saveData.mutate(fd, {
      onSuccess: (res) => {
        setSaving(false)
        const newUid = res?.datauid || form.datauid
        if (newUid) {
          createCols.mutate({ datauid: newUid })
        }
      },
      onError: () => setSaving(false),
    })
  }

  const handleDelete = () => {
    if (!form.datauid) { alert('삭제할 데이터를 선택해주세요.'); return }
    if (!window.confirm('삭제하시겠습니까?')) return
    deleteData.mutate(form.datauid, { onSuccess: handleNew })
  }

  const handleSaveCols = () => {
    if (editCols.length === 0) { alert('저장할 데이터가 없습니다.'); return }
    saveCols.mutate(editCols.map((c) => ({ ...c, datauid: selectedColDatauid })))
  }

  const updateCol = (idx, field, value) => {
    setEditCols((prev) => prev.map((c, i) => i === idx ? { ...c, [field]: value } : c))
  }

  const showSaveDelete = form.datauid && isManager(form.projectid)

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>Excel 데이터</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* Left: data cards */}
        <div style={{ flex: '25%' }}>
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
        <div style={{ flex: '35%' }}>
          <h3>데이터 상세</h3>
          <div style={{ paddingTop: 15 }}>
            <div className="form-group">
              <label htmlFor="ex-projectid">프로젝트명:</label>
              {form.datauid ? (
                <span style={{ padding: '6px 4px', fontWeight: 600 }}>{form.projectnm}</span>
              ) : (
                <select
                  id="ex-projectid"
                  value={form.projectid}
                  onChange={(e) => setForm((f) => ({ ...f, projectid: e.target.value }))}
                >
                  {projects.map((p) => <option key={p.projectid} value={p.projectid}>{p.projectnm}</option>)}
                </select>
              )}
            </div>

            <div className="form-group">
              <label htmlFor="ex-datanm">데이터명:</label>
              <input
                id="ex-datanm"
                type="text"
                value={form.datanm}
                onChange={(e) => setForm((f) => ({ ...f, datanm: e.target.value }))}
              />
            </div>

            <div className="form-group">
              <label>파일:</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <button
                  type="button"
                  className="icon-btn"
                  onClick={() => document.getElementById('ex-file-input').click()}
                >
                  <img src="/icons/upload.svg" title="업로드" className="icon-img" alt="업로드" />
                </button>
                <input
                  id="ex-file-input"
                  type="file"
                  style={{ display: 'none' }}
                  accept=".xlsx,.xls"
                  onChange={(e) => {
                    const f = e.target.files[0]
                    if (f) { setExcelFile(f); setFileName(f.name) }
                  }}
                />
                {form.excelurl ? (
                  <a
                    href="#"
                    style={{ textDecoration: 'underline' }}
                    onClick={async (e) => {
                      e.preventDefault()
                      try {
                        const res = await fetch(form.excelurl)
                        const blob = await res.blob()
                        const url = URL.createObjectURL(blob)
                        const a = document.createElement('a')
                        a.href = url; a.download = form.excelnm || 'data.xlsx'
                        document.body.appendChild(a); a.click()
                        document.body.removeChild(a); URL.revokeObjectURL(url)
                      } catch { window.open(form.excelurl, '_blank') }
                    }}
                  >
                    {fileName}
                  </a>
                ) : (
                  <span>{fileName}</span>
                )}
              </div>
            </div>

            <div className="button-group">
              <button className="icon-btn" type="button" onClick={handleNew}>
                <div className="icon-wrapper">
                  <img src="/icons/new.svg" className="icon-img new-icon" alt="신규" />
                  <span className="icon-label">신규</span>
                </div>
              </button>
              <button className="icon-btn" type="button" onClick={handleSave} disabled={saving || saveData.isPending}>
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
            </div>
          </div>
        </div>

        {/* Right: columns table */}
        <div style={{ flex: '35%' }}>
          <h3>데이터 컬럼</h3>
          <div className="table-container">
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th>원본컬럼</th>
                  <th>표현컬럼</th>
                  <th>타입</th>
                  <th>측정값여부</th>
                </tr>
              </thead>
              <tbody>
                {editCols.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center' }}>데이터를 선택해주세요</td></tr>
                ) : (
                  editCols.map((col, idx) => (
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
                  ))
                )}
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
