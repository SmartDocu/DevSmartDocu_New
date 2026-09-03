import { useState } from 'react'
import { App, Modal } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useAuthStore } from '@/stores/authStore'
import { useOrgTenantLlms, useSaveTenantLlm, useDeleteTenantLlm } from '@/hooks/useOrg'

const EMPTY_FORM = { projectnm: '', llmmodelnm: '', apikey: '' }

export default function OrgTenantLlmsPage() {
  const { message } = App.useApp()
  useLangStore((s) => s.translations)
  const accountuid = useAuthStore((s) => s.user?.accountuid)
  const { data = {}, isLoading } = useOrgTenantLlms(accountuid)
  const saveMutation = useSaveTenantLlm()
  const deleteMutation = useDeleteTenantLlm()

  const [form, setForm] = useState(EMPTY_FORM)
  const [selectedId, setSelectedId] = useState(null)

  const { projects = [], llmmodels = [], account_projects = [] } = data

  const handleRowClick = (row) => {
    setSelectedId(row.projectid?.toString())
    setForm({ projectnm: row.projectnm || '', llmmodelnm: row.llmmodelnm || '', apikey: '' })
  }

  const handleProjectSelect = (pid) => {
    setSelectedId(pid || null)
    const found = projects.find((p) => p.projectid?.toString() === pid)
    setForm({
      projectnm: found?.projectnm || '',
      llmmodelnm: found?.llmmodelnm || '',
      apikey: '',
    })
  }

  const handleSave = () => {
    if (!selectedId) { message.warning(t('msg.select')); return }
    saveMutation.mutate(
      { projectid: selectedId, llmmodelnm: form.llmmodelnm || null, apikey: form.apikey || '' },
      {
        onSuccess: () => message.success(t('msg.save.success')),
        onError: (err) => message.error(t(err.response?.data?.detail) || t('msg.save.error')),
      }
    )
  }

  const handleDelete = () => {
    if (!selectedId) return
    Modal.confirm({
      title: t('btn.delete'),
      content: t('msg.confirm.delete'),
      okText: t('btn.delete'), cancelText: t('btn.cancel'), okButtonProps: { danger: true },
      onOk: () => {
        deleteMutation.mutate(
          { projectid: selectedId },
          {
            onSuccess: () => { message.success(t('msg.delete.success')); setSelectedId(null); setForm(EMPTY_FORM) },
            onError: (err) => message.error(t(err.response?.data?.detail) || t('msg.delete.error')),
          }
        )
      },
    })
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.project.llm')}</div>
        </div>
      </div>

      <div style={{ background: '#f9fbe7', padding: '4px 10px', borderRadius: 6, color: '#6a7d3c', marginBottom: 10 }}>
        <span style={{ color: '#6a7d3c', fontSize: 13 }}>＊ {t('msg.llmkey.notice')}</span>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측 패널: 프로젝트 테이블 */}
        <div style={{ flex: 3, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.project.llm')}</h3>
            <div />
          </div>
          <div className="table-container" style={{ height: 500 }}>
            <table id="project-table" className="table table-bordered table-sm" style={{ cursor: 'pointer' }}>
              <thead>
                <tr>
                  <th style={{ width: '25%' }}>{t('thd.projectnm_thd')}</th>
                  <th style={{ width: '35%' }}>{t('thd.projectdesc_thd')}</th>
                  <th style={{ width: '25%' }}>{t('thd.llmmodelnm_thd')}</th>
                  <th style={{ width: '15%' }}>{t('thd.activeyn_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : projects.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : projects.map((p) => (
                  <tr key={p.projectid}
                    className={selectedId === p.projectid?.toString() ? 'selected-row' : ''}
                    onClick={() => handleRowClick(p)}
                  >
                    <td>{p.projectnm}</td>
                    <td>{p.projectdesc || ''}</td>
                    <td>{p.llmmodelfullnm || ''}</td>
                    <td style={{ textAlign: 'center' }}>{p.llmmodelactiveyn ? '✔' : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측 패널: LLM 상세 */}
        <div style={{ flex: 2, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.llm.detail')}</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveMutation.isPending}>
                {t('btn.save')}
              </button>
              {selectedId && (
                <button className="btn btn-danger" type="button" onClick={handleDelete} disabled={deleteMutation.isPending}>
                  {t('btn.delete')}
                </button>
              )}
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="projectid"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.projectnm_lbl')}:</label>
            <select id="projectid" value={selectedId || ''}
              onChange={(e) => handleProjectSelect(e.target.value)}>
              <option value="">{t('msg.select')}</option>
              {account_projects.map((p) => (
                <option key={p.projectid} value={p.projectid?.toString()}>
                  {p.projectnm}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="llmmodelnm">{t('lbl.llmmodelnm')}:</label>
            <select id="llmmodelnm" value={form.llmmodelnm}
              onChange={(e) => setForm(f => ({ ...f, llmmodelnm: e.target.value }))}>
              <option value="">{t('msg.select')}</option>
              {llmmodels.map((m) => (
                <option key={m.llmmodelnm} value={m.llmmodelnm}>{m.llmmodelnm}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>{t('lbl.apikey')}:</label>
            <input type="password" value={form.apikey} placeholder={t('msg.placeholder.password.change')}
              autoComplete="new-password"
              onChange={(e) => setForm(f => ({ ...f, apikey: e.target.value }))} />
            <small style={{ color: '#888' }}>{t('inf.password.hidden')}</small>
          </div>
        </div>
      </div>
    </div>
  )
}
