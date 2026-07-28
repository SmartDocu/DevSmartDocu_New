import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { App, Spin } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useAuthStore } from '@/stores/authStore'
import { useMenus, useMenuCodes } from '@/hooks/useMenus'
import { useDocs, useProjects } from '@/hooks/useDocs'
import {
  useDfDatas, useSaveDfData, useSaveDfvData, useDeleteDfData,
  useAiDataPreview, useDatasSource, useDatacols,
} from '@/hooks/useDatas'


const EMPTY_FORM = { datauid: '', datanm: '', datasourcecd: 'df', sourcedatauid: '', gensentence: '', dfv_docid: '' }

function parseCols(colsInfoJson) {
  try {
    const info = JSON.parse(colsInfoJson)
    return Object.entries(info)
      .filter(([k]) => k !== 'is_table_value')
      .map(([k, v], i) => {
        const dtype = v['데이터형'] || ''
        const datatypecd = dtype.startsWith('int') || dtype.startsWith('float') ? 'number'
          : dtype.startsWith('datetime') ? 'datetime' : 'string'
        return { querycolnm: k, dispcolnm: k, datatypecd, measureyn: !!v['측정값'], orderno: i + 1 }
      })
  } catch { return [] }
}

export default function MasterDatasAiPage() {
  const { message, modal } = App.useApp()
  useLangStore((s) => s.translations)
  const translationVersion = useLangStore((s) => s.translationVersion)

  const { data: datatypeOptions = [] } = useMenuCodes('keycoldatatypecd')
  const { data: serviceCodes = [] } = useMenuCodes('servicecd')
  const serviceLabel = (servicecd) => {
    const c = serviceCodes.find((sc) => sc.codevalue === servicecd)
    return c ? (t(c.term_key) || c.default_name) : servicecd
  }
  const projectLabel = (p) => p.servicecd ? `${p.projectnm} - ${serviceLabel(p.servicecd)}` : p.projectnm

  const location = useLocation()
  const user = useAuthStore((s) => s.user)
  const isEditYn = user?.editbuttonyn === 'Y'

  const { data: allMenus = [] } = useMenus()
  const currentMenu = allMenus.find((m) => m.route_path && location.pathname.includes(m.route_path))
  const menuNm = currentMenu ? (t(`mnu.${currentMenu.menucd}`) || currentMenu.default_text || '') : ''

  const { data: projects = [] } = useProjects()
  const { data: allDocs = [] } = useDocs()
  const [projectId, setProjectId] = useState('')
  const projectIdNum = projectId ? Number(projectId) : null
  const selectedProject = projects.find((p) => String(p.projectid) === String(projectId))
  const projectNm = selectedProject ? projectLabel(selectedProject) : ''
  const projectDocs = allDocs.filter((d) => String(d.projectid) === String(projectId))

  const { data: datas = [] } = useDfDatas(projectIdNum)
  const { data: sourceDatas = [] } = useDatasSource(projectIdNum)
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
    if (existingCols.length > 0) {
      setPreviewCols(existingCols.map((c) => ({ ...c })))
    }
  }, [form.datauid, existingCols])

  useEffect(() => {
    if (!isNew) return
    const raw = t('inf.gensentence.default')
    if (raw === 'inf.gensentence.default') return  // 번역 아직 미로드
    setForm((f) => ({ ...f, gensentence: raw.replace(/\\n/g, '\n') }))
  }, [translationVersion])

  const handleSelect = (d) => {
    setSelected(d)
    setIsNew(false)
    setPreviewRows([])
    setPreviewCols([])
    setIsTableValue(d.is_multirow === true || d.is_multirow === 'Y')
    setForm({
      datauid: d.datauid,
      datanm: d.datanm,
      datasourcecd: d.datasourcecd || 'df',
      sourcedatauid: d.sourcedatauid || '',
      gensentence: d.gensentence || '',
      dfv_docid: d.dfv_docid ? String(d.dfv_docid) : '',
    })
  }

  const handleNew = () => {
    setSelected(null)
    setIsNew(true)
    setForm({ ...EMPTY_FORM, gensentence: t('inf.gensentence.default').replace(/\\n/g, '\n') })
    setPreviewRows([])
    setPreviewCols([])
    setIsTableValue(false)
  }

  const handleProjectChange = (val) => {
    setProjectId(val)
    handleNew()
  }

  const handlePreview = () => {
    if (!form.sourcedatauid) { message.warning(t('msg.source.select')); return }
    if (!form.gensentence.trim()) { message.warning(t('msg.prompt.required')); return }
    const previewDocid = form.datasourcecd === 'dfv' && form.dfv_docid ? Number(form.dfv_docid) : null
    aiPreview.mutate(
      { sourcedatauid: form.sourcedatauid, gensentence: form.gensentence, docid: previewDocid, projectid: projectIdNum },
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
    if (!projectIdNum) { message.warning(t('msg.select.project')); return }
    if (!form.datanm.trim()) { message.warning(t('msg.datanm.required')); return }
    if (!form.sourcedatauid) { message.warning(t('msg.source.select')); return }
    if (!form.gensentence.trim()) { message.warning(t('msg.prompt.required')); return }
    if (form.datasourcecd === 'dfv' && !form.dfv_docid) { message.warning(t('msg.doc.select')); return }

    const body = {
      datauid: form.datauid || null,
      projectid: projectIdNum,
      datanm: form.datanm,
      sourcedatauid: form.sourcedatauid,
      gensentence: form.gensentence,
      is_multirow: isTableValue ? 'Y' : 'N',
      cols: previewCols.length > 0 ? previewCols : null,
    }

    const onSuccess = () => handleNew()

    if (form.datasourcecd === 'dfv') {
      saveDfv.mutate({ ...body, dfv_docid: Number(form.dfv_docid) }, { onSuccess })
    } else {
      saveDf.mutate(body, { onSuccess })
    }
  }

  const handleDelete = () => {
    if (!form.datauid) { message.warning(t('msg.select.delete')); return }
    modal.confirm({
      content: t('msg.confirm.delete'),
      onOk: () => { deleteDf.mutate({ datauid: form.datauid, projectid: projectIdNum }, { onSuccess: handleNew }) },
    })
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
          <div>{menuNm}{projectNm ? ` - ${projectNm}` : ''}</div>
        </div>
      </div>

      <div className="form-group" style={{ maxWidth: 320, marginBottom: 20 }}>
        <label htmlFor="df-projectid">
          <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.projectnm_lbl')}:
        </label>
        <select
          id="df-projectid"
          value={projectId}
          onChange={(e) => handleProjectChange(e.target.value)}
        >
          <option value="">{t('msg.select.project')}</option>
          {projects.map((p) => (
            <option key={p.projectid} value={p.projectid}>{projectLabel(p)}</option>
          ))}
        </select>
      </div>

      {!projectId ? (
        <div style={{ padding: 24, color: '#888' }}>{t('msg.select.project')}</div>
      ) : (
      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측: 데이터 목록 */}
        <div style={{ flex: 3.5, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
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
                  <th style={{ width: 150 }}>{t('thd.datanm_thd')}</th>
                  <th style={{ width: 150 }}>{t('thd.datasourcecd_thd')}</th>
                  <th style={{ width: 60 }}>{t('thd.docnm_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {datas.length === 0 ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center' }}>{t('msg.no.data')}</td></tr>
                ) : datas.map((d) => (
                  <tr
                    key={d.datauid}
                    onClick={() => handleSelect(d)}
                    style={{ cursor: 'pointer', background: selected?.datauid === d.datauid ? 'var(--selected-row-bg)' : '', color: selected?.datauid === d.datauid ? 'var(--selected-row)' : '' }}
                  >
                    <td>{d.datanm}</td>
                    <td style={{ textAlign: 'center' }}>
                      {d.datasourcecd === 'dfv' ? t('cod.datasourcecd_dfv') : t('cod.datasourcecd_df')}
                    </td>
                    <td>
                      {d.datasourcecd === 'dfv'
                        ? (allDocs.find((doc) => String(doc.docid) === String(d.dfv_docid))?.docnm || '-')
                        : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 중간: 입력 폼 */}
        <div style={{ flex: 3.5, display: 'flex', flexDirection: 'column', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8, flexShrink: 0 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <button
              className="btn btn-primary"
              type="button"
              onClick={handlePreview}
              disabled={aiPreview.isPending}
            >
              {aiPreview.isPending && <Spin size="small" style={{ marginRight: 4 }} />}
              {t('btn.preview_btn')}
            </button>
          </div>

          <div style={{ flex: 1, overflowY: 'auto' }}>
          <div className="form-group">
            <label htmlFor="df-datanm">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.datanm_lbl')}:
            </label>
            <input
              id="df-datanm"
              type="text"
              value={form.datanm}
              onChange={(e) => setForm((f) => ({ ...f, datanm: e.target.value }))}
            />
          </div>

          <div className="form-group">
            <label htmlFor="df-datasourcecd">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.datasourcecd_lbl')}:
            </label>
            {!isNew ? (
              <span style={{ padding: '6px 4px', fontWeight: 600 }}>
                {form.datasourcecd === 'dfv' ? t('cod.datasourcecd_dfv') : t('cod.datasourcecd_df')}
              </span>
            ) : (
              <select
                id="df-datasourcecd"
                value={form.datasourcecd}
                onChange={(e) => setForm((f) => ({ ...f, datasourcecd: e.target.value, dfv_docid: '' }))}
              >
                <option value="df">{t('cod.datasourcecd_df')}</option>
                <option value="dfv">{t('cod.datasourcecd_dfv')}</option>
              </select>
            )}
          </div>

          {form.datasourcecd === 'dfv' && (
            <div className="form-group">
              <label htmlFor="df-dfvdoc">
                <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.docnm')}:
              </label>
              <select
                id="df-dfvdoc"
                value={form.dfv_docid}
                onChange={(e) => setForm((f) => ({ ...f, dfv_docid: e.target.value }))}
              >
                <option value="">{t('msg.select.placeholder')}</option>
                {projectDocs.map((d) => (
                  <option key={d.docid} value={d.docid}>{d.docnm}</option>
                ))}
              </select>
            </div>
          )}

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
              rows={13}
              value={form.gensentence}
              onChange={(e) => setForm((f) => ({ ...f, gensentence: e.target.value }))}
              style={{ width: '100%', resize: 'vertical' }}
            />
          </div>
          </div>
        </div>

        {/* 우측: 미리보기 결과 */}
        <div style={{ flex: 3, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.preview_ttl')}</h3>
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

          {form.datasourcecd === 'dfv' && (previewRows.length > 0 || previewCols.length > 0) && (
            <div style={{ marginBottom: 8, fontSize: 13, fontWeight: 600 }}>
              {isTableValue ? t('cod.is_multirow_y') : t('cod.is_multirow_n')}
            </div>
          )}

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
                            value={col.datatypecd || 'string'}
                            onChange={(e) => updateCol(idx, 'datatypecd', e.target.value)}
                          >
                            {datatypeOptions.map((c) => (
                              <option key={c.codevalue} value={c.codevalue}>{t(c.term_key) || c.default_name}</option>
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
      )}

      {aiPreview.isPending && (
        <div style={{
          position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
          background: 'rgba(255,255,255,0.6)',
          display: 'flex', justifyContent: 'center', alignItems: 'center',
          zIndex: 9999,
        }}>
          <Spin size="large" />
        </div>
      )}
    </div>
  )
}
