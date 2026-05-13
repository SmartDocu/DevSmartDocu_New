import { useState } from 'react'
import { App, Modal } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useOrgTenantLlms, useSaveTenantLlm, useDeleteTenantLlm } from '@/hooks/useOrg'

const roStyle = { backgroundColor: '#f0f0f0', color: '#555', border: '1px solid #ccc' }

const EMPTY_FORM = { jobnm: '', llmmodelnm: '', apikey: '' }

export default function OrgTenantLlmsPage() {
  const { message } = App.useApp()
  useLangStore((s) => s.translations)
  const { data = {}, isLoading } = useOrgTenantLlms()
  const saveMutation = useSaveTenantLlm()
  const deleteMutation = useDeleteTenantLlm()

  const [form, setForm] = useState(EMPTY_FORM)
  const [selectedType, setSelectedType] = useState(null)  // 'tenant' | 'project'
  const [selectedId,   setSelectedId]   = useState(null)
  const [selectedRow,  setSelectedRow]  = useState(null)

  const { tenant = {}, projects = [], llmmodels = [] } = data

  const handleTenantRowClick = (row) => {
    setSelectedType('tenant')
    setSelectedId(row.tenantid?.toString())
    setSelectedRow(row)
    setForm({ jobnm: row.tenantnm || '', llmmodelnm: row.llmmodelnm || '', apikey: '' })
  }

  const handleProjectRowClick = (row) => {
    setSelectedType('project')
    setSelectedId(row.projectid?.toString())
    setSelectedRow(row)
    setForm({ jobnm: row.projectnm || '', llmmodelnm: row.llmmodelnm || '', apikey: '' })
  }

  const handleSave = () => {
    if (!selectedType) { message.warning(t('msg.select')); return }
    const body = selectedType === 'tenant'
      ? { tenantid: selectedId, llmmodelnm: form.llmmodelnm || null, apikey: form.apikey || '' }
      : { projectid: selectedId, llmmodelnm: form.llmmodelnm || null, apikey: form.apikey || '' }
    saveMutation.mutate(body, {
      onSuccess: () => message.success(t('msg.save.success')),
      onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
    })
  }

  const handleDelete = () => {
    if (!selectedType) return
    Modal.confirm({
      title: t('btn.delete'),
      content: t('msg.confirm.delete'),
      okText: t('btn.delete'), cancelText: t('btn.cancel'), okButtonProps: { danger: true },
      onOk: () => {
        const body = selectedType === 'tenant' ? { tenantid: selectedId } : { projectid: selectedId }
        deleteMutation.mutate(body, {
          onSuccess: () => { message.success(t('msg.delete.success')); setSelectedType(null); setSelectedId(null); setForm(EMPTY_FORM) },
          onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
        })
      },
    })
  }

  const jobnmLabel = selectedType === 'tenant' ? t('lbl.tenantnm')
    : selectedType === 'project' ? t('lbl.projectnm_lbl')
    : t('lbl.jobnm')

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('mnu.project.llm')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측 패널: 기업 + 프로젝트 테이블 */}
        <div style={{ flex: 3, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>

          {/* 기업 LLM */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.tenant.llm')}</h3>
            <div />
          </div>
          <div className="table-container" style={{ height: 100 }}>
            <table id="tenant-table" className="table table-bordered table-sm" style={{ cursor: 'pointer' }}>
              <thead>
                <tr>
                  <th style={{ width: '30%' }}>{t('thd.tenantnm_thd')}</th>
                  <th style={{ width: '35%' }}>{t('thd.llmmodelnm_thd')}</th>
                  <th style={{ width: '20%' }}>{t('thd.llmmodeluseyn_thd')}</th>
                  <th style={{ width: '15%' }}>{t('thd.activeyn_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : tenant.tenantid ? (
                  <tr
                    className={selectedType === 'tenant' && selectedId === tenant.tenantid?.toString() ? 'selected-row' : ''}
                    onClick={() => handleTenantRowClick(tenant)}
                  >
                    <td>{tenant.tenantnm}</td>
                    <td>{tenant.llmmodelnicknm || ''}</td>
                    <td style={{ textAlign: 'center' }}>{tenant.llmmodeluseyn ? t('cod.llmmodeluseyn_C') : t('cod.llmmodeluseyn_S')}</td>
                    <td style={{ textAlign: 'center' }}>{tenant.llmmodelactiveyn ? '✔' : ''}</td>
                  </tr>
                ) : (
                  <tr><td colSpan={4} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {/* 프로젝트 LLM */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8, marginTop: 24 }}>
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
                {projects.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : projects.map((p) => (
                  <tr key={p.projectid}
                    className={selectedType === 'project' && selectedId === p.projectid?.toString() ? 'selected-row' : ''}
                    onClick={() => handleProjectRowClick(p)}
                  >
                    <td>{p.projectnm}</td>
                    <td>{p.projectdesc || ''}</td>
                    <td>{p.llmmodelnicknm || ''}</td>
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
              {selectedType && (
                <button className="btn btn-danger" type="button" onClick={handleDelete} disabled={deleteMutation.isPending}>
                  {t('btn.delete')}
                </button>
              )}
            </div>
          </div>

          <div className="form-group">
            <label>{jobnmLabel}:</label>
            <input type="text" value={form.jobnm} readOnly style={roStyle} />
          </div>

          <div className="form-group">
            <label htmlFor="llmmodelnm">{t('lbl.llmmodelnm')}:</label>
            <select id="llmmodelnm" value={form.llmmodelnm}
              onChange={(e) => setForm(f => ({ ...f, llmmodelnm: e.target.value }))}>
              <option value="">{t('msg.select')}</option>
              {llmmodels.map((m) => (
                <option key={m.llmmodelnm} value={m.llmmodelnm}>{m.llmmodelnicknm}</option>
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
