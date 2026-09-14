import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { App, Spin, Select } from 'antd'
import { PlusOutlined, EyeOutlined, SaveOutlined, DeleteOutlined } from '@ant-design/icons'
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
  const languageCd = useLangStore((s) => s.languageCd)

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
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 171px)', overflow: 'hidden' }}>
      {/* 페이지 타이틀 */}
      <div className="page-title" style={{ flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{menuNm}{projectNm ? ` - ${projectNm}` : ''}</div>
        </div>
      </div>

      {/* 필터 */}
      <div className="panel-section" style={{ display: 'flex', alignItems: 'center', flexShrink: 0, marginBottom: 16 }}>
        <div className="filter-item">
          <label htmlFor="df-projectid" style={{ fontWeight: 'bold' }}>
            <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.projectnm_lbl')}
          </label>
          <Select
            id="df-projectid"
            value={projectId || undefined}
            onChange={(val) => handleProjectChange(val || '')}
            allowClear
            style={{ width: 280 }}
            placeholder={t('msg.select.project')}
            options={projects.map((p) => ({ value: String(p.projectid), label: projectLabel(p) }))}
          />
        </div>
      </div>

      {!projectId ? (
        <div style={{ padding: 24, color: '#888' }}>{t('msg.select.project')}</div>
      ) : (
      <div style={{ flex: 1, display: 'flex', gap: 24, minHeight: 0 }}>
        {/* 좌측: 데이터 목록 */}
        <div className="panel-section" style={{ flex: 3.5, display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0, overflow: 'hidden' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', height: 60, flexShrink: 0,
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
          <div className="table-container" style={{ flex: 1, height: 'auto', overflowY: 'auto' }}>
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
                    className={selected?.datauid === d.datauid ? 'selected-row' : ''}
                    style={{ cursor: 'pointer' }}
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
        <div className="panel-section" style={{ flex: 3.5, display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0, overflow: 'hidden' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', height: 60, flexShrink: 0,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <button
              className="btn btn-secondary"
              type="button"
              onClick={handlePreview}
              disabled={aiPreview.isPending}
            >
              {aiPreview.isPending ? <Spin size="small" style={{ marginRight: 6 }} /> : <EyeOutlined style={{ marginRight: 6 }} />}
              {t('btn.preview_btn')}
            </button>
          </div>

          <div style={{ flex: 1, overflowY: 'auto' }}>
          <div className="form-group" style={{ marginBottom: 10 }}>
            <label htmlFor="df-datanm">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.datanm_lbl')}:
            </label>
            <input
              id="df-datanm"
              type="text"
              value={form.datanm}
              onChange={(e) => setForm((f) => ({ ...f, datanm: e.target.value }))}
              style={{ height: 38 }}
            />
          </div>

          <div className="form-group" style={{ marginBottom: 10 }}>
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
                style={{ height: 38 }}
              >
                <option value="df">{t('cod.datasourcecd_df')}</option>
                <option value="dfv">{t('cod.datasourcecd_dfv')}</option>
              </select>
            )}
          </div>

          {form.datasourcecd === 'dfv' && (
            <div className="form-group" style={{ marginBottom: 10 }}>
              <label htmlFor="df-dfvdoc">
                <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.docnm')}:
              </label>
              <select
                id="df-dfvdoc"
                value={form.dfv_docid}
                onChange={(e) => setForm((f) => ({ ...f, dfv_docid: e.target.value }))}
                style={{ height: 38 }}
              >
                <option value="">{t('msg.select.placeholder')}</option>
                {projectDocs.map((d) => (
                  <option key={d.docid} value={d.docid}>{d.docnm}</option>
                ))}
              </select>
            </div>
          )}

          <div className="form-group" style={{ marginBottom: 10 }}>
            <label htmlFor="df-source">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.source.data')}:
            </label>
            <select
              id="df-source"
              value={form.sourcedatauid}
              onChange={(e) => setForm((f) => ({ ...f, sourcedatauid: e.target.value }))}
              style={{ height: 38 }}
            >
              <option value="">{t('msg.select.placeholder')}</option>
              {sourceDatas.map((s) => (
                <option key={s.datauid} value={s.datauid}>{s.datanm}</option>
              ))}
            </select>
          </div>

          <div className="form-group" style={{ marginBottom: 10 }}>
            <label>{t('lbl.dim.cols')}:</label>
            <div style={{ padding: '6px 4px', fontSize: 13, color: '#555' }}>
              {dimCols.map((c) => c.dispcolnm || c.querycolnm).join(', ') || '-'}
            </div>
          </div>

          <div className="form-group" style={{ marginBottom: 10 }}>
            <label>{t('lbl.measure.cols')}:</label>
            <div style={{ padding: '6px 4px', fontSize: 13, color: '#555' }}>
              {measureCols.map((c) => c.dispcolnm || c.querycolnm).join(', ') || '-'}
            </div>
          </div>

          <div className="form-group" style={{ marginBottom: 0 }}>
            <label htmlFor="df-gensentence">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.prompt')}:
            </label>
            <textarea
              id="df-gensentence"
              value={form.gensentence}
              onChange={(e) => setForm((f) => ({ ...f, gensentence: e.target.value }))}
              style={{ width: '100%', resize: 'vertical', fontSize: 13, lineHeight: '20px', height: 124 }}
            />
          </div>
          </div>
        </div>

        {/* 우측: 미리보기 결과 */}
        <div className="panel-section" style={{ flex: 3, display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0, overflow: 'hidden' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', height: 60, flexShrink: 0,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.preview_ttl')}</h3>
            {isEditYn && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button
                  className="btn btn-primary"
                  type="button"
                  onClick={handleSave}
                  disabled={isSaving || deleteDf.isPending}
                >
                  {isSaving ? <Spin size="small" style={{ marginRight: 6 }} /> : <SaveOutlined style={{ marginRight: 6 }} />}
                  {t('btn.save')}
                </button>
                {!isNew && (
                  <button
                    className="btn btn-danger"
                    type="button"
                    onClick={handleDelete}
                    disabled={deleteDf.isPending}
                    title={t('btn.delete')}
                    style={{ width: 38, height: 38, padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                  >
                    <DeleteOutlined />
                  </button>
                )}
              </div>
            )}
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>

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
                      <th style={{ width: 80, whiteSpace: 'pre-line' }}>
                        {languageCd === 'ko' ? '데이터\n타입' : t('thd.datatypecd')}
                      </th>
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
