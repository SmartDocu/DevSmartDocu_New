import { useState } from 'react'
import { App, Modal, Popconfirm } from 'antd'
import { useServers, useSaveServer, useDeleteServer } from '@/hooks/useSettings'

const roStyle = { backgroundColor: '#f0f0f0', color: '#555', border: '1px solid #ccc' }

const EMPTY_FORM = {
  connectid: '', connectnm: '', connecttype: '', orderno: '',
  useyn: true, encendpoint: '', encdatabase: '', encaccessuserid: '',
  password: '', password_confirm: '',
}

export default function SettingsServersPage() {
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
          <div>DB 연결정보</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 왼쪽: DB 목록 */}
        <div style={{ flex: '50%' }}>
          <h3>DB 목록</h3>
          <div className="table-container">
            <table id="servers-table" style={{ cursor: 'pointer' }}>
              <thead>
                <tr>
                  <th style={{ width: '20%' }}>서버명</th>
                  <th style={{ width: '13%' }}>DBMS</th>
                  <th style={{ width: '12%' }}>순번</th>
                  <th style={{ width: '12%' }}>사용</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center' }}>로딩 중...</td></tr>
                ) : connectors.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center', color: '#888' }}>등록된 서버가 없습니다.</td></tr>
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

        {/* 오른쪽: DB 상세 */}
        <div style={{ flex: '50%' }}>
          <h3>DB 상세</h3>

          <div className="form-group">
            <label htmlFor="connecttype">DBMS:</label>
            <select id="connecttype" value={form.connecttype}
              onChange={(e) => setForm(f => ({ ...f, connecttype: e.target.value }))}>
              {dbtypes.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          <div className="form-group">
            <label>서버명:</label>
            <input type="text" value={form.connectnm}
              onChange={(e) => setForm(f => ({ ...f, connectnm: e.target.value }))} />
          </div>

          <div className="form-group">
            <label htmlFor="orderno">순번:</label>
            <input type="number" id="orderno" value={form.orderno} min={0} step={1}
              onChange={(e) => setForm(f => ({ ...f, orderno: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>사용:</label>
            <input type="checkbox" checked={form.useyn}
              onChange={(e) => setForm(f => ({ ...f, useyn: e.target.checked }))} />
          </div>

          <div className="form-group">
            <label htmlFor="encendpoint">EndPoint:</label>
            <input type="text" id="encendpoint" value={form.encendpoint}
              onChange={(e) => setForm(f => ({ ...f, encendpoint: e.target.value }))} />
          </div>

          <div className="form-group">
            <label htmlFor="encdatabase">DB:</label>
            <input type="text" id="encdatabase" value={form.encdatabase}
              onChange={(e) => setForm(f => ({ ...f, encdatabase: e.target.value }))} />
          </div>

          <div className="form-group">
            <label htmlFor="encaccessuserid">계정:</label>
            <input type="text" id="encaccessuserid" value={form.encaccessuserid}
              autoComplete="off"
              onChange={(e) => setForm(f => ({ ...f, encaccessuserid: e.target.value }))} />
          </div>

          <div className="form-group">
            <label htmlFor="password">비밀번호:</label>
            <input type="password" id="password" value={form.password}
              placeholder="변경 시에만 입력" autoComplete="new-password"
              onChange={(e) => setForm(f => ({ ...f, password: e.target.value }))} />
          </div>

          <div className="form-group">
            <label htmlFor="password_confirm">비밀번호 확인:</label>
            <input type="password" id="password_confirm" value={form.password_confirm}
              placeholder="비밀번호를 다시 입력" autoComplete="new-password"
              onChange={(e) => setForm(f => ({ ...f, password_confirm: e.target.value }))} />
            <small style={{ color: '#888' }}>※ 기존 비밀번호는 표시되지 않습니다.</small>
          </div>

          <div className="button-group">
            <button type="button" className="icon-btn" onClick={handleNew}>
              <div className="icon-wrapper">
                <img src="/icons/new.svg" className="icon-img new-icon" alt="신규" />
                <span className="icon-label">신규</span>
              </div>
            </button>
            <button type="button" className="icon-btn" onClick={handleSave} disabled={saveServer.isPending}>
              <div className="icon-wrapper">
                <img src="/icons/save.svg" className="icon-img save-icon" alt="저장" />
                <span className="icon-label">저장</span>
              </div>
            </button>
            <Popconfirm title="정말 삭제하시겠습니까?" onConfirm={handleDelete}
              okText="삭제" cancelText="취소" okButtonProps={{ danger: true }}
              disabled={!selectedId}>
              <button type="button" className="icon-btn" disabled={deleteServer.isPending}>
                <div className="icon-wrapper">
                  <img src="/icons/delete.svg" className="icon-img del-icon" alt="삭제" />
                  <span className="icon-label">삭제</span>
                </div>
              </button>
            </Popconfirm>
          </div>
        </div>
      </div>
    </div>
  )
}
