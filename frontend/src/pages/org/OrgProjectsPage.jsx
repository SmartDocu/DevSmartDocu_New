import { useState } from 'react'
import { App, Modal, Popconfirm } from 'antd'
import { useSearchParams } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useOrgProjects, useSaveOrgProject, useDeleteOrgProject } from '@/hooks/useOrg'

const roStyle = { backgroundColor: '#f0f0f0', color: '#555', border: '1px solid #ccc' }

const EMPTY_FORM = {
  projectid: '', projectnm: '', projectdesc: '',
  useyn: true, creatornm: '', createdts: '',
}

export default function OrgProjectsPage() {
  const { message } = App.useApp()
  const [searchParams] = useSearchParams()
  const { user } = useAuthStore()
  useLangStore((s) => s.translations)
  const roleid = user?.roleid

  const paramTenantid = roleid === 7 ? searchParams.get('tenantid') : null

  const { data = {}, isLoading } = useOrgProjects(paramTenantid)
  const saveMutation = useSaveOrgProject()
  const deleteMutation = useDeleteOrgProject()

  const [form, setForm] = useState(EMPTY_FORM)
  const [selectedRow, setSelectedRow] = useState(null)

  const { projects = [], tenantnm, tenantid } = data

  const handleRowClick = (row) => {
    setSelectedRow(row)
    setForm({
      projectid:   row.projectid || '',
      projectnm:   row.projectnm || '',
      projectdesc: row.projectdesc || '',
      useyn:       !!row.useyn,
      creatornm:   row.creatornm || '',
      createdts:   row.createdts || '',
    })
  }

  const handleNew = () => { setSelectedRow(null); setForm(EMPTY_FORM) }

  const handleSave = () => {
    if (!form.projectnm.trim()) { message.warning(t('msg.projectnm.required')); return }
    saveMutation.mutate(
      {
        projectid:   form.projectid || null,
        tenantid:    tenantid?.toString() || null,
        projectnm:   form.projectnm,
        projectdesc: form.projectdesc || null,
        useyn:       form.useyn ?? true,
      },
      {
        onSuccess: () => { message.success(t('msg.save.success')); handleNew() },
        onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
      },
    )
  }

  const handleDelete = () => {
    if (!form.projectid) { message.warning(t('msg.select.delete')); return }
    Modal.confirm({
      title: t('btn.delete'), content: t('msg.confirm.delete'),
      okText: t('btn.delete'), cancelText: t('btn.cancel'), okButtonProps: { danger: true },
      onOk: () => deleteMutation.mutate(
        { projectid: form.projectid },
        {
          onSuccess: () => { message.success(t('msg.delete.success')); handleNew() },
          onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
        },
      ),
    })
  }

  const pageTitle = tenantnm
    ? `${t('mnu.project.projects')}: ${tenantnm}` : t('mnu.project.projects')

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{pageTitle}</div>
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
                  <th style={{ width: '40%' }}>{t('thd.projectnm_thd')}</th>
                  <th style={{ width: '45%' }}>{t('thd.projectdesc_thd')}</th>
                  <th style={{ width: '15%' }}>{t('thd.useyn_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : projects.length === 0 ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : projects.map((p) => (
                  <tr key={p.projectid}
                    className={selectedRow?.projectid === p.projectid ? 'selected-row' : ''}
                    onClick={() => handleRowClick(p)}
                  >
                    <td>{p.projectnm}</td>
                    <td style={{ whiteSpace: 'pre-wrap' }}>{p.projectdesc || ''}</td>
                    <td style={{ textAlign: 'center' }}>{p.useyn ? '✔' : ''}</td>
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
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
<button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveMutation.isPending}>
                {t('btn.save')}
              </button>
              {selectedRow && (
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
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.projectnm_lbl')}:</label>
            <input type="text" value={form.projectnm}
              onChange={(e) => setForm(f => ({ ...f, projectnm: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.desc_lbl')}:</label>
            <textarea rows={3} value={form.projectdesc} style={{ resize: 'vertical' }}
              onChange={(e) => setForm(f => ({ ...f, projectdesc: e.target.value }))} />
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
