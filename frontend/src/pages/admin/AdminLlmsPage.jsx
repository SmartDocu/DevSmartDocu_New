import { useState } from 'react'
import { App } from 'antd'
import { useAdminLlms, useSaveLlm, useDeleteLlm } from '@/hooks/useAdmin'
import { useLangStore, t } from '@/stores/langStore'

export default function AdminLlmsPage() {
  const { message, modal } = App.useApp()
  const { data = {}, isLoading } = useAdminLlms()
  const saveMutation = useSaveLlm()
  const deleteMutation = useDeleteLlm()
  useLangStore((s) => s.translations)

  const { llmmodels = [] } = data

  const EMPTY = { llmvendornm: '', llmmodelnm: '', llmmodelnicknm: '', useyn: true, isdefault: false, apikey: '' }
  const [form, setForm] = useState(EMPTY)
  const [selectedRow, setSelectedRow] = useState(null)

  const handleRowClick = (row) => {
    setSelectedRow(row)
    setForm({
      llmvendornm: row.llmvendornm || '',
      llmmodelnm: row.llmmodelnm || '',
      llmmodelnicknm: row.llmmodelnicknm || '',
      useyn: !!row.useyn,
      isdefault: !!row.isdefault,
      apikey: '',
    })
  }

  const handleNew = () => {
    setSelectedRow(null)
    setForm(EMPTY)
  }

  const handleSave = () => {
    if (!form.llmmodelnm.trim()) { message.warning(t('msg.llmmodelnm.required')); return }
    saveMutation.mutate(
      {
        llmmodelnm: form.llmmodelnm,
        llmvendornm: form.llmvendornm || null,
        llmmodelnicknm: form.llmmodelnicknm || null,
        useyn: form.useyn,
        isdefault: form.isdefault,
        apikey: form.apikey || '',
      },
      { onSuccess: handleNew },
    )
  }

  const handleDelete = () => {
    if (!selectedRow) { message.warning(t('msg.select.delete')); return }
    modal.confirm({
      title: t('msg.confirm.delete'),
      content: `"${selectedRow.llmmodelnm}" ${t('msg.confirm.delete')}`,
      okText: t('btn.delete'), cancelText: t('btn.cancel'), okButtonProps: { danger: true },
      onOk: () => deleteMutation.mutate(selectedRow.llmmodelnm, { onSuccess: handleNew }),
    })
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('mnu.company.llm')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측: LLM 목록 */}
        <div style={{ flex: 5, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleNew}>
              {t('btn.new')}
            </button>
          </div>
          <div className="table-container">
            {isLoading ? (
              <div style={{ textAlign: 'center', padding: 32 }}><div className="spinner" /></div>
            ) : (
              <table id="llms-table">
                <thead>
                  <tr>
                    <th style={{ width: '15%' }}>{t('thd.llmvendornm_thd')}</th>
                    <th style={{ width: '35%' }}>{t('thd.llmmodelnm_thd')}</th>
                    <th style={{ width: '30%' }}>{t('thd.llmmodelnicknm_thd')}</th>
                    <th style={{ width: '10%' }} className="info">{t('thd.useyn_thd')}</th>
                  </tr>
                </thead>
                <tbody>
                  {llmmodels.map((llm) => (
                    <tr
                      key={llm.llmmodelnm}
                      className={selectedRow?.llmmodelnm === llm.llmmodelnm ? 'selected-row' : ''}
                      style={{ cursor: 'pointer' }}
                      onClick={() => handleRowClick(llm)}
                    >
                      <td>{llm.llmvendornm}</td>
                      <td>{llm.llmmodelnm}</td>
                      <td>{llm.llmmodelnicknm}</td>
                      <td className="info">{llm.useyn ? '✔' : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* 우측: LLM 상세 */}
        <div style={{ flex: 5, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.llm.detail')}</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveMutation.isPending}>
                {t('btn.save')}
              </button>
              {selectedRow && (
                <button className="btn btn-danger" type="button" onClick={handleDelete} disabled={deleteMutation.isPending}>
                  {t('btn.delete')}
                </button>
              )}
            </div>
          </div>
          <div className="form-group">
            <label>{t('lbl.llmvendornm')}:</label>
            <input
              type="text"
              value={form.llmvendornm}
              onChange={(e) => setForm((f) => ({ ...f, llmvendornm: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.llmmodelnm')}:</label>
            <input
              type="text"
              value={form.llmmodelnm}
              onChange={(e) => setForm((f) => ({ ...f, llmmodelnm: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label>{t('lbl.llmmodelnicknm')}:</label>
            <input
              type="text"
              value={form.llmmodelnicknm}
              autoComplete="off"
              onChange={(e) => setForm((f) => ({ ...f, llmmodelnicknm: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label>{t('lbl.useyn_lbl')}:</label>
            <input
              type="checkbox"
              checked={form.useyn}
              onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
            />
          </div>
          <div className="form-group">
            <label>{t('lbl.isdefault')}:</label>
            <input
              type="checkbox"
              checked={form.isdefault}
              onChange={(e) => setForm((f) => ({ ...f, isdefault: e.target.checked }))}
            />
          </div>
          <div className="form-group">
            <label>{t('lbl.apikey')}:</label>
            <input
              type="password"
              value={form.apikey}
              placeholder={t('msg.placeholder.password.change')}
              autoComplete="new-password"
              onChange={(e) => setForm((f) => ({ ...f, apikey: e.target.value }))}
            />
            <small style={{ color: '#888' }}>{t('inf.password.hidden')}</small>
          </div>
        </div>
      </div>
    </div>
  )
}
