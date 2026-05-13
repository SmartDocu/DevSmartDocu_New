import { useState, useMemo } from 'react'
import { App, Modal, Popconfirm } from 'antd'
import { useSearchParams } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useOrgTenantUsers, useSaveTenantUser, useDeleteTenantUser } from '@/hooks/useOrg'

const roStyle = { backgroundColor: '#f0f0f0', color: '#555', border: '1px solid #ccc' }

const EMPTY_FORM = {
  sep: '', tenantnewuid: '', useruid: '',
  email: '', usernm: '', rolecd: 'U', useyn: true, creatornm: '', createdts: '',
}

export default function OrgTenantUsersPage() {
  const { message } = App.useApp()
  const [searchParams] = useSearchParams()
  const { user } = useAuthStore()
  useLangStore((s) => s.translations)
  const roleid = user?.roleid

  const paramTenantid = roleid === 7 ? searchParams.get('tenantid') : null

  const { data = {}, isLoading } = useOrgTenantUsers(paramTenantid)
  const saveMutation = useSaveTenantUser()
  const deleteMutation = useDeleteTenantUser()

  const [form, setForm] = useState(EMPTY_FORM)
  const [selectedUid, setSelectedUid] = useState(null)

  const [sepFilter,    setSepFilter]    = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [roleFilter,   setRoleFilter]   = useState('all')

  const { tenantid, tenantnm, users = [] } = data

  const filteredUsers = useMemo(() => {
    return [...users]
      .sort((a, b) => (a.email || '').toLowerCase().localeCompare((b.email || '').toLowerCase()))
      .filter((u) => {
        if (sepFilter !== 'all' && u.sep !== sepFilter) return false
        if (statusFilter === 'active' && !u.useyn) return false
        if (statusFilter === 'inactive' && u.useyn) return false
        if (roleFilter !== 'all' && u.rolecd !== roleFilter) return false
        return true
      })
  }, [users, sepFilter, statusFilter, roleFilter])

  const handleRowClick = (row) => {
    setSelectedUid(row.useruid || row.tenantnewuid)
    setForm({
      sep:          row.sep || '',
      tenantnewuid: row.tenantnewuid || '',
      useruid:      row.useruid || '',
      email:        row.email || '',
      usernm:       row.usernm || '',
      rolecd:       row.rolecd || 'U',
      useyn:        !!row.useyn,
      creatornm:    row.creatornm || '',
      createdts:    row.createdts || '',
    })
  }

  const handleNew = () => { setSelectedUid(null); setForm(EMPTY_FORM) }

  const handleSave = () => {
    if (!form.email.trim()) { message.warning(t('msg.email.required')); return }
    saveMutation.mutate(
      {
        sep: form.sep || null,
        tenantnewuid: form.tenantnewuid || null,
        tenantid: tenantid?.toString(),
        useruid: form.useruid || null,
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
    if (!form.useruid && !form.tenantnewuid) { message.warning(t('msg.select.delete')); return }

    const doDelete = (approvenote) => {
      deleteMutation.mutate(
        {
          sep: form.sep,
          tenantnewuid: form.tenantnewuid || null,
          tenantid: tenantid?.toString(),
          useruid: form.useruid,
          approvenote: approvenote || null,
        },
        {
          onSuccess: () => { message.success(t('msg.delete.success')); handleNew() },
          onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
        },
      )
    }

    if (form.sep === 'newusers') {
      let note = ''
      Modal.confirm({
        title: t('ttl.tenant.user.reject'),
        content: (
          <div>
            <p>{t('msg.tenant.user.reject.reason')}</p>
            <textarea rows={3} style={{ width: '100%' }}
              onChange={(e) => { note = e.target.value }} />
          </div>
        ),
        okText: t('btn.delete'), cancelText: t('btn.cancel'), okButtonProps: { danger: true },
        onOk: () => {
          if (!note.trim()) { Modal.error({ title: t('msg.reject.reason.required') }); return Promise.reject() }
          doDelete(note.trim())
        },
      })
    } else {
      Modal.confirm({
        title: t('btn.delete'), content: t('msg.confirm.delete'),
        okText: t('btn.delete'), cancelText: t('btn.cancel'), okButtonProps: { danger: true },
        onOk: () => doDelete(null),
      })
    }
  }

  const pageTitle = roleid === 7 && tenantnm
    ? `${t('mnu.project.users')}: ${tenantnm}` : t('mnu.project.users')

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{pageTitle}</div>
        </div>
      </div>

      {/* 필터 */}
      <div className="form-filter-group">
        <div className="filter-item">
          <label>{t('lbl.newuser')}:</label>
          {[['all', t('cod.filter_all')], ['newusers', t('cod.sep_newusers')]].map(([v, lbl]) => (
            <span key={v}>
              <input type="radio" id={`sep_${v}`} name="sepFilter" value={v}
                checked={sepFilter === v} onChange={() => setSepFilter(v)} />
              <label className="radio-label" htmlFor={`sep_${v}`}>{lbl}</label>
            </span>
          ))}
        </div>
        <div className="filter-item">
          <label>{t('lbl.status')}:</label>
          {[['all', t('cod.filter_all')], ['active', t('cod.status_active')], ['inactive', t('cod.status_inactive')]].map(([v, lbl]) => (
            <span key={v}>
              <input type="radio" id={`status_${v}`} name="statusFilter" value={v}
                checked={statusFilter === v} onChange={() => setStatusFilter(v)} />
              <label className="radio-label" htmlFor={`status_${v}`}>{lbl}</label>
            </span>
          ))}
        </div>
        <div className="filter-item">
          <label>{t('lbl.rolecd_lbl')}:</label>
          {[['all', t('cod.filter_all')], ['M', t('cod.rolecd_M')], ['U', t('cod.rolecd_U')]].map(([v, lbl]) => (
            <span key={v}>
              <input type="radio" id={`role_${v}`} name="roleFilter" value={v}
                checked={roleFilter === v} onChange={() => setRoleFilter(v)} />
              <label className="radio-label" htmlFor={`role_${v}`}>{lbl}</label>
            </span>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측 패널: 목록 */}
        <div style={{ flex: 3, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
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
                  <th style={{ width: '15%' }}>{t('thd.rolecd_thd')}</th>
                  <th style={{ width: '15%' }}>{t('thd.useyn_thd')}</th>
                  <th style={{ width: '10%' }}>{t('lbl.newuser')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={5} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : filteredUsers.length === 0 ? (
                  <tr><td colSpan={5} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : filteredUsers.map((u) => {
                  const key = u.useruid || u.tenantnewuid
                  return (
                    <tr key={key}
                      className={selectedUid === key ? 'selected-row' : ''}
                      onClick={() => handleRowClick(u)}
                    >
                      <td>{u.email}</td>
                      <td>{u.usernm}</td>
                      <td>{u.rolecd === 'M' ? t('cod.rolecd_M') : t('cod.rolecd_U')}</td>
                      <td style={{ textAlign: 'center' }}>{u.useyn ? '✔' : ''}</td>
                      <td>{u.sep === 'newusers' ? t('cod.sep_newusers') : ''}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측 패널: 상세 */}
        <div style={{ flex: 7, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
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
            <input type="text" value={form.email}
              onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))} />
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
    </div>
  )
}
