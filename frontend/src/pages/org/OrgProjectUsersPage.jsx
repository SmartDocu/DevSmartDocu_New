import { useState, useEffect } from 'react'
import { App, Select } from 'antd'
import { useSearchParams } from 'react-router-dom'
import { PlusOutlined, SaveOutlined, DeleteOutlined, CheckCircleFilled, SearchOutlined } from '@ant-design/icons'
import { useLangStore, t } from '@/stores/langStore'
import {
  useOrgProjectUsers,
  useSaveProjectUser,
  useDeleteProjectUser,
} from '@/hooks/useOrg'
import { useMenuCodes } from '@/hooks/useMenus'

const roStyle = { backgroundColor: '#f0f0f0', color: '#555', border: '1px solid #ccc' }

const EMPTY_FORM = {
  useruid: '', email: '', usernm: '', rolecd: 'U',
  useyn: true, creatornm: '', createdts: '',
}

export default function OrgProjectUsersPage() {
  const { message, modal } = App.useApp()
  const [searchParams, setSearchParams] = useSearchParams()
  useLangStore((s) => s.translations)

  const paramProjectid = searchParams.get('projects') || ''
  const [selectedProjectid, setSelectedProjectid] = useState(paramProjectid)

  const { data = {}, isLoading } = useOrgProjectUsers(selectedProjectid)
  const saveMutation = useSaveProjectUser()
  const deleteMutation = useDeleteProjectUser()
  const { data: roleCodes = [] } = useMenuCodes('rolecd')
  const { data: serviceCodes = [] } = useMenuCodes('servicecd')

  const [form, setForm] = useState(EMPTY_FORM)
  const [selectedUid, setSelectedUid] = useState(null)
  const [userModalOpen, setUserModalOpen] = useState(false)

  const { projects = [], projectusers = [], tenantusers = [] } = data

  const serviceLabel = (scd) => {
    const found = serviceCodes.find((c) => c.codevalue === scd)
    return found ? (t(found.term_key) || found.default_name) : scd
  }


  useEffect(() => {
    if (paramProjectid) setSelectedProjectid(paramProjectid)
  }, [paramProjectid])

  const handleProjectChange = (value) => {
    value = value ? String(value) : ''
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
        onError: (err) => {
          const detail = err.response?.data?.detail
          message.error((typeof detail === 'string' && t(detail)) || t('msg.save.error'))
        },
      },
    )
  }

  const handleDelete = () => {
    if (!form.useruid) { message.warning(t('msg.select.delete')); return }
    modal.confirm({
      title: t('msg.confirm.delete'),
      okText: t('btn.delete'),
      cancelText: t('btn.cancel'),
      okButtonProps: { danger: true },
      onOk: () => deleteMutation.mutate(
        { projectid: selectedProjectid, useruid: form.useruid },
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

  const handleModalUserSelect = (u) => {
    setForm(f => ({ ...f, email: u.email, usernm: u.usernm }))
    setUserModalOpen(false)
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('ttl.project.project_users')}</div>
        </div>
      </div>

      {/* 프로젝트 선택 필터 */}
      <div className="panel-section" style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
        <div className="filter-item">
          <label htmlFor="projects" style={{ fontWeight: 'bold' }}>{t('lbl.project')}</label>
          <Select
            id="projects"
            value={selectedProjectid || undefined}
            onChange={handleProjectChange}
            allowClear
            style={{ width: 300 }}
            placeholder={t('msg.select.project')}
            options={projects.map((p) => ({
              value: String(p.projectid),
              label: p.servicecd ? `${p.projectnm} - ${serviceLabel(p.servicecd)}` : p.projectnm,
            }))}
          />
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
        {/* 좌측 패널: 목록 */}
        <div className="panel-section" style={{ flex: 1.5, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 306px)' }}>
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
                {t('lbl.count.docs').replace('{n}', projectusers.length)}
              </span>
            </div>
            <button className="btn btn-primary" type="button" onClick={handleNew}>
              <PlusOutlined style={{ marginRight: 6 }} />{t('btn.new')}
            </button>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
            <table className="table table-bordered table-sm" style={{ cursor: 'pointer' }}>
              <thead>
                <tr>
                  <th style={{ width: '28%' }}>{t('thd.email_thd')}</th>
                  <th style={{ width: '18%' }}>{t('thd.usernm_thd')}</th>
                  <th style={{ width: '14%' }}>{t('thd.rolecd_thd')}</th>
                  <th style={{ width: '10%' }}>{t('thd.useyn_thd')}</th>
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
                    <td style={{ textAlign: 'center' }}>{u.useyn && <CheckCircleFilled style={{ color: '#2f7d4f' }} title={t('thd.useyn_thd')} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </div>
        </div>

        {/* 우측 패널: 상세 */}
        <div className="panel-section" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 306px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
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
            <label style={{ marginBottom: 4 }}><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.email')}:</label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input id="proj-user-email" type="text" value={form.email} placeholder={t('msg.email.required')}
                onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))} style={{ flex: 1 }} />
              <button type="button" className="btn btn-secondary" onClick={() => setUserModalOpen(true)} style={{ flexShrink: 0, whiteSpace: 'nowrap' }}>
                <SearchOutlined style={{ marginRight: 6 }} />{t('btn.lookup')}
              </button>
            </div>
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
          background: '#fff', padding: 20, width: 620, maxHeight: '80%', overflow: 'auto',
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

      <style>{`#proj-user-email { margin-top: 0 !important; }`}</style>
    </div>
  )
}
