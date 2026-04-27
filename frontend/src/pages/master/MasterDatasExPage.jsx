import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useLangStore, t } from '@/stores/langStore'
import { useAuthStore } from '@/stores/authStore'
import { useMenus } from '@/hooks/useMenus'
import {
  useDatasEx, useSaveExData, useDeleteData,
  useDatacols, useCreateDatacols, useSaveDatacols,
} from '@/hooks/useDatas'
import { useDocs } from '@/hooks/useDocs'

const DATATYPE_OPTIONS = [
  { value: 'D', label: t('cod.keycoldatatypecd_D') },
  { value: 'C', label: t('cod.keycoldatatypecd_C') },
  { value: 'I', label: t('cod.keycoldatatypecd_I') },
]

export default function MasterDatasExPage() {
  useLangStore((s) => s.translations)
  const location = useLocation()
  const user = useAuthStore((s) => s.user)

  const { data: allMenus = [] } = useMenus()
  const currentMenu = allMenus.find((m) => m.route_path && location.pathname.includes(m.route_path))
  const menuNm = currentMenu ? (t(`mnu.${currentMenu.menucd}`) || currentMenu.default_text || '') : ''

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
    if (excelFile && form.datauid && !window.confirm(t('msg.confirm.file.overwrite'))) return
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
          <div>{menuNm}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측: 데이터 목록 */}
        <div style={{ flex: 3, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleNew}>{t('btn.new')}</button>
          </div>
          <div className="table-container" style={{ height: 'auto' }}>
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th>{t('thd.datanm')}</th>
                  <th style={{ width: '35%' }}>{t('thd.projectnm')}</th>
                </tr>
              </thead>
              <tbody>
                {datas.length === 0 ? (
                  <tr><td colSpan={2} style={{ textAlign: 'center', color: '#aaa' }}>{t('msg.no.data')}</td></tr>
                ) : datas.map((d) => (
                  <tr
                    key={d.datauid}
                    onClick={() => selectData(d)}
                    style={{ cursor: 'pointer', background: selectedData?.datauid === d.datauid ? '#e6f4ff' : '' }}
                  >
                    <td>{d.datanm}</td>
                    <td>{d.projectnm}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 중간: 데이터 상세 */}
        <div style={{ flex: 4, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saving || saveData.isPending}>
                {t('btn.save')}
              </button>
              {form.datauid && (
                <button className="btn btn-danger" type="button" onClick={handleDelete} disabled={deleteData.isPending}>
                  {t('btn.delete')}
                </button>
              )}
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="ex-projectid">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.projectnm')}:
            </label>
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
            <label htmlFor="ex-datanm">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.datanm')}:
            </label>
            <input
              id="ex-datanm"
              type="text"
              value={form.datanm}
              onChange={(e) => setForm((f) => ({ ...f, datanm: e.target.value }))}
            />
          </div>

          <div className="form-group">
            <label>
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.file')}:
            </label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => document.getElementById('ex-file-input').click()}
              >
                {t('btn.upload')}
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
        </div>

        {/* 우측: 데이터 컬럼 */}
        <div style={{ flex: 3, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.datacols')}</h3>
            {editCols.length > 0 && (
              <button className="btn btn-primary" type="button" onClick={handleSaveCols} disabled={saveCols.isPending}>
                {t('btn.save')}
              </button>
            )}
          </div>
          <div className="table-container">
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th>{t('thd.querycolnm')}</th>
                  <th>{t('thd.dispcolnm')}</th>
                  <th style={{ width: 80 }}>{t('thd.datatypecd')}</th>
                  <th style={{ width: 60 }}>{t('thd.measureyn')}</th>
                </tr>
              </thead>
              <tbody>
                {editCols.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center', color: '#aaa' }}>{t('msg.no.data')}</td></tr>
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
        </div>
      </div>
    </div>
  )
}
