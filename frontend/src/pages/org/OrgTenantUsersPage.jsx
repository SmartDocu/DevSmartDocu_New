import { useState, useMemo } from 'react'
import { App, Modal, Popconfirm } from 'antd'
import { useSearchParams } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useOrgTenantUsers, useSaveTenantUser, useDeleteTenantUser } from '@/hooks/useOrg'
import { useMenuCodes } from '@/hooks/useMenus'
import { useOpenInTab } from '@/hooks/useOpenInTab'

const roStyle = { backgroundColor: '#f0f0f0', color: '#555', border: '1px solid #ccc' }

const EMPTY_FORM = {
  useruid: '',
  email: '', usernm: '', rolecd: 'U', useyn: true, creatornm: '', createdts: '',
  servicecds: [],
}

export default function OrgTenantUsersPage() {
  const { message } = App.useApp()
  const [searchParams] = useSearchParams()
  const { user } = useAuthStore()
  useLangStore((s) => s.translations)
  const roleid = user?.roleid
  const accountuid = user?.accountuid

  const paramTenantid = roleid === 7 ? searchParams.get('tenantid') : null

  const { data = {}, isLoading } = useOrgTenantUsers(paramTenantid, accountuid)
  const saveMutation = useSaveTenantUser()
  const deleteMutation = useDeleteTenantUser()
  const { data: roleCodes = [] } = useMenuCodes('rolecd')
  const { data: allServiceCodes = [] } = useMenuCodes('servicecd')

  const [form, setForm] = useState(EMPTY_FORM)
  const [selectedUid, setSelectedUid] = useState(null)

  const openInTab = useOpenInTab()

  const [statusFilter,   setStatusFilter]   = useState('all')
  const [roleFilter,     setRoleFilter]     = useState('all')
  const [serviceFilters, setServiceFilters] = useState([])

  const { tenantid, tenantnm, users = [], available_servicecds = [], service_summary = [] } = data
  const serviceCodes = allServiceCodes.filter((c) => available_servicecds.includes(c.codevalue))

  const serviceLabels = (scds) => allServiceCodes
    .filter((c) => (scds || []).includes(c.codevalue))
    .map((c) => t(c.term_key) || c.default_name)
    .join(', ')

  const filteredUsers = useMemo(() => {
    return [...users]
      .sort((a, b) => (a.email || '').toLowerCase().localeCompare((b.email || '').toLowerCase()))
      .filter((u) => {
        if (statusFilter === 'active' && !u.useyn) return false
        if (statusFilter === 'inactive' && u.useyn) return false
        if (roleFilter !== 'all' && u.rolecd !== roleFilter) return false
        if (serviceFilters.length > 0 && !(u.servicecds || []).some((s) => serviceFilters.includes(s))) return false
        return true
      })
  }, [users, statusFilter, roleFilter, serviceFilters])

  const toggleServiceFilter = (v) => {
    setServiceFilters((f) => (f.includes(v) ? f.filter((x) => x !== v) : [...f, v]))
  }

  const toggleFormServicecd = (v) => {
    if (!available_servicecds.includes(v)) return
    setForm((f) => ({
      ...f,
      servicecds: f.servicecds.includes(v) ? f.servicecds.filter((x) => x !== v) : [...f.servicecds, v],
    }))
  }

  const handleRowClick = (row) => {
    setSelectedUid(row.useruid)
    setForm({
      useruid:      row.useruid || '',
      email:        row.email || '',
      usernm:       row.usernm || '',
      rolecd:       row.rolecd || 'U',
      useyn:        !!row.useyn,
      creatornm:    row.creatornm || '',
      createdts:    row.createdts || '',
      servicecds:   row.servicecds || [],
    })
  }

  const handleNew = () => { setSelectedUid(null); setForm(EMPTY_FORM) }

  const handleSave = () => {
    if (!form.email.trim()) { message.warning(t('msg.email.required')); return }
    if (form.servicecds.length === 0) { message.warning(t('msg.servicecd.required')); return }
    saveMutation.mutate(
      {
        tenantid: tenantid?.toString(),
        useruid: form.useruid || null,
        email: form.email,
        rolecd: form.rolecd || 'U',
        useyn: form.useyn ?? true,
        servicecds: form.servicecds,
        accountuid: accountuid || null,
      },
      {
        onSuccess: () => { message.success(t('msg.save.success')); handleNew() },
        onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
      },
    )
  }

  const handleDelete = () => {
    if (!form.useruid) { message.warning(t('msg.select.delete')); return }

    Modal.confirm({
      title: t('btn.delete'), content: t('msg.confirm.delete'),
      okText: t('btn.delete'), cancelText: t('btn.cancel'), okButtonProps: { danger: true },
      onOk: () => deleteMutation.mutate(
        {
          tenantid: tenantid?.toString(),
          useruid: form.useruid,
          accountuid: accountuid || null,
        },
        {
          onSuccess: () => { message.success(t('msg.delete.success')); handleNew() },
          onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
        },
      ),
    })
  }

  const pageTitle = roleid === 7 && tenantnm
    ? `${t('mnu.tenant.users')}: ${tenantnm}` : t('mnu.tenant.users')

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{pageTitle}</div>
        </div>
        {user?.tenantmanager === 'Y' && (
          <button
            className="btn btn-primary"
            type="button"
            onClick={() => openInTab('org/invite-members')}
          >
            {t('btn.invite.members.manage')}
          </button>
        )}
      </div>

      {/* 필터 */}
      <div className="form-filter-group">
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
        <div className="filter-item">
          <label>{t('lbl.servicecd')}:</label>
          {serviceCodes.map((c) => (
            <span key={c.codevalue}>
              <input type="checkbox" id={`svcf_${c.codevalue}`}
                checked={serviceFilters.includes(c.codevalue)}
                onChange={() => toggleServiceFilter(c.codevalue)} />
              <label className="radio-label" htmlFor={`svcf_${c.codevalue}`}>{t(c.term_key) || c.default_name}</label>
            </span>
          ))}
        </div>
      </div>

      {service_summary.length > 0 && (
        <div className="form-filter-group">
          <div className="filter-item">
            <label style={{ width: 'auto', marginRight: 16 }}>{t('lbl.service.usage')}:</label>
            {serviceCodes.map((svc) => {
              const s = service_summary.find((r) => r.servicecd === svc.codevalue)
              if (!s) return null
              const label = t(svc.term_key) || svc.default_name
              const countText = s.total_users != null
                ? t('inf.service.usage.count').replace('{current}', s.current_users).replace('{total}', s.total_users)
                : t('inf.service.usage.nolimit').replace('{current}', s.current_users)
              return (
                <span key={s.servicecd} className="radio-label" style={{ marginRight: 24 }}>
                  {label} {countText}
                </span>
              )
            })}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측 패널: 목록 */}
        <div style={{ flex: 6, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleNew}>{t('btn.new')}</button>
          </div>
          <div className="table-container">
            <table className="table table-bordered table-sm" style={{ cursor: 'pointer' }}>
              <thead>
                <tr>
                  <th style={{ width: '30%' }}>{t('thd.email_thd')}</th>
                  <th style={{ width: '20%' }}>{t('thd.usernm_thd')}</th>
                  <th style={{ width: '12%' }}>{t('thd.rolecd_thd')}</th>
                  <th style={{ width: '10%' }}>{t('thd.useyn_thd')}</th>
                  <th style={{ width: '28%' }}>{t('thd.servicecd_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={5} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : filteredUsers.length === 0 ? (
                  <tr><td colSpan={5} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : filteredUsers.map((u) => (
                  <tr key={u.useruid}
                    className={selectedUid === u.useruid ? 'selected-row' : ''}
                    onClick={() => handleRowClick(u)}
                  >
                    <td>{u.email}</td>
                    <td>{u.usernm}</td>
                    <td>{u.rolecd === 'M' ? t('cod.rolecd_M') : t('cod.rolecd_U')}</td>
                    <td style={{ textAlign: 'center' }}>{u.useyn ? '✔' : ''}</td>
                    <td>{serviceLabels(u.servicecds)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측 패널: 상세 */}
        <div style={{ flex: 4, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
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
              {roleCodes.map((code) => (
                <span key={code.codevalue} style={{ display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }}>
                  <input type="radio" name="rolecd" value={code.codevalue}
                    checked={form.rolecd === code.codevalue}
                    onChange={() => setForm(f => ({ ...f, rolecd: code.codevalue }))} />
                  <span>{t(code.term_key) || code.default_name}</span>
                </span>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label>{t('lbl.useyn_lbl')}:</label>
            <div style={{ paddingLeft: 60 }}>
              <input type="checkbox" checked={form.useyn}
                onChange={(e) => setForm(f => ({ ...f, useyn: e.target.checked }))} />
            </div>
          </div>

          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.servicecd')}:</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 32, flexWrap: 'wrap', paddingLeft: 60 }}>
              {allServiceCodes.map((c) => {
                const subscribed = available_servicecds.includes(c.codevalue)
                return (
                  <span key={c.codevalue} style={{ display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap', color: subscribed ? undefined : '#aaa' }}>
                    <input type="checkbox" checked={form.servicecds.includes(c.codevalue)}
                      disabled={!subscribed}
                      onChange={() => toggleFormServicecd(c.codevalue)} />
                    <span>
                      {t(c.term_key) || c.default_name}
                      {!subscribed && ` (${t('lbl.service.not_subscribed')})`}
                    </span>
                  </span>
                )
              })}
            </div>
          </div>

        </div>
      </div>
    </div>
  )
}
