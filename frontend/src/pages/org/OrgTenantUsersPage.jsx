import { useState, useMemo } from 'react'
import { App, Modal } from 'antd'
import { useSearchParams } from 'react-router-dom'
import { PlusOutlined, SaveOutlined, DeleteOutlined, ExportOutlined, CheckCircleFilled } from '@ant-design/icons'
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
        onError: (err) => {
          const detail = err.response?.data?.detail
          message.error((typeof detail === 'string' && t(detail)) || t('msg.save.error'))
        },
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
          onError: (err) => {
            const detail = err.response?.data?.detail
            message.error((typeof detail === 'string' && t(detail)) || t('msg.delete.error'))
          },
        },
      ),
    })
  }

  const pageTitle = roleid === 7 && tenantnm
    ? `${t('ttl.tenant.users')}: ${tenantnm}` : t('ttl.tenant.users')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 171px)', overflow: 'hidden' }}>
      <div className="page-title" style={{ flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{pageTitle}</div>
        </div>
      </div>

      {/* 필터 */}
      <div className="panel-section" style={{ display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap', flexShrink: 0, marginBottom: 16 }}>
        <div className="filter-item">
          <label style={{ fontWeight: 'bold' }}>{t('lbl.status')}</label>
          <div className="segmented" style={{ height: 32 }}>
            {[['all', t('cod.filter_all')], ['active', t('cod.status_active')], ['inactive', t('cod.status_inactive')]].map(([v, lbl]) => (
              <button
                key={v}
                type="button"
                className={`segmented-item${statusFilter === v ? ' active' : ''}`}
                style={{ padding: '0 14px', display: 'flex', alignItems: 'center' }}
                onClick={() => setStatusFilter(v)}
              >
                {lbl}
              </button>
            ))}
          </div>
        </div>
        <div className="filter-item">
          <label style={{ fontWeight: 'bold' }}>{t('lbl.rolecd_lbl')}</label>
          <div className="segmented" style={{ height: 32 }}>
            {[['all', t('cod.filter_all')], ['M', t('cod.rolecd_M')], ['U', t('cod.rolecd_U')]].map(([v, lbl]) => (
              <button
                key={v}
                type="button"
                className={`segmented-item${roleFilter === v ? ' active' : ''}`}
                style={{ padding: '0 14px', display: 'flex', alignItems: 'center' }}
                onClick={() => setRoleFilter(v)}
              >
                {lbl}
              </button>
            ))}
          </div>
        </div>
        <div className="filter-item">
          <label style={{ fontWeight: 'bold' }}>{t('lbl.servicecd')}</label>
          <div className="segmented" style={{ height: 32 }}>
            {serviceCodes.map((c) => (
              <button
                key={c.codevalue}
                type="button"
                className={`segmented-item${serviceFilters.includes(c.codevalue) ? ' active' : ''}`}
                style={{ padding: '0 14px', display: 'flex', alignItems: 'center' }}
                onClick={() => toggleServiceFilter(c.codevalue)}
              >
                {t(c.term_key) || c.default_name}
              </button>
            ))}
          </div>
        </div>
      </div>

      {service_summary.length > 0 && (
        <div className="panel-section" style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 24, flexShrink: 0, marginBottom: 16, fontSize: 13 }}>
          <span style={{ color: '#888', flexShrink: 0 }}>{t('lbl.service.usage')}: </span>
          {serviceCodes.map((svc) => {
            const s = service_summary.find((r) => r.servicecd === svc.codevalue)
            if (!s) return null
            const label = t(svc.term_key) || svc.default_name
            const countText = s.total_users != null
              ? t('inf.service.usage.count').replace('{current}', s.current_users).replace('{total}', s.total_users)
              : t('inf.service.usage.nolimit').replace('{current}', s.current_users)
            return (
              <span key={s.servicecd}>
                {label} {countText}
              </span>
            )
          })}
        </div>
      )}

      <div style={{ flex: 1, display: 'flex', gap: 24, minHeight: 0 }}>
        {/* 좌측 패널: 목록 */}
        <div className="panel-section" style={{ flex: 1.5, display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0, overflow: 'hidden' }}>
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
                {t('lbl.count.docs').replace('{n}', filteredUsers.length)}
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {user?.tenantmanager === 'Y' && (
                <>
                  <button
                    className="btn btn-secondary"
                    type="button"
                    onClick={() => openInTab('org/invite-members')}
                  >
                    {t('btn.invite.members.manage')}<ExportOutlined style={{ marginLeft: 6 }} />
                  </button>
                  <span style={{ color: '#d9d9d9' }}>|</span>
                </>
              )}
              <button className="btn btn-primary" type="button" onClick={handleNew}>
                <PlusOutlined style={{ marginRight: 6 }} />{t('btn.new')}
              </button>
            </div>
          </div>
          <div className="table-container" style={{ flex: 1, height: 'auto', overflowY: 'auto' }}>
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
                    <td style={{ textAlign: 'center' }}>{u.useyn && <CheckCircleFilled style={{ color: '#2f7d4f' }} title={t('thd.useyn_thd')} />}</td>
                    <td>{serviceLabels(u.servicecds)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측 패널: 상세 */}
        <div className="panel-section" style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0, overflow: 'hidden' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', height: 60, flexShrink: 0,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveMutation.isPending || deleteMutation.isPending}>
                <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
              </button>
              {selectedUid && (
                <button
                  className="btn btn-danger"
                  type="button"
                  onClick={handleDelete}
                  disabled={deleteMutation.isPending}
                  title={t('btn.delete')}
                  style={{ width: 38, height: 38, padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                >
                  <DeleteOutlined />
                </button>
              )}
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>

          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.email')}:</label>
            <input type="text" value={form.email}
              onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))} style={{ height: 38 }} />
          </div>

          <div className="form-group">
            <label>{t('lbl.usernm')}:</label>
            <input type="text" value={form.usernm} disabled style={{ ...roStyle, height: 38 }} />
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
    </div>
  )
}
