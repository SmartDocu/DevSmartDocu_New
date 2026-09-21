import { useState } from 'react'
import { App } from 'antd'
import { SaveOutlined, DeleteOutlined } from '@ant-design/icons'
import { useLangStore, t } from '@/stores/langStore'
import { useAuthStore } from '@/stores/authStore'
import { useOrgTenantLlms, useSaveTenantLlm, useDeleteTenantLlm } from '@/hooks/useOrg'

const EMPTY_FORM = { projectnm: '', llmmodelnm: '', apikey: '' }

export default function OrgTenantLlmsPage() {
  const { message, modal } = App.useApp()
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
    )
  }

  const handleDelete = () => {
    if (!selectedId) return
    modal.confirm({
      title: t('btn.delete'),
      content: t('msg.confirm.delete'),
      okText: t('btn.delete'), cancelText: t('btn.cancel'), okButtonProps: { danger: true },
      onOk: () => {
        deleteMutation.mutate(
          { projectid: selectedId },
          { onSuccess: () => { setSelectedId(null); setForm(EMPTY_FORM) } }
        )
      },
    })
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('ttl.project.llm')}</div>
        </div>
      </div>

      <div className="panel-section" style={{ background: '#f9fbe7', color: '#6a7d3c', fontSize: 13, marginBottom: 16, padding: '13px 18px' }}>
        ＊ {t('msg.llmkey.notice')}
      </div>

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
        {/* 좌측 패널: 프로젝트 테이블 */}
        <div className="panel-section" style={{ flex: 1.5, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 288px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h3 style={{ margin: 0, lineHeight: 1 }}>{t('ttl.project.llm')}</h3>
              <span style={{
                display: 'inline-flex', alignItems: 'center', lineHeight: 1,
                font: '500 11px monospace', color: '#8d9199', background: '#f2efe9',
                borderRadius: 6, padding: '5px 8px 4px',
              }}>
                {t('lbl.count.docs').replace('{n}', projects.length)}
              </span>
            </div>
            <div />
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
            <table id="project-table" className="table table-bordered table-sm" style={{ cursor: 'pointer' }}>
              <thead>
                <tr>
                  <th style={{ width: '30%' }}>{t('thd.projectnm_thd')}</th>
                  <th style={{ width: '40%' }}>{t('thd.projectdesc_thd')}</th>
                  <th style={{ width: '30%' }}>{t('thd.llmmodelnm_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : projects.length === 0 ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : projects.map((p) => (
                  <tr key={p.projectid}
                    className={selectedId === p.projectid?.toString() ? 'selected-row' : ''}
                    onClick={() => handleRowClick(p)}
                  >
                    <td>{p.projectnm}</td>
                    <td>{p.projectdesc || ''}</td>
                    <td>{p.llmmodelfullnm || ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </div>
        </div>

        {/* 우측 패널: LLM 상세 */}
        <div className="panel-section" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 288px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.llm.detail')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveMutation.isPending || deleteMutation.isPending}>
                <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
              </button>
              {selectedId && (
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
            <label htmlFor="projectid"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.projectnm_lbl')}:</label>
            <select id="projectid" value={selectedId || ''} style={{ height: 38 }}
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
            <select id="llmmodelnm" value={form.llmmodelnm} style={{ height: 38 }}
              onChange={(e) => setForm(f => ({ ...f, llmmodelnm: e.target.value }))}>
              <option value="">{t('msg.select')}</option>
              {llmmodels.map((m) => (
                <option key={m.llmmodelnm} value={m.llmmodelnm}>{m.llmmodelnm}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>{t('lbl.apikey')}:</label>
            <input type="password" value={form.apikey} placeholder={t('msg.placeholder.secret.change')}
              autoComplete="new-password" style={{ height: 38 }}
              onChange={(e) => setForm(f => ({ ...f, apikey: e.target.value }))} />
            <small style={{ color: '#888' }}>{t('inf.secret.hidden')}</small>
          </div>
          </div>
        </div>
      </div>
    </div>
  )
}
