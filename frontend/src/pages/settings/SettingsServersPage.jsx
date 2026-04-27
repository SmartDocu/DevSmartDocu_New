import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { App, Modal } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useMenus } from '@/hooks/useMenus'
import { useServers, useSaveServer, useDeleteServer } from '@/hooks/useSettings'

const EMPTY_FORM = {
  connectid: '', connectnm: '', connecttype: '', orderno: '',
  useyn: true, encendpoint: '', encdatabase: '', encaccessuserid: '',
  password: '', password_confirm: '',
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

  const handleRowClick = (row) => {
    setSelectedId(row.connectid)
    setForm({
      connectid:       row.connectid || '',
      connectnm:       row.connectnm || '',
      connecttype:     row.connecttype || '',
      orderno:         row.orderno ?? '',
      useyn:           !!row.useyn,
      encendpoint:     row.decendpoint || '',
      encdatabase:     row.decdatabase || '',
      encaccessuserid: row.decuserid || '',
      password:        '',
      password_confirm: '',
    })
  }

  const handleNew = () => {
    setSelectedId(null)
    setForm({ ...EMPTY_FORM, connecttype: dbtypes[0] || 'MSSQL' })
  }

  const handleSave = () => {
    const pw = form.password.trim()
    const pwConfirm = form.password_confirm.trim()
    if (pw && pw !== pwConfirm) { message.warning('비밀번호가 일치하지 않습니다. 다시 입력해주세요.'); return }
    if (!form.connectnm.trim()) { message.warning('서버명을 입력하세요.'); return }

    const body = {
      connectid:       form.connectid || null,
      connectnm:       form.connectnm,
      connecttype:     form.connecttype,
      orderno:         form.orderno !== '' ? Number(form.orderno) : null,
      useyn:           form.useyn,
      encendpoint:     form.encendpoint,
      encdatabase:     form.encdatabase,
      encaccessuserid: form.encaccessuserid,
    }
    if (pw) body.password = pw
    saveServer.mutate(body, {
      onSuccess: () => { message.success('저장되었습니다.'); handleNew() },
      onError: (err) => message.error(err.response?.data?.detail || '저장 실패'),
    })
  }

  const handleDelete = () => {
    if (!selectedId) { message.warning('삭제할 서버를 먼저 선택하세요.'); return }
    Modal.confirm({
      title: '삭제 확인', content: '정말 삭제하시겠습니까?',
      okText: '삭제', cancelText: '취소', okButtonProps: { danger: true },
      onOk: () => deleteServer.mutate(selectedId, {
        onSuccess: () => { message.success('삭제되었습니다.'); handleNew() },
        onError: (err) => message.error(err.response?.data?.detail || '삭제 실패'),
      }),
    })
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
                  <th style={{ width: '20%' }}>{t('thd.connectnm')}</th>
                  <th style={{ width: '13%' }}>{t('thd.connecttype')}</th>
                  <th style={{ width: '12%' }}>{t('thd.orderno')}</th>
                  <th style={{ width: '12%' }}>{t('thd.useyn')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : connectors.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : connectors.map((s) => (
                  <tr key={s.connectid}
                    className={selectedId === s.connectid ? 'selected-row' : ''}
                    onClick={() => handleRowClick(s)}
                  >
                    <td>{s.connectnm}</td>
                    <td>{s.connecttype}</td>
                    <td style={{ textAlign: 'center' }}>{s.orderno ?? ''}</td>
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
            <label htmlFor="connecttype">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.connecttype')}:
            </label>
            <select id="connecttype" value={form.connecttype}
              onChange={(e) => setForm(f => ({ ...f, connecttype: e.target.value }))}>
              {dbtypes.map((tp) => <option key={tp} value={tp}>{tp}</option>)}
            </select>
          </div>

          <div className="form-group">
            <label>
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.connectnm')}:
            </label>
            <input type="text" value={form.connectnm}
              onChange={(e) => setForm(f => ({ ...f, connectnm: e.target.value }))} />
          </div>

          <div className="form-group">
            <label htmlFor="orderno">{t('lbl.orderno')}:</label>
            <input type="number" id="orderno" value={form.orderno} min={0} step={1}
              onChange={(e) => setForm(f => ({ ...f, orderno: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.useyn')}:
            </label>
            <input type="checkbox" checked={form.useyn}
              onChange={(e) => setForm(f => ({ ...f, useyn: e.target.checked }))} />
          </div>

          <div className="form-group">
            <label htmlFor="encendpoint">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.encendpoint')}:
            </label>
            <input type="text" id="encendpoint" value={form.encendpoint}
              onChange={(e) => setForm(f => ({ ...f, encendpoint: e.target.value }))} />
          </div>

          <div className="form-group">
            <label htmlFor="encdatabase">{t('lbl.encdatabase')}:</label>
            <input type="text" id="encdatabase" value={form.encdatabase}
              onChange={(e) => setForm(f => ({ ...f, encdatabase: e.target.value }))} />
          </div>

          <div className="form-group">
            <label htmlFor="encaccessuserid">{t('lbl.encaccessuserid')}:</label>
            <input type="text" id="encaccessuserid" value={form.encaccessuserid}
              autoComplete="off"
              onChange={(e) => setForm(f => ({ ...f, encaccessuserid: e.target.value }))} />
          </div>

          <div className="form-group">
            <label htmlFor="password">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.password')}:
              <small style={{ color: '#888', marginLeft: 8, fontWeight: 'normal' }}>{t('inf.password.hidden')}</small>
            </label>
            <input type="password" id="password" value={form.password}
              placeholder={t('placeholder.password.change')} autoComplete="new-password"
              onChange={(e) => setForm(f => ({ ...f, password: e.target.value }))} />
          </div>

          <div className="form-group">
            <label htmlFor="password_confirm">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.password_confirm')}:
            </label>
            <input type="password" id="password_confirm" value={form.password_confirm}
              placeholder={t('placeholder.password.confirm')} autoComplete="new-password"
              onChange={(e) => setForm(f => ({ ...f, password_confirm: e.target.value }))} />
          </div>
        </div>
      </div>
    </div>
  )
}
