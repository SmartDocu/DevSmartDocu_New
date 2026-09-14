import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { App } from 'antd'
import { PlusOutlined, SaveOutlined, DeleteOutlined, UploadOutlined } from '@ant-design/icons'
import { useLangStore, t } from '@/stores/langStore'
import { useAuthStore } from '@/stores/authStore'
import { useMenus, useMenuCodes } from '@/hooks/useMenus'
import {
  useDatasEx, useSaveExData, useDeleteData,
  useDatacols, useCreateDatacols, useSaveDatacols,
} from '@/hooks/useDatas'

const EMPTY_COLS = []

export default function MasterDatasExPage() {
  const { message, modal } = App.useApp()
  useLangStore((s) => s.translations)
  const languageCd = useLangStore((s) => s.languageCd)

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

  const handleSave = () => {
    if (!form.datanm) { message.warning(t('msg.datanm.required')); return }
    if (!excelFile && !form.datauid) { message.warning(t('msg.file.required')); return }

    const doSave = async () => {
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

    if (excelFile && form.datauid) {
      modal.confirm({
        content: t('msg.confirm.file.overwrite'),
        onOk: doSave,
      })
      return
    }
    doSave()
  }

  const handleDelete = () => {
    if (!form.datauid) { message.warning(t('msg.select.data')); return }
    modal.confirm({
      content: t('msg.confirm.delete'),
      onOk: async () => {
        try {
          await deleteData.mutateAsync(form.datauid)
          handleNew()
        } catch {
          // deleteData의 onError에서 이미 메시지 처리함
        }
      },
    })
  }

  const handleSaveCols = () => {
    if (editCols.length === 0) { message.warning(t('msg.no.data.to.save')); return }
    saveCols.mutate(editCols.map((c) => ({ ...c, datauid: selectedColDatauid })))
  }

  const updateCol = (idx, field, value) => {
    setEditCols((prev) => prev.map((c, i) => i === idx ? { ...c, [field]: value } : c))
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{menuNm}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
        {/* 좌측: 데이터 목록 */}
        <div className="panel-section" style={{ flex: 3, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 224px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h3 style={{ margin: 0, lineHeight: 1 }}>{t('ttl.list')}</h3>
              <span style={{
                display: 'inline-flex', alignItems: 'center', lineHeight: 1,
                font: '500 11px monospace', color: '#8d9199', background: '#f2efe9',
                borderRadius: 6, padding: '5px 8px 4px',
              }}>
                {t('lbl.count.docs').replace('{n}', datas.length)}
              </span>
            </div>
            <button className="btn btn-primary" type="button" onClick={handleNew}>
              <PlusOutlined style={{ marginRight: 6 }} />{t('btn.new')}
            </button>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
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
                    className={selectedData?.datauid === d.datauid ? 'selected-row' : ''}
                    style={{ cursor: 'pointer' }}
                  >
                    <td>{d.datanm}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </div>
        </div>

        {/* 중간: 데이터 상세 */}
        <div className="panel-section" style={{ flex: 4, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 224px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saving || saveData.isPending || deleteData.isPending}>
                <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
              </button>
              {form.datauid && (
                <button
                  className="btn btn-danger"
                  type="button"
                  onClick={handleDelete}
                  disabled={deleteData.isPending}
                  title={t('btn.delete')}
                  style={{ width: 38, height: 38, padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                >
                  <DeleteOutlined />
                </button>
              )}
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>

          <div className="form-group">
            <label htmlFor="ex-datanm">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.datanm_lbl')}:
            </label>
            <input
              id="ex-datanm"
              type="text"
              value={form.datanm}
              style={{ height: 38 }}
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
                <UploadOutlined style={{ marginRight: 6 }} />{t('btn.upload_btn')}
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
        </div>

        {/* 우측: 데이터 컬럼 */}
        <div className="panel-section" style={{ flex: 3, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 224px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.datacols')}</h3>
            {editCols.length > 0 && (
              <button className="btn btn-primary" type="button" onClick={handleSaveCols} disabled={saveCols.isPending}>
                <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
              </button>
            )}
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th>{t('thd.querycolnm')}</th>
                  <th>{t('thd.dispcolnm')}</th>
                  <th style={{ width: 80, whiteSpace: 'pre-line' }}>
                    {languageCd === 'ko' ? '데이터\n타입' : t('thd.datatypecd')}
                  </th>
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
    </div>
  )
}
