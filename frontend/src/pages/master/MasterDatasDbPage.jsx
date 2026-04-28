import { useState, useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { App, Spin } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useAuthStore } from '@/stores/authStore'
import { useMenus } from '@/hooks/useMenus'
import {
  useDatasDb, useDatasProjects, useDbConnectors, useSaveDbData, useDeleteData,
  useDatacols, useCreateDatacols, useSaveDatacols,
} from '@/hooks/useDatas'

const DATATYPE_OPTIONS = [
  { value: 'D', label: t('cod.keycoldatatypecd_D') },
  { value: 'C', label: t('cod.keycoldatatypecd_C') },
  { value: 'I', label: t('cod.keycoldatatypecd_I') },
]

const EMPTY_FORM = { datauid: '', projectid: '', connectid: '', datanm: '', query: '' }

export default function MasterDatasDbPage() {
  const { message } = App.useApp()
  useLangStore((s) => s.translations)

  const location = useLocation()
  const user = useAuthStore((s) => s.user)
  const isEditYn = user?.editbuttonyn === 'Y'

  const { data: allMenus = [] } = useMenus()
  const currentMenu = allMenus.find((m) => m.route_path && location.pathname.includes(m.route_path))
  const menuNm = currentMenu ? (currentMenu.default_text || '') : 'DB 데이터'

  const { data: datas = [], isLoading } = useDatasDb()
  const { data: projects = [] } = useDatasProjects()
  const { data: connectors = [] } = useDbConnectors()
  const saveData     = useSaveDbData()
  const deleteData   = useDeleteData('db')
  const createCols   = useCreateDatacols()
  const saveCols     = useSaveDatacols()

  const [form,        setForm]        = useState(EMPTY_FORM)
  const [selectedUid, setSelectedUid] = useState(null)
  const [colsLocal,   setColsLocal]   = useState([])

  const queryRef = useRef(null)

  // 선택된 데이터의 컬럼 조회
  const { data: datacols } = useDatacols(selectedUid)

  // datacols가 변경되면 로컬 상태 갱신
  useEffect(() => {
    setColsLocal((datacols || []).map((c) => ({ ...c })))
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
      message.warning(t('msg.db.required'))
      return
    }
    const body = {
      datauid:   form.datauid || null,
      datanm:    form.datanm,
      connectid: form.connectid ? Number(form.connectid) : null,
      projectid: Number(form.projectid),
      query:     form.query,
    }
    saveData.mutate(body, {
      onSuccess: (result) => {
        const savedUid = result?.datauid || form.datauid
        if (savedUid) {
          createCols.mutate({ datauid: savedUid }, {
            onSuccess: () => {
              message.success(t('msg.save.col.created'))
              setSelectedUid(savedUid)
            },
            onError: () => message.warning(t('msg.save.col.warn')),
          })
        } else {
          message.success(t('msg.save.success'))
        }
      },
      onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
    })
  }

  const handleDelete = () => {
    if (!form.datauid) { message.warning(t('msg.select.delete')); return }
    if (!window.confirm(t('msg.confirm.delete'))) return
    deleteData.mutate(form.datauid, {
      onSuccess: () => { message.success(t('msg.delete.success')); handleNew() },
      onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
    })
  }

  const handleSaveCols = () => {
    if (colsLocal.length === 0) { message.warning(t('msg.col.empty')); return }
    const payload = colsLocal.map((c) => ({
      datauid:    c.datauid || selectedUid,
      querycolnm: c.querycolnm,
      dispcolnm:  c.dispcolnm || '',
      datatypecd: c.datatypecd || 'C',
      measureyn:  !!c.measureyn,
    }))
    saveCols.mutate(payload, {
      onSuccess: () => message.success(t('msg.save.success')),
      onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
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
          <div>{menuNm}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>

        {/* 왼쪽: 데이터 목록 */}
        <div style={{ flex: 3, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleNew}>{t('btn.new')}</button>
          </div>
          <div className="table-container" style={{ height: 'auto' }}>
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th>{t('thd.projectnm')}</th>
                  <th>{t('thd.connectnm')}</th>
                  <th>{t('thd.datanm')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : datas.length === 0 ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : datas.map((d) => (
                  <tr key={d.datauid}
                    style={{ cursor: 'pointer', background: selectedUid === d.datauid ? '#e6f4ff' : '' }}
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

        {/* 가운데: 데이터 상세 */}
        <div style={{ flex: 3, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            {isEditYn && (
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-primary" type="button" onClick={handleSave}
                  disabled={saveData.isPending || createCols.isPending}>
                  {(saveData.isPending || createCols.isPending) && <Spin size="small" style={{ marginRight: 4 }} />}
                  {t('btn.save')}
                </button>
                {form.datauid && (
                  <button className="btn btn-danger" type="button" onClick={handleDelete}
                    disabled={deleteData.isPending}>
                    {t('btn.delete')}
                  </button>
                )}
              </div>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="data-projectid">{t('lbl.projectnm')}</label>
            <select id="data-projectid" value={form.projectid}
              onChange={(e) => setForm(f => ({ ...f, projectid: e.target.value }))}>
              <option value="">{t('msg.select.placeholder')}</option>
              {projects.map((p) => (
                <option key={p.projectid} value={p.projectid}>{p.projectnm}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="data-connectid">{t('lbl.connectnm')}</label>
            <select id="data-connectid" value={form.connectid}
              onChange={(e) => setForm(f => ({ ...f, connectid: e.target.value }))}>
              <option value="">{t('msg.select.placeholder')}</option>
              {connectors.map((c) => (
                <option key={c.connectid} value={c.connectid}>{c.connectnm}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>{t('lbl.datanm')}</label>
            <input type="text" value={form.datanm}
              onChange={(e) => setForm(f => ({ ...f, datanm: e.target.value }))} />
          </div>

          {/* 안 보이는 더미 필드 (브라우저 자동완성 방지) */}
          <input type="text" style={{ position: 'absolute', left: -9999, top: -9999 }} autoComplete="off" readOnly />

          <div className="form-group">
            <label htmlFor="data-query">{t('lbl.query')}</label>
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
        </div>

        {/* 오른쪽: 데이터 컬럼 */}
        <div style={{ flex: 4, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.col.info')}</h3>
            {isEditYn && (
              <button className="btn btn-primary" type="button" onClick={handleSaveCols}
                disabled={saveCols.isPending || colsLocal.length === 0}>
                {saveCols.isPending && <Spin size="small" style={{ marginRight: 4 }} />}
                {t('btn.savecols')}
              </button>
            )}
          </div>
          <div className="table-container" style={{ height: 'auto' }}>
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th>{t('thd.querycolnm')}</th>
                  <th>{t('thd.dispcolnm')}</th>
                  <th>{t('thd.datatypecd')}</th>
                  <th>{t('thd.measureyn')}</th>
                </tr>
              </thead>
              <tbody>
                {colsLocal.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center' }}>{t('msg.select.data')}</td></tr>
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
                        {DATATYPE_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
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
          </div>
        </div>

      </div>
    </div>
  )
}
