import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { App, Spin } from 'antd'
import { PlusOutlined, SaveOutlined, DeleteOutlined } from '@ant-design/icons'
import { useLangStore, t } from '@/stores/langStore'
import { useAuthStore } from '@/stores/authStore'
import { useMenus, useMenuCodes } from '@/hooks/useMenus'
import {
  useDatasApi, useApiConnectors,
  useSaveApiData, useDeleteData,
  useDatacols, useSaveDatacols, useCreateDatacols,
  useApiParams,
} from '@/hooks/useDatas'

const EMPTY_FORM = {
  datauid: '', connuid: '', datanm: '', endpoint: '', desc: '', useyn: true,
}

const EMPTY_PARAM = {
  paramnm: '', param_locationcd: 'query', datatypecd: 'string',
  is_required: false, testvalue: '', is_fixed: false, fixed_value: '', desc: '',
}

export default function MasterDatasApiPage() {
  const { data: datatypeOptions = [] } = useMenuCodes('keycoldatatypecd')
  const { message, modal } = App.useApp()
  useLangStore((s) => s.translations)
  const languageCd = useLangStore((s) => s.languageCd)

  const location = useLocation()
  const user = useAuthStore((s) => s.user)
  const isEditYn = user?.editbuttonyn === 'Y'

  const { data: allMenus = [] } = useMenus()
  const currentMenu = allMenus.find((m) => m.route_path && location.pathname.includes(m.route_path))
  const menuNm = currentMenu ? (currentMenu.default_text || '') : t('ttl.master_data.data.api')

  const { data: paramLocations = [] } = useMenuCodes('param_locationcd')
  const { data: datas = [], isLoading } = useDatasApi()
  const { data: connectors = [] } = useApiConnectors()
  const saveData   = useSaveApiData()
  const deleteData = useDeleteData('api')
  const createCols = useCreateDatacols()
  const saveCols   = useSaveDatacols()

  const [form,        setForm]        = useState(EMPTY_FORM)
  const [selectedUid, setSelectedUid] = useState(null)
  const [paramsLocal, setParamsLocal] = useState([])
  const [colsLocal,   setColsLocal]   = useState([])

  const { data: datacols } = useDatacols(selectedUid)
  const { data: apiparams } = useApiParams(selectedUid)

  useEffect(() => {
    setColsLocal((datacols || []).map((c) => ({ ...c })))
  }, [datacols])

  useEffect(() => {
    setParamsLocal((apiparams || []).map((p) => ({ ...p })))
  }, [apiparams])

  const handleRowClick = (row) => {
    setSelectedUid(row.datauid)
    setForm({
      datauid:   row.datauid   || '',
      connuid:   row.connuid   || '',
      datanm:    row.datanm    || '',
      endpoint:  row.endpoint  || '',
      desc:      row.desc      || '',
      useyn:     row.useyn !== false,
    })
  }

  const handleNew = () => {
    setSelectedUid(null)
    setForm({ ...EMPTY_FORM })
    setParamsLocal([])
    setColsLocal([])
  }

  const handleSave = () => {
    if (!form.datanm.trim()) {
      message.warning(t('msg.db.required'))
      return
    }
    const body = {
      datauid:   form.datauid   || null,
      datanm:    form.datanm,
      connuid:   form.connuid   || null,
      endpoint:  form.endpoint  || null,
      desc:      form.desc      || null,
      useyn:     form.useyn,
      params:    paramsLocal.filter((p) => p.paramnm.trim()).map((p, i) => ({
        paramnm:          p.paramnm,
        param_locationcd: p.param_locationcd || 'query',
        datatypecd:       p.datatypecd || 'string',
        is_required:      !!p.is_required,
        testvalue:        p.testvalue || null,
        is_fixed:         !!p.is_fixed,
        fixed_value:      p.fixed_value || null,
        desc:             p.desc || null,
        orderno:          i + 1,
      })),
    }
    saveData.mutate(body, {
      onSuccess: (res) => {
        const savedUid = res.datauid || form.datauid
        setSelectedUid(savedUid)
        setForm((f) => ({ ...f, datauid: savedUid }))
        createCols.mutate({ datauid: savedUid }, {
          onSuccess: () => { message.success(t('msg.save.success')) },
          onError: () => { message.warning(t('msg.save.col.warn')) },
        })
      },
    })
  }

  const handleDelete = () => {
    if (!form.datauid) { message.warning(t('msg.select.delete')); return }
    modal.confirm({
      content: t('msg.confirm.delete'),
      onOk: () => {
        deleteData.mutate(form.datauid, {
          onSuccess: () => { handleNew() },
        })
      },
    })
  }

  const handleSaveCols = () => {
    if (!selectedUid) { message.warning(t('msg.select.data')); return }
    const validCols = colsLocal.filter((c) => c.querycolnm?.trim())
    if (validCols.length === 0) { message.warning(t('msg.col.empty')); return }
    const payload = validCols.map((c, i) => ({
      datauid:    selectedUid,
      querycolnm: c.querycolnm,
      dispcolnm:  c.dispcolnm || c.querycolnm,
      datatypecd: c.datatypecd || 'string',
      measureyn:  !!c.measureyn,
      useyn:      c.useyn !== false,
      orderno:    i + 1,
      field_path: c.field_path || null,
    }))
    saveCols.mutate(payload)
  }

  const addParam = () => setParamsLocal((p) => [...p, { ...EMPTY_PARAM }])
  const removeParam = (i) => setParamsLocal((p) => p.filter((_, idx) => idx !== i))
  const updateParam = (i, field, value) =>
    setParamsLocal((p) => p.map((row, idx) => idx === i ? { ...row, [field]: value } : row))

  const removeCol = (i) => setColsLocal((c) => c.filter((_, idx) => idx !== i))
  const updateCol = (i, field, value) =>
    setColsLocal((c) => c.map((row, idx) => idx === i ? { ...row, [field]: value } : row))

  const tdStyle = { padding: '2px 4px' }
  const inputStyle = { width: '100%', padding: '2px 4px', boxSizing: 'border-box' }

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

        {/* ── 왼쪽: 목록 ── */}
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
                  <th>{t('thd.connnm_thd')}</th>
                  <th>{t('thd.datanm_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={2} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : datas.length === 0 ? (
                  <tr><td colSpan={2} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : datas.map((d) => (
                  <tr key={d.datauid}
                    className={selectedUid === d.datauid ? 'selected-row' : ''}
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleRowClick(d)}
                  >
                    <td>{d.connnm || ''}</td>
                    <td>{d.datanm}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </div>
        </div>

        {/* ── 가운데: 상세 폼 + 파라미터 ── */}
        <div className="panel-section" style={{ flex: 3.5, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 224px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            {isEditYn && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button className="btn btn-primary" type="button" onClick={handleSave}
                  disabled={saveData.isPending || createCols.isPending || deleteData.isPending}>
                  {(saveData.isPending || createCols.isPending) ? <Spin size="small" style={{ marginRight: 6 }} /> : <SaveOutlined style={{ marginRight: 6 }} />}
                  {t('btn.save')}
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
            )}
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>

          <div className="form-group">
            <label>{t('lbl.connnm_lbl')}</label>
            <select value={form.connuid} style={{ height: 38 }}
              onChange={(e) => setForm((f) => ({ ...f, connuid: e.target.value }))}>
              <option value="">{t('msg.select.placeholder')}</option>
              {connectors.map((c) => (
                <option key={c.connuid} value={c.connuid}>{c.connnm}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.datanm_lbl')}</label>
            <input type="text" value={form.datanm} style={{ height: 38 }}
              onChange={(e) => setForm((f) => ({ ...f, datanm: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.endpoint_lbl')}</label>
            <input type="text" value={form.endpoint} placeholder="/v1/users" style={{ height: 38 }}
              onChange={(e) => setForm((f) => ({ ...f, endpoint: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.desc_lbl')}</label>
            <textarea rows={3} style={{ resize: 'vertical' }} value={form.desc}
              onChange={(e) => setForm((f) => ({ ...f, desc: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.useyn_lbl')}:</label>
            <div style={{ paddingLeft: 60 }}>
              <input type="checkbox" checked={form.useyn}
                onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))} />
            </div>
          </div>

          <hr style={{ margin: '16px 0', borderColor: '#f0f0f0' }} />

          {/* 파라미터 */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h4 style={{ margin: 0 }}>{t('ttl.api.params')}</h4>
            {isEditYn && (
              <button className="btn btn-primary" type="button" style={{ padding: '4px 10px', height: 32 }} onClick={addParam}>
                {t('btn.add')}
              </button>
            )}
          </div>
          <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th>{t('thd.paramnm_thd')}</th>
                  <th style={{ width: '18%' }}>{t('thd.param_location_thd')}</th>
                  <th style={{ width: '10%' }}>{t('thd.is_required_thd')}</th>
                  <th style={{ width: '10%' }}>{t('thd.is_fixed_thd')}</th>
                  <th>{t('thd.fixed_value_thd')}</th>
                  <th>{t('thd.testvalue_thd')}</th>
                  {isEditYn && <th style={{ width: 28 }} />}
                </tr>
              </thead>
              <tbody>
                {paramsLocal.length === 0 ? (
                  <tr><td colSpan={isEditYn ? 7 : 6} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : paramsLocal.map((p, i) => (
                  <tr key={i}>
                    <td style={tdStyle}>
                      <input style={inputStyle} type="text" value={p.paramnm}
                        onChange={(e) => updateParam(i, 'paramnm', e.target.value)} />
                    </td>
                    <td style={tdStyle}>
                      <select style={inputStyle} value={p.param_locationcd}
                        onChange={(e) => updateParam(i, 'param_locationcd', e.target.value)}>
                        {paramLocations.map((c) => <option key={c.codevalue} value={c.codevalue}>{t(c.term_key) || c.default_name}</option>)}
                      </select>
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                      <input type="checkbox" checked={!!p.is_required}
                        onChange={(e) => updateParam(i, 'is_required', e.target.checked)} />
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                      <input type="checkbox" checked={!!p.is_fixed}
                        onChange={(e) => updateParam(i, 'is_fixed', e.target.checked)} />
                    </td>
                    <td style={tdStyle}>
                      <input style={inputStyle} type="text" value={p.fixed_value || ''}
                        disabled={!p.is_fixed}
                        onChange={(e) => updateParam(i, 'fixed_value', e.target.value)} />
                    </td>
                    <td style={tdStyle}>
                      <input style={inputStyle} type="text" value={p.testvalue || ''}
                        onChange={(e) => updateParam(i, 'testvalue', e.target.value)} />
                    </td>
                    {isEditYn && (
                      <td style={{ ...tdStyle, textAlign: 'center' }}>
                        <button type="button" style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ff4d4f', padding: 0 }}
                          onClick={() => removeParam(i)}>✕</button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </div>
        </div>

        {/* ── 오른쪽: 컬럼 정보 ── */}
        <div className="panel-section" style={{ flex: 3.5, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 224px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.col.info')}</h3>
            {isEditYn && (
              <button className="btn btn-primary" type="button" onClick={handleSaveCols}
                disabled={saveCols.isPending || colsLocal.length === 0}>
                {saveCols.isPending ? <Spin size="small" style={{ marginRight: 6 }} /> : <SaveOutlined style={{ marginRight: 6 }} />}
                {t('btn.savecols')}
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
                  <th style={{ width: '18%', whiteSpace: 'pre-line' }}>
                    {languageCd === 'ko' ? '데이터\n타입' : t('thd.datatypecd')}
                  </th>
                  <th style={{ width: '9%' }}>{t('thd.measureyn')}</th>
                  <th style={{ width: '9%' }}>{t('thd.useyn_thd')}</th>
                  <th>{t('thd.field_path_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {colsLocal.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', color: '#888' }}>{t('msg.select.data')}</td></tr>
                ) : colsLocal.map((col, i) => (
                  <tr key={i}>
                    <td style={tdStyle}>
                      <input style={inputStyle} type="text" value={col.querycolnm || ''}
                        onChange={(e) => updateCol(i, 'querycolnm', e.target.value)} />
                    </td>
                    <td style={tdStyle}>
                      <input style={inputStyle} type="text" value={col.dispcolnm || ''}
                        onChange={(e) => updateCol(i, 'dispcolnm', e.target.value)} />
                    </td>
                    <td style={tdStyle}>
                      <select style={inputStyle} value={col.datatypecd || 'string'}
                        onChange={(e) => updateCol(i, 'datatypecd', e.target.value)}>
                        {datatypeOptions.map((c) => (
                          <option key={c.codevalue} value={c.codevalue}>{t(c.term_key) || c.default_name}</option>
                        ))}
                      </select>
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                      <input type="checkbox" checked={!!col.measureyn}
                        onChange={(e) => updateCol(i, 'measureyn', e.target.checked)} />
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                      <input type="checkbox" checked={col.useyn !== false}
                        onChange={(e) => updateCol(i, 'useyn', e.target.checked)} />
                    </td>
                    <td style={tdStyle}>
                      <input style={inputStyle} type="text" value={col.field_path || ''}
                        placeholder="data.items"
                        onChange={(e) => updateCol(i, 'field_path', e.target.value)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </div>
        </div>

      </div>
    </div>
  )
}
