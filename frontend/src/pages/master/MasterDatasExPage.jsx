import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { App } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useAuthStore } from '@/stores/authStore'
import { useMenus, useMenuCodes } from '@/hooks/useMenus'
import {
  useDatasEx, useSaveExData, useDeleteData,
  useDatacols, useCreateDatacols, useSaveDatacols,
} from '@/hooks/useDatas'

const EMPTY_COLS = []

export default function MasterDatasExPage() {
  const { message } = App.useApp()
  useLangStore((s) => s.translations)

  const { data: datatypeOptions = [] } = useMenuCodes('keycoldatatypecd')

  const location = useLocation()
  const user = useAuthStore((s) => s.user)

  const { data: allMenus = [] } = useMenus()
  const currentMenu = allMenus.find((m) => m.route_path && location.pathname.includes(m.route_path))
  const menuNm = currentMenu ? (t(`mnu.${currentMenu.menucd}`) || currentMenu.default_text || '') : ''

  const { data: datas = [] } = useDatasEx()
  const saveData = useSaveExData()
  const deleteData = useDeleteData('ex')
  const createCols = useCreateDatacols()
  const saveCols = useSaveDatacols()

  const [selectedData, setSelectedData] = useState(null)
  const [form, setForm] = useState({ datauid: '', datanm: '', excelnm: '', excelurl: '' })
  const [excelFile, setExcelFile] = useState(null)
  const [fileName, setFileName] = useState(null)
  const [saving, setSaving] = useState(false)

  // Columns state (editable in-place)
  const [selectedColDatauid, setSelectedColDatauid] = useState(null)
  const { data: rawCols = EMPTY_COLS } = useDatacols(selectedColDatauid)
  const [editCols, setEditCols] = useState([])

  useEffect(() => {
    setEditCols(rawCols.map((c) => ({ ...c })))
  }, [rawCols])

  const selectData = (d) => {
    setSelectedData(d)
    setForm({
      datauid: d.datauid, datanm: d.datanm,
      excelnm: d.excelnm || '', excelurl: d.excelurl || '',
    })
    setExcelFile(null)
    setFileName(d.excelnm || null)
    setSelectedColDatauid(d.datauid)
  }

  const handleNew = () => {
    setSelectedData(null)
    setForm({ datauid: '', datanm: '', excelnm: '', excelurl: '' })
    setExcelFile(null)
    setFileName(null)
    setSelectedColDatauid(null)
    setEditCols([])
  }

  const handleSave = async () => {
    if (!form.datanm) { alert(t('msg.datanm.required')); return }
    if (!excelFile && !form.datauid) { alert(t('msg.file.required')); return }
    if (excelFile && form.datauid && !window.confirm(t('msg.confirm.file.overwrite'))) return
    setSaving(true)
    const fd = new FormData()
    fd.append('datanm', form.datanm)
    if (form.datauid) fd.append('datauid', form.datauid)
    if (user?.accountuid) fd.append('accountuid', user.accountuid)
    if (excelFile) fd.append('excelfile', excelFile)
    try {
      const res = await saveData.mutateAsync(fd)
      const newUid = res?.datauid || form.datauid
      if (newUid) {
        try {
          await createCols.mutateAsync({ datauid: newUid })
        } catch {
          message.warning(t('msg.save.col.warn'))
        }
      }
    } catch {
      // saveData의 onError에서 이미 메시지 처리함
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!form.datauid) { alert(t('msg.select.data')); return }
    if (!window.confirm(t('msg.confirm.delete'))) return
    try {
      await deleteData.mutateAsync(form.datauid)
      handleNew()
    } catch {
      // deleteData의 onError에서 이미 메시지 처리함
    }
  }

  const handleSaveCols = () => {
    if (editCols.length === 0) { alert(t('msg.no.data.to.save')); return }
    saveCols.mutate(editCols.map((c) => ({ ...c, datauid: selectedColDatauid })))
  }

  const updateCol = (idx, field, value) => {
    setEditCols((prev) => prev.map((c, i) => i === idx ? { ...c, [field]: value } : c))
  }

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
                  <th>{t('thd.datanm_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {datas.length === 0 ? (
                  <tr><td colSpan={1} style={{ textAlign: 'center', color: '#aaa' }}>{t('msg.no.data')}</td></tr>
                ) : datas.map((d) => (
                  <tr
                    key={d.datauid}
                    onClick={() => selectData(d)}
                    style={{ cursor: 'pointer', background: selectedData?.datauid === d.datauid ? '#e6f4ff' : '' }}
                  >
                    <td>{d.datanm}</td>
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
            <label htmlFor="ex-datanm">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.datanm_lbl')}:
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
                {t('btn.upload_btn')}
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
                  {fileName || t('msg.no.file.selected')}
                </a>
              ) : (
                <span>{fileName || t('msg.no.file.selected')}</span>
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
                          value={col.datatypecd || 'string'}
                          onChange={(e) => updateCol(idx, 'datatypecd', e.target.value)}
                        >
                          {datatypeOptions.map((c) => <option key={c.codevalue} value={c.codevalue}>{t(c.term_key) || c.default_name}</option>)}
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
