import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { App, Spin } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useAuthStore } from '@/stores/authStore'
import { useMenus } from '@/hooks/useMenus'
import {
  useDfDatas, useSaveDfData, useSaveDfvData, useDeleteDfData,
  useAiDataPreview, useDatasSource, useDatacols,
} from '@/hooks/useDatas'

const DATATYPE_OPTIONS = [
  { value: 'I', label: t('cod.keycoldatatypecd_I') },
  { value: 'C', label: t('cod.keycoldatatypecd_C') },
  { value: 'D', label: t('cod.keycoldatatypecd_D') },
]

const EMPTY_FORM = { datauid: '', datanm: '', datasourcecd: 'df', sourcedatauid: '', gensentence: '' }

function parseCols(colsInfoJson) {
  try {
    const info = JSON.parse(colsInfoJson)
    return Object.entries(info)
      .filter(([k]) => k !== 'is_table_value')
      .map(([k, v], i) => {
        const dtype = v['데이터형'] || ''
        const datatypecd = dtype.startsWith('int') || dtype.startsWith('float') ? 'I'
          : dtype.startsWith('datetime') ? 'D' : 'C'
        return { querycolnm: k, dispcolnm: k, datatypecd, measureyn: !!v['측정값'], orderno: i + 1 }
      })
  } catch { return [] }
}

export default function MasterDatasAiPage() {
  const { modal } = App.useApp()
  useLangStore((s) => s.translations)

  const location = useLocation()
  const user = useAuthStore((s) => s.user)
  const docid = user?.docid ? Number(user.docid) : null
  const docnm = useAuthStore((s) => s.user?.docnm)
  const projectid = user?.projectid ? Number(user.projectid) : null
  const isEditYn = user?.editbuttonyn === 'Y'

  const { data: allMenus = [] } = useMenus()
  const currentMenu = allMenus.find((m) => m.route_path && location.pathname.includes(m.route_path))
  const menuNm = currentMenu ? (t(`mnu.${currentMenu.menucd}`) || currentMenu.default_text || '') : ''

  const { data: datas = [] } = useDfDatas(docid)
  const { data: sourceDatas = [] } = useDatasSource()
  const saveDf = useSaveDfData()
  const saveDfv = useSaveDfvData()
  const deleteDf = useDeleteDfData()
  const aiPreview = useAiDataPreview()

  const [selected, setSelected] = useState(null)
  const [isNew, setIsNew] = useState(true)
  const [form, setForm] = useState(EMPTY_FORM)

  const { data: sourceCols = [] } = useDatacols(form.sourcedatauid || null)
  const dimCols = sourceCols.filter((c) => !c.measureyn)
  const measureCols = sourceCols.filter((c) => c.measureyn)

  const { data: existingCols = [] } = useDatacols(form.datauid || null)
  const [previewRows, setPreviewRows] = useState([])
  const [previewCols, setPreviewCols] = useState([])
  const [isTableValue, setIsTableValue] = useState(false)

  useEffect(() => {
    if (previewCols.length === 0 && existingCols.length > 0) {
      setPreviewCols(existingCols.map((c) => ({ ...c })))
    }
  }, [existingCols])

  const handleSelect = (d) => {
    setSelected(d)
    setIsNew(false)
    setPreviewRows([])
    setPreviewCols([])
    setIsTableValue(false)
    setForm({
      datauid: d.datauid,
      datanm: d.datanm,
      datasourcecd: d.datasourcecd || 'df',
      sourcedatauid: d.sourcedatauid || '',
      gensentence: d.gensentence || '',
    })
  }

  const handleNew = () => {
    setSelected(null)
    setIsNew(true)
    setForm(EMPTY_FORM)
    setPreviewRows([])
    setPreviewCols([])
    setIsTableValue(false)
  }

  const handlePreview = () => {
    if (!form.sourcedatauid) { alert(t('msg.source.select')); return }
    if (!form.gensentence.trim()) { alert(t('msg.prompt.required')); return }
    aiPreview.mutate(
      { sourcedatauid: form.sourcedatauid, gensentence: form.gensentence, docid },
      {
        onSuccess: (data) => {
          setPreviewRows(data.rows || [])
          if (data.cols_info) {
            const parsed = parseCols(data.cols_info)
            setPreviewCols(parsed)
            try {
              const info = JSON.parse(data.cols_info)
              setIsTableValue(!!info.is_table_value)
            } catch { setIsTableValue(false) }
          } else {
            setPreviewCols([])
            setIsTableValue(false)
          }
        },
      },
    )
  }

  const handleSave = () => {
    if (!form.datanm.trim()) { alert(t('msg.datanm.required')); return }
    if (!form.sourcedatauid) { alert(t('msg.source.select')); return }
    if (!form.gensentence.trim()) { alert(t('msg.prompt.required')); return }
    if (!projectid) { alert(t('msg.doc.select')); return }

    const body = {
      datauid: form.datauid || null,
      projectid,
      datanm: form.datanm,
      sourcedatauid: form.sourcedatauid,
      gensentence: form.gensentence,
      is_multirow: isTableValue ? 'Y' : 'N',
      cols: previewCols.length > 0 ? previewCols : null,
    }

    const onSuccess = () => handleNew()

    if (form.datasourcecd === 'dfv') {
      saveDfv.mutate({ ...body, dfv_docid: docid }, { onSuccess })
    } else {
      saveDf.mutate({ ...body, docid }, { onSuccess })
    }
  }

  const handleDelete = () => {
    if (!form.datauid) { alert(t('msg.select.delete')); return }
    if (!window.confirm(t('msg.confirm.delete'))) return
    deleteDf.mutate({ datauid: form.datauid, docid }, { onSuccess: handleNew })
  }

  const updateCol = (idx, field, value) => {
    setPreviewCols((prev) => prev.map((c, i) => (i === idx ? { ...c, [field]: value } : c)))
  }

  const isSaving = saveDf.isPending || saveDfv.isPending

  const previewColKeys = previewRows.length > 0 ? Object.keys(previewRows[0]) : []

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{menuNm}{docnm ? ` - ${docnm}` : ''}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측: 데이터 목록 */}
        <div style={{ flex: 3, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleNew}>
              {t('btn.new')}
            </button>
          </div>
          <div className="table-container" style={{ height: 'auto' }}>
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th>{t('thd.datanm')}</th>
                  <th style={{ width: 80 }}>{t('thd.datasourcecd')}</th>
                </tr>
              </thead>
              <tbody>
                {datas.length === 0 ? (
                  <tr><td colSpan={2} style={{ textAlign: 'center' }}>{t('msg.no.data')}</td></tr>
                ) : datas.map((d) => (
                  <tr
                    key={d.datauid}
                    onClick={() => handleSelect(d)}
                    style={{ cursor: 'pointer', background: selected?.datauid === d.datauid ? '#e6f4ff' : '' }}
                  >
                    <td>{d.datanm}</td>
                    <td style={{ textAlign: 'center' }}>
                      {d.datasourcecd === 'dfv' ? t('cod.datasourcecd_dfv') : t('cod.datasourcecd_df')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 중간: 입력 폼 */}
        <div style={{ flex: 3, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <button
              className="btn btn-primary"
              type="button"
              onClick={handlePreview}
              disabled={aiPreview.isPending}
            >
              {aiPreview.isPending && <Spin size="small" style={{ marginRight: 4 }} />}
              {t('btn.preview')}
            </button>
          </div>

          <div className="form-group">
            <label htmlFor="df-datanm">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.datanm')}:
            </label>
            <input
              id="df-datanm"
              type="text"
              value={form.datanm}
              onChange={(e) => setForm((f) => ({ ...f, datanm: e.target.value }))}
            />
          </div>

          <div className="form-group">
            <label htmlFor="df-datasourcecd">{t('lbl.datasourcecd')}:</label>
            {!isNew ? (
              <span style={{ padding: '6px 4px', fontWeight: 600 }}>
                {form.datasourcecd === 'dfv' ? t('cod.datasourcecd_dfv') : t('cod.datasourcecd_df')}
              </span>
            ) : (
              <select
                id="df-datasourcecd"
                value={form.datasourcecd}
                onChange={(e) => setForm((f) => ({ ...f, datasourcecd: e.target.value }))}
              >
                <option value="df">{t('cod.datasourcecd_df')}</option>
                <option value="dfv">{t('cod.datasourcecd_dfv')}</option>
              </select>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="df-source">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.source.data')}:
            </label>
            <select
              id="df-source"
              value={form.sourcedatauid}
              onChange={(e) => setForm((f) => ({ ...f, sourcedatauid: e.target.value }))}
            >
              <option value="">{t('msg.select.placeholder')}</option>
              {sourceDatas.map((s) => (
                <option key={s.datauid} value={s.datauid}>{s.datanm}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>{t('lbl.dim.cols')}:</label>
            <div style={{ padding: '6px 4px', fontSize: 13, color: '#555' }}>
              {dimCols.map((c) => c.dispcolnm || c.querycolnm).join(', ') || '-'}
            </div>
          </div>

          <div className="form-group">
            <label>{t('lbl.measure.cols')}:</label>
            <div style={{ padding: '6px 4px', fontSize: 13, color: '#555' }}>
              {measureCols.map((c) => c.dispcolnm || c.querycolnm).join(', ') || '-'}
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="df-gensentence">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.prompt')}:
            </label>
            <textarea
              id="df-gensentence"
              rows={8}
              value={form.gensentence}
              onChange={(e) => setForm((f) => ({ ...f, gensentence: e.target.value }))}
              style={{ width: '100%', resize: 'vertical' }}
            />
          </div>
        </div>

        {/* 우측: 미리보기 결과 */}
        <div style={{ flex: 4, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.preview')}</h3>
            {isEditYn && (
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  className="btn btn-primary"
                  type="button"
                  onClick={handleSave}
                  disabled={isSaving}
                >
                  {isSaving && <Spin size="small" style={{ marginRight: 4 }} />}
                  {t('btn.save')}
                </button>
                {!isNew && (
                  <button
                    className="btn btn-danger"
                    type="button"
                    onClick={handleDelete}
                    disabled={deleteDf.isPending}
                  >
                    {t('btn.delete')}
                  </button>
                )}
              </div>
            )}
          </div>

          {previewRows.length > 0 && (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 28, marginBottom: 4 }}>
                <h3 style={{ margin: 0 }}>{t('ttl.data.preview')}</h3>
                <div />
              </div>
              <div className="table-container" style={{ height: 'auto', marginBottom: 12 }}>
                <table className="table table-bordered table-sm">
                  <thead>
                    <tr>
                      {previewColKeys.map((k) => <th key={k}>{k}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {previewRows.slice(0, 10).map((row, i) => (
                      <tr key={i}>
                        {previewColKeys.map((k) => <td key={k}>{row[k] ?? ''}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {previewCols.length > 0 && (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 28, marginBottom: 4 }}>
                <h3 style={{ margin: 0 }}>{t('ttl.col.info')}</h3>
                <div />
              </div>
              <div className="table-container" style={{ height: 'auto' }}>
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
                    {previewCols.map((col, idx) => (
                      <tr key={col.querycolnm}>
                        <td>{col.querycolnm}</td>
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
                            {DATATYPE_OPTIONS.map((o) => (
                              <option key={o.value} value={o.value}>{o.label}</option>
                            ))}
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
            </>
          )}

          {previewCols.length === 0 && previewRows.length === 0 && (
            <div style={{ color: '#bbb', fontSize: 13, paddingTop: 12 }}>
              {t('inf.preview.empty')}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
