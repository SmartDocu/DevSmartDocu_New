import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { App, Modal } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useMenus } from '@/hooks/useMenus'
import { useServers, useSaveServer, useDeleteServer } from '@/hooks/useSettings'

const EMPTY_FORM = {
  connuid: '', connnm: '', dbtype: '',
  server: '', port: '', db: '', ssl_mode: false,
  service_name: '', sid: '', tns: '',
  timeout: '', retry_count: '', desc: '',
  useyn: true,
  username: '', password: '', password_confirm: '',
}

export default function SettingsServersPage() {
  useLangStore((s) => s.translations)

  const location = useLocation()
  const { data: allMenus = [] } = useMenus()
  const currentMenu = allMenus.find((m) => m.route_path && location.pathname.includes(m.route_path))
  const menuNm = currentMenu ? (t(`mnu.${currentMenu.menucd}`) || currentMenu.default_text || '') : ''

  const { message } = App.useApp()
  const { data = {}, isLoading } = useServers()
  const saveServer = useSaveServer()
  const deleteServer = useDeleteServer()

  const [form, setForm] = useState(EMPTY_FORM)
  const [selectedId, setSelectedId] = useState(null)

  const connectors = data.connectors || []
  const dbtypes    = data.dbtypes    || []

  useEffect(() => {
    if (dbtypes.length > 0) {
      setForm(f => ({ ...f, dbtype: f.dbtype || dbtypes[0] }))
    }
  }, [dbtypes])

  const handleRowClick = (row) => {
    setSelectedId(row.connuid)
    setForm({
      connuid:       row.connuid || '',
      connnm:        row.connnm || '',
      dbtype:        row.dbtype || '',
      server:        row.server || '',
      port:          row.port || '',
      db:            row.db || '',
      ssl_mode:      !!row.ssl_mode,
      service_name:  row.service_name || '',
      sid:           row.sid || '',
      tns:           row.tns || '',
      timeout:       row.timeout ?? '',
      retry_count:   row.retry_count ?? '',
      desc:          row.desc || '',
      useyn:         !!row.useyn,
      username:      row.username || '',
      password:      '',
      password_confirm: '',
    })
  }

  const handleNew = () => {
    setSelectedId(null)
    setForm({ ...EMPTY_FORM, dbtype: dbtypes[0] || 'Oracle' })
  }

  const handleSave = () => {
    const pw = form.password.trim()
    const pwConfirm = form.password_confirm.trim()
    if (pw && pw !== pwConfirm) { message.warning(t('msg.password.mismatch')); return }
    if (!form.connnm.trim()) { message.warning(t('msg.connectnm.required')); return }

    const body = {
      connuid:      form.connuid || null,
      connnm:       form.connnm,
      dbtype:       form.dbtype,
      server:       form.server || null,
      port:         form.port || null,
      db:           form.db || null,
      ssl_mode:     form.ssl_mode,
      service_name: form.service_name || null,
      sid:          form.sid || null,
      tns:          form.tns || null,
      timeout:      form.timeout !== '' ? Number(form.timeout) : null,
      retry_count:  form.retry_count !== '' ? Number(form.retry_count) : null,
      desc:         form.desc || null,
      useyn:        form.useyn,
      username:     form.username,
    }
    if (pw) body.password = pw
    saveServer.mutate(body, {
      onSuccess: () => { message.success(t('msg.save.success')); handleNew() },
      onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
    })
  }

  const handleDelete = () => {
    if (!selectedId) { message.warning(t('msg.select.server')); return }
    Modal.confirm({
      title: t('ttl.confirm.delete'), content: t('msg.confirm.delete'),
      okText: t('btn.delete'), cancelText: t('btn.cancel'), okButtonProps: { danger: true },
      onOk: () => deleteServer.mutate(selectedId, {
        onSuccess: () => { message.success(t('msg.delete.success')); handleNew() },
        onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
      }),
    })
  }

  const isOracle = form.dbtype === 'Oracle'
  const isOracleTns = form.dbtype === 'Oracle(TNS)'
  const isSupabase = form.dbtype === 'supabase'
  const showServerPort = !isOracleTns && !isSupabase
  const showDb = ['mssql', 'postgres'].includes(form.dbtype)
  const showSsl = form.dbtype === 'postgres'
  const showUsername = !isSupabase

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{menuNm}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측: DB 목록 */}
        <div style={{ flex: 3, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleNew}>{t('btn.new')}</button>
          </div>
          <div className="table-container">
            <table id="servers-table" style={{ cursor: 'pointer' }}>
              <thead>
                <tr>
                  <th style={{ width: '50%' }}>{t('thd.connectnm_thd')}</th>
                  <th style={{ width: '35%' }}>{t('thd.dbtype_thd')}</th>
                  <th style={{ width: '15%' }}>{t('thd.useyn_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : connectors.length === 0 ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : connectors.map((s) => (
                  <tr key={s.connuid}
                    className={selectedId === s.connuid ? 'selected-row' : ''}
                    onClick={() => handleRowClick(s)}
                  >
                    <td>{s.connnm}</td>
                    <td>{s.dbtype}</td>
                    <td style={{ textAlign: 'center' }}>{s.useyn ? '✔' : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측: DB 상세 */}
        <div style={{ flex: 7, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveServer.isPending}>{t('btn.save')}</button>
              {selectedId && (
                <button className="btn btn-danger" type="button" onClick={handleDelete} disabled={deleteServer.isPending}>{t('btn.delete')}</button>
              )}
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="dbtype">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.dbtype_lbl')}:
            </label>
            <select id="dbtype" value={form.dbtype}
              onChange={(e) => setForm(f => ({ ...f, dbtype: e.target.value }))}>
              {dbtypes.map((tp) => <option key={tp} value={tp}>{tp}</option>)}
            </select>
          </div>

          <div className="form-group">
            <label>
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.connectnm_lbl')}:
            </label>
            <input type="text" value={form.connnm}
              onChange={(e) => setForm(f => ({ ...f, connnm: e.target.value }))} />
          </div>

          {(showServerPort || isSupabase) && (
            <div className="form-group">
              <label htmlFor="server">
                <span style={{ color: 'red', marginRight: 2 }}>*</span>
                {isSupabase ? t('lbl.supabase_url_lbl') : t('lbl.server_lbl')}:
              </label>
              <input type="text" id="server" value={form.server}
                onChange={(e) => setForm(f => ({ ...f, server: e.target.value }))} />
            </div>
          )}

          {showServerPort && (
            <div className="form-group">
              <label htmlFor="port">{t('lbl.port_lbl')}:</label>
              <input type="text" id="port" value={form.port}
                onChange={(e) => setForm(f => ({ ...f, port: e.target.value }))} />
            </div>
          )}

          {isOracleTns && (
            <div className="form-group">
              <label htmlFor="tns">
                <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.tns_lbl')}:
              </label>
              <textarea id="tns" rows={3} style={{ resize: 'vertical' }} value={form.tns}
                onChange={(e) => setForm(f => ({ ...f, tns: e.target.value }))} />
            </div>
          )}

          {showDb && (
            <div className="form-group">
              <label htmlFor="db">{t('lbl.db_lbl')}:</label>
              <input type="text" id="db" value={form.db}
                onChange={(e) => setForm(f => ({ ...f, db: e.target.value }))} />
            </div>
          )}

          {isOracle && (
            <div className="form-group">
              <label htmlFor="service_name">{t('lbl.service_name_lbl')}:</label>
              <input type="text" id="service_name" value={form.service_name}
                onChange={(e) => setForm(f => ({ ...f, service_name: e.target.value }))} />
            </div>
          )}

          {isOracle && (
            <div className="form-group">
              <label htmlFor="sid">{t('lbl.sid_lbl')}:</label>
              <input type="text" id="sid" value={form.sid}
                onChange={(e) => setForm(f => ({ ...f, sid: e.target.value }))} />
            </div>
          )}

          {showSsl && (
            <div className="form-group">
              <label>{t('lbl.ssl_mode_lbl')}:</label>
              <input type="checkbox" checked={form.ssl_mode}
                onChange={(e) => setForm(f => ({ ...f, ssl_mode: e.target.checked }))} />
            </div>
          )}

          <div className="form-group">
            <label htmlFor="timeout">{t('lbl.timeout_lbl')}:</label>
            <input type="number" id="timeout" value={form.timeout} min={0}
              onChange={(e) => setForm(f => ({ ...f, timeout: e.target.value }))} />
          </div>

          <div className="form-group">
            <label htmlFor="retry_count">{t('lbl.retry_count_lbl')}:</label>
            <input type="number" id="retry_count" value={form.retry_count} min={0}
              onChange={(e) => setForm(f => ({ ...f, retry_count: e.target.value }))} />
          </div>

          <div className="form-group">
            <label htmlFor="desc">{t('lbl.desc_lbl')}:</label>
            <textarea id="desc" rows={3} style={{ resize: 'vertical' }} value={form.desc}
              onChange={(e) => setForm(f => ({ ...f, desc: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.useyn_lbl')}:
            </label>
            <input type="checkbox" checked={form.useyn}
              onChange={(e) => setForm(f => ({ ...f, useyn: e.target.checked }))} />
          </div>

          {showUsername && (
            <div className="form-group">
              <label htmlFor="username">{t('lbl.username_lbl')}:</label>
              <input type="text" id="username" value={form.username}
                autoComplete="off"
                onChange={(e) => setForm(f => ({ ...f, username: e.target.value }))} />
            </div>
          )}

          <div className="form-group">
            <label htmlFor="password">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>
              {isSupabase ? t('lbl.api_key_lbl') : t('lbl.password')}:
              <small style={{ color: '#888', marginLeft: 8, fontWeight: 'normal' }}>{t('inf.password.hidden')}</small>
            </label>
            <input type="password" id="password" value={form.password}
              placeholder={t('msg.placeholder.password.change')} autoComplete="new-password"
              onChange={(e) => setForm(f => ({ ...f, password: e.target.value }))} />
          </div>

          <div className="form-group">
            <label htmlFor="password_confirm">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.password.confirm')}:
            </label>
            <input type="password" id="password_confirm" value={form.password_confirm}
              placeholder={t('msg.placeholder.password.confirm')} autoComplete="new-password"
              onChange={(e) => setForm(f => ({ ...f, password_confirm: e.target.value }))} />
          </div>
        </div>
      </div>
    </div>
  )
}
