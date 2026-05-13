import { useState, useEffect } from 'react'
import { App, Popconfirm } from 'antd'
import { useSearchParams } from 'react-router-dom'
import { useLangStore, t } from '@/stores/langStore'
import {
  useOrgProjectUsers,
  useSaveProjectUser,
  useDeleteProjectUser,
} from '@/hooks/useOrg'

const roStyle = { backgroundColor: '#f0f0f0', color: '#555', border: '1px solid #ccc' }

const EMPTY_FORM = {
  useruid: '', email: '', usernm: '', rolecd: 'U',
  useyn: true, creatornm: '', createdts: '',
}

export default function OrgProjectUsersPage() {
  const { message } = App.useApp()
  const [searchParams, setSearchParams] = useSearchParams()
  useLangStore((s) => s.translations)

  const paramProjectid = searchParams.get('projects') || ''
  const [selectedProjectid, setSelectedProjectid] = useState(paramProjectid)

  const { data = {}, isLoading } = useOrgProjectUsers(selectedProjectid)
  const saveMutation = useSaveProjectUser()
  const deleteMutation = useDeleteProjectUser()

  const [form, setForm] = useState(EMPTY_FORM)
  const [selectedUid, setSelectedUid] = useState(null)
  const [userModalOpen, setUserModalOpen] = useState(false)

  const { projects = [], projectusers = [], tenantusers = [] } = data

  useEffect(() => {
    if (paramProjectid) setSelectedProjectid(paramProjectid)
  }, [paramProjectid])

  const handleProjectChange = (e) => {
    const value = e.target.value
    setSelectedProjectid(value)
    setSearchParams(value ? { projects: value } : {})
    setSelectedUid(null)
    setForm(EMPTY_FORM)
  }

  const handleRowClick = (row) => {
    setSelectedUid(row.useruid)
    setForm({
      useruid:   row.useruid || '',
      email:     row.email || '',
      usernm:    row.usernm || '',
      rolecd:    row.rolecd || 'U',
      useyn:     !!row.useyn,
      creatornm: row.creatornm || '',
      createdts: row.createdts || '',
    })
  }

  const handleNew = () => { setSelectedUid(null); setForm(EMPTY_FORM) }

  const handleSave = () => {
    if (!selectedProjectid) { message.warning(t('msg.select.project')); return }
    if (!form.email.trim()) { message.warning(t('msg.email.required')); return }
    saveMutation.mutate(
      {
        projectid: selectedProjectid,
        email: form.email,
        rolecd: form.rolecd || 'U',
        useyn: form.useyn ?? true,
      },
      {
        onSuccess: () => { message.success(t('msg.save.success')); handleNew() },
        onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
      },
    )
  }

  const handleDelete = () => {
    if (!form.useruid) { message.warning(t('msg.select.delete')); return }
    deleteMutation.mutate(
      { projectid: selectedProjectid, useruid: form.useruid },
      {
        onSuccess: () => { message.success(t('msg.delete.success')); handleNew() },
        onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
      },
    )
  }

  const handleModalUserSelect = (u) => {
    setForm(f => ({ ...f, email: u.email, usernm: u.usernm }))
    setUserModalOpen(false)
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('mnu.project.project_users')}</div>
        </div>
      </div>

      {/* 프로젝트 선택 필터 */}
      <div className="form-filter-group">
        <div className="filter-item">
          <label htmlFor="projects" style={{ width: 100 }}>{t('lbl.project')}:</label>
          <select name="projects" id="projects" value={selectedProjectid} onChange={handleProjectChange} style={{ minWidth: 300 }}>
            <option value="">{t('msg.select.project')}</option>
            {projects.map((p) => (
              <option key={p.projectid} value={p.projectid}>{p.projectnm}</option>
            ))}
          </select>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측 패널: 목록 */}
        <div style={{ flex: 5, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleNew}>{t('btn.new')}</button>
          </div>
          <div className="table-container">
            <table className="table table-bordered table-sm" style={{ cursor: 'pointer' }}>
              <thead>
                <tr>
                  <th style={{ width: '35%' }}>{t('thd.email_thd')}</th>
                  <th style={{ width: '25%' }}>{t('thd.usernm_thd')}</th>
                  <th style={{ width: '20%' }}>{t('thd.rolecd_thd')}</th>
                  <th style={{ width: '20%' }}>{t('thd.useyn_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : projectusers.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : projectusers.map((u) => (
                  <tr key={u.useruid}
                    className={selectedUid === u.useruid ? 'selected-row' : ''}
                    onClick={() => handleRowClick(u)}
                  >
                    <td>{u.email}</td>
                    <td>{u.usernm}</td>
                    <td>{u.rolecd === 'M' ? t('cod.rolecd_M') : t('cod.rolecd_U')}</td>
                    <td style={{ textAlign: 'center' }}>{u.useyn ? '✔' : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측 패널: 상세 */}
        <div style={{ flex: 5, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveMutation.isPending}>
                {t('btn.save')}
              </button>
              {selectedUid && (
                <Popconfirm
                  title={t('msg.confirm.delete')}
                  onConfirm={handleDelete}
                  okText={t('btn.delete')}
                  cancelText={t('btn.cancel')}
                  okButtonProps={{ danger: true }}
                >
                  <button className="btn btn-danger" type="button" disabled={deleteMutation.isPending}>
                    {t('btn.delete')}
                  </button>
                </Popconfirm>
              )}
            </div>
          </div>

          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.email')}:</label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input type="text" value={form.email} placeholder={t('msg.email.required')}
                onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))} />
              <button type="button" className="btn btn-primary" onClick={() => setUserModalOpen(true)}>
                {t('btn.lookup')}
              </button>
            </div>
          </div>

          <div className="form-group">
            <label>{t('lbl.usernm')}:</label>
            <input type="text" value={form.usernm} disabled style={roStyle} />
          </div>

          <div className="form-group">
            <label>{t('lbl.rolecd_lbl')}:</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 64, paddingLeft: 60 }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }}>
                <input type="radio" name="rolecd" value="M"
                  checked={form.rolecd === 'M'}
                  onChange={() => setForm(f => ({ ...f, rolecd: 'M' }))} />
                <span>{t('cod.rolecd_M')}</span>
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }}>
                <input type="radio" name="rolecd" value="U"
                  checked={form.rolecd === 'U'}
                  onChange={() => setForm(f => ({ ...f, rolecd: 'U' }))} />
                <span>{t('cod.rolecd_U')}</span>
              </span>
            </div>
          </div>

          <div className="form-group">
            <label>{t('lbl.useyn_lbl')}:</label>
            <div style={{ paddingLeft: 60 }}>
              <input type="checkbox" checked={form.useyn}
                onChange={(e) => setForm(f => ({ ...f, useyn: e.target.checked }))} />
            </div>
          </div>
        </div>
      </div>

      {/* 사용자 선택 Modal */}
      <div id="user-modal" style={{
        display: userModalOpen ? 'flex' : 'none',
        position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
        background: 'rgba(0,0,0,0.5)', justifyContent: 'center', alignItems: 'center', zIndex: 1050,
      }}>
        <div style={{
          background: '#fff', padding: 20, width: 500, maxHeight: '80%', overflow: 'auto',
          borderRadius: 8, position: 'relative', zIndex: 1060,
        }}>
          <h4>{t('ttl.user.select')}</h4>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f0f0f0' }}>
                <th style={{ padding: 8, border: '1px solid #ccc' }}>{t('thd.usernm_thd')}</th>
                <th style={{ padding: 8, border: '1px solid #ccc' }}>{t('thd.email_thd')}</th>
              </tr>
            </thead>
            <tbody>
              {tenantusers.map((u) => (
                <tr key={u.useruid} style={{ cursor: 'pointer' }}
                  onClick={() => handleModalUserSelect(u)}>
                  <td style={{ padding: 6, border: '1px solid #ccc' }}>{u.usernm}</td>
                  <td style={{ padding: 6, border: '1px solid #ccc' }}>{u.email}</td>
                </tr>
              ))}
              {tenantusers.length === 0 && (
                <tr><td colSpan={2} style={{ textAlign: 'center', padding: 8 }}>{t('msg.no.data')}</td></tr>
              )}
            </tbody>
          </table>
          <div style={{ textAlign: 'right', marginTop: 10 }}>
            <button type="button" className="btn btn-primary" onClick={() => setUserModalOpen(false)}>
              {t('btn.close')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
