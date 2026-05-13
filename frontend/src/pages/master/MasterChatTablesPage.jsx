import { useState, useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { App } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useAuthStore } from '@/stores/authStore'
import { useMenus } from '@/hooks/useMenus'
import {
  useDataMetaDatas, useDataMeta, useSaveDataMeta, useDeleteDataMeta,
} from '@/hooks/useDataMetas'
import { useDataCols } from '@/hooks/useDataCols'

const parseKeys = (str) =>
  str ? (str.match(/"([^"]+)"/g)?.map((s) => s.replace(/"/g, '')) ?? []) : []

const formatKeys = (arr) => arr.map((v) => `"${v}"`).join(', ')

const EMPTY_FORM = {
  aliases: '',
  primary_key: '',
  default_time_column: '',
  grain: '',
  purpose: '',
  query_examples: '',
  parent_schema: '',
  parent_table: '',
  parent_column: '',
  child_column: '',
}

export default function MasterChatTablesPage() {
  const { message } = App.useApp()
  useLangStore((s) => s.translations)

  const location = useLocation()
  const user = useAuthStore((s) => s.user)
  const isEditYn = user?.editbuttonyn === 'Y'

  const { data: allMenus = [] } = useMenus()
  const currentMenu = allMenus.find((m) => m.route_path && location.pathname.includes(m.route_path))
  const menuNm = currentMenu ? (currentMenu.default_text || '') : 'Chat Tables'

  const { data: datas = [], isLoading } = useDataMetaDatas()
  const saveDataMeta   = useSaveDataMeta()
  const deleteDataMeta = useDeleteDataMeta()

  const [selectedUid, setSelectedUid] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [pkOpen, setPkOpen] = useState(false)
  const pkRef = useRef(null)

  useEffect(() => {
    if (!pkOpen) return
    const close = (e) => { if (pkRef.current && !pkRef.current.contains(e.target)) setPkOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [pkOpen])

  const { data: meta } = useDataMeta(selectedUid)
  const { data: cols = [] } = useDataCols(selectedUid)

  useEffect(() => {
    if (meta) {
      setForm({
        aliases:             meta.aliases             || '',
        primary_key:         meta.primary_key         || '',
        default_time_column: meta.default_time_column || '',
        grain:               meta.grain               || '',
        purpose:             meta.purpose             || '',
        query_examples:      meta.query_examples      || '',
        parent_schema:       meta.parent_schema       || '',
        parent_table:        meta.parent_table        || '',
        parent_column:       meta.parent_column       || '',
        child_column:        meta.child_column        || '',

      })
    } else if (selectedUid && meta === null) {
      setForm(EMPTY_FORM)
    }
  }, [meta, selectedUid])

  const handleRowClick = (row) => {
    setSelectedUid(row.datauid)
    setForm(EMPTY_FORM)
  }

  const handleSave = () => {
    if (!selectedUid) {
      message.warning(t('msg.chat.tables.required'))
      return
    }
    const body = { datauid: selectedUid, ...form }
    saveDataMeta.mutate(body, {
      onSuccess: () => message.success(t('msg.save.success')),
      onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
    })
  }

  const handleDelete = () => {
    if (!selectedUid) { message.warning(t('msg.select.delete')); return }
    if (!window.confirm(t('msg.confirm.delete'))) return
    deleteDataMeta.mutate(selectedUid, {
      onSuccess: () => {
        message.success(t('msg.delete.success'))
        setSelectedUid(null)
        setForm(EMPTY_FORM)
      },
      onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
    })
  }

  const setField = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }))

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{menuNm}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>

        {/* 좌측: datas 목록 */}
        <div style={{ flex: 3, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <div />
          </div>
          <div className="table-container" style={{ height: 'auto' }}>
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th>{t('thd.projectnm_thd')}</th>
                  <th>{t('thd.datanm_thd')}</th>
                  <th style={{ textAlign: 'center' }}>{t('thd.setting_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : datas.length === 0 ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : datas.map((d) => (
                  <tr key={d.datauid}
                    style={{
                      cursor: 'pointer',
                      background: selectedUid === d.datauid ? 'var(--selected-row-bg)' : '',
                      color: selectedUid === d.datauid ? 'var(--selected-row)' : '',
                      fontWeight: selectedUid === d.datauid ? 600 : 'normal',
                    }}
                    onClick={() => handleRowClick(d)}
                  >
                    <td>{d.projectnm || ''}</td>
                    <td>{d.datanm}</td>
                    <td style={{ textAlign: 'center' }}>{d.settingyn ? '✓' : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측: data_meta 상세 폼 */}
        <div style={{ flex: 7, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            {isEditYn && (
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-primary" type="button" onClick={handleSave}
                  disabled={saveDataMeta.isPending || !selectedUid}>
                  {t('btn.save')}
                </button>
                {selectedUid && (
                  <button className="btn btn-danger" type="button" onClick={handleDelete}
                    disabled={deleteDataMeta.isPending}>
                    {t('btn.delete')}
                  </button>
                )}
              </div>
            )}
          </div>

          <div className="form-group">
            <label>{t('lbl.aliases')}</label>
            <input type="text" value={form.aliases} onChange={setField('aliases')} placeholder='"SalesOrderDetail", "OrderDetailID"' />
          </div>

          <div className="form-group">
            <label>{t('lbl.primary_key')}</label>
            <div ref={pkRef} style={{ position: 'relative' }}>
              <select
                value=""
                onMouseDown={(e) => { e.preventDefault(); if (isEditYn) setPkOpen((o) => !o) }}
                onChange={() => {}}
                disabled={!isEditYn}
                style={{ cursor: isEditYn ? 'pointer' : 'default' }}
              >
                <option value="">
                  {parseKeys(form.primary_key).length === 0
                    ? t('msg.select.placeholder')
                    : parseKeys(form.primary_key).join(', ')}
                </option>
              </select>
              {pkOpen && isEditYn && (
                <div style={{
                  position: 'absolute', top: 'calc(100% + 2px)', left: 0, right: 0,
                  background: '#fff', border: '1px solid #d9d9d9', borderRadius: 4,
                  zIndex: 1000, maxHeight: 200, overflowY: 'auto',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
                }}>
                  {cols.map((c) => {
                    const checked = parseKeys(form.primary_key).includes(c.querycolnm)
                    return (
                      <div key={c.querycolnm}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 8,
                          padding: '5px 10px', cursor: 'pointer',
                          background: checked ? '#f0f7ff' : 'transparent', color: '#333',
                        }}
                        onClick={() => {
                          const cur = parseKeys(form.primary_key)
                          const next = checked ? cur.filter((v) => v !== c.querycolnm) : [...cur, c.querycolnm]
                          setForm((f) => ({ ...f, primary_key: formatKeys(next) }))
                        }}
                      >
                        <input type="checkbox" checked={checked} readOnly
                          style={{ margin: 0, cursor: 'pointer', pointerEvents: 'none' }} />
                        {c.querycolnm}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>

          <div className="form-group">
            <label>{t('lbl.default_time_column')}</label>
            <select value={form.default_time_column} onChange={setField('default_time_column')}>
              <option value="">{t('msg.select.placeholder')}</option>
              {cols.map((c) => (
                <option key={c.querycolnm} value={c.querycolnm}>{c.querycolnm}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>{t('lbl.grain')}</label>
            <input type="text" value={form.grain} onChange={setField('grain')} placeholder='"SalesOrderDetailID"' />
          </div>

          <div className="form-group">
            <label>{t('lbl.purpose')}</label>
            <textarea rows={3} value={form.purpose} style={{ resize: 'vertical' }} onChange={setField('purpose')}
              placeholder={'"Product sales volume analysis",\n"Sales analysis by category",\n"Sales aggregation by line"'} />
          </div>

          <div className="form-group">
            <label>{t('lbl.query_examples')}</label>
            <textarea rows={3} value={form.query_examples} style={{ resize: 'vertical' }} onChange={setField('query_examples')}
              placeholder={'"Best-selling products",\n"Sales by category",\n"Product sales ranking"'} />
          </div>

          <div className="form-group">
            <label>{t('lbl.parent_schema')}</label>
            <input type="text" value={form.parent_schema} onChange={setField('parent_schema')} placeholder="Sales" />
          </div>

          <div className="form-group">
            <label>{t('lbl.parent_table')}</label>
            <input type="text" value={form.parent_table} onChange={setField('parent_table')} placeholder="SalesOrderHeader" />
          </div>

          <div className="form-group">
            <label>{t('lbl.parent_column')}</label>
            <input type="text" value={form.parent_column} onChange={setField('parent_column')} placeholder="SalesOrderID" />
          </div>

          <div className="form-group">
            <label>{t('lbl.child_column')}</label>
            <input type="text" value={form.child_column} onChange={setField('child_column')} placeholder="SalesOrderID" />
          </div>


        </div>

      </div>
    </div>
  )
}
