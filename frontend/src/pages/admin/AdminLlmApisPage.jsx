import { useState } from 'react'
import { App } from 'antd'
import { useAdminLlmApis, useSaveLlmApi, useDeleteLlmApi } from '@/hooks/useAdmin'
import { useLangStore, t } from '@/stores/langStore'

export default function AdminLlmApisPage() {
  const { message, modal } = App.useApp()
  const { data = {}, isLoading } = useAdminLlmApis()
  const saveMutation = useSaveLlmApi()
  const deleteMutation = useDeleteLlmApi()
  useLangStore((s) => s.translations)

  const { llmapis = [], llmmodels = [], tenants = [] } = data

  const EMPTY = { llmapiuid: '', llmmodelnm: '', apikey: '', usetypecd: '', desc: '' }
  const [form, setForm] = useState(EMPTY)
  const [selectedRow, setSelectedRow] = useState(null)

  const handleRowClick = (row) => {
    setSelectedRow(row)
    setForm({
      llmapiuid: row.llmapiuid || '',
      llmmodelnm: row.llmmodelnm || '',
      apikey: '',
      usetypecd: row.usetypecd || '',
      desc: row.usetypecd === 'D' ? (row.desc || '') : '',
    })
  }

  const handleNew = () => {
    setSelectedRow(null)
    setForm(EMPTY)
  }

  const handleUsetypeChange = (val) => {
    setForm((f) => ({ ...f, usetypecd: val, desc: val !== 'D' ? '' : f.desc }))
  }

  const handleSave = () => {
    if (!form.llmmodelnm) { message.warning(t('msg.llmmodel.required')); return }
    if (!form.usetypecd) { message.warning(t('msg.usetypecd.required')); return }
    saveMutation.mutate(
      {
        llmapiuid: form.llmapiuid || null,
        llmmodelnm: form.llmmodelnm,
        apikey: form.apikey || '',
        usetypecd: form.usetypecd,
        desc: form.usetypecd === 'D' ? (form.desc || null) : null,
      },
      { onSuccess: handleNew },
    )
  }

  const handleDelete = () => {
    if (!selectedRow) { message.warning(t('msg.select.delete')); return }
    modal.confirm({
      title: t('msg.confirm.delete'),
      content: t('msg.confirm.delete'),
      okText: t('btn.delete'), cancelText: t('btn.cancel'), okButtonProps: { danger: true },
      onOk: () => deleteMutation.mutate(selectedRow.llmapiuid, { onSuccess: handleNew }),
    })
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('mnu.company.llm_api')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측: LLM API 목록 */}
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
              <table id="llmapis-table">
                <thead>
                  <tr>
                    <th style={{ width: '40%' }}>{t('thd.llmmodelnm_thd')}</th>
                    <th style={{ width: '20%' }}>{t('thd.usetypecd_thd')}</th>
                    <th style={{ width: '30%' }}>{t('thd.desc_thd')}</th>
                  </tr>
                </thead>
                <tbody>
                  {llmapis.map((api) => (
                    <tr
                      key={api.llmapiuid}
                      className={selectedRow?.llmapiuid === api.llmapiuid ? 'selected-row' : ''}
                      style={{ cursor: 'pointer' }}
                      onClick={() => handleRowClick(api)}
                    >
                      <td>{api.llmmodelnm}</td>
                      <td>{api.usetypenm}</td>
                      <td>{api.desc || ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* 우측: LLM API 상세 */}
        <div style={{ flex: 5, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
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
          <input type="hidden" value={form.llmapiuid} />

          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.llmmodelnm')}:</label>
            <select
              value={form.llmmodelnm}
              onChange={(e) => setForm((f) => ({ ...f, llmmodelnm: e.target.value }))}
              required
            >
              <option value="">{t('msg.select.placeholder')}</option>
              {llmmodels.map((m) => (
                <option key={m.llmmodelnm} value={m.llmmodelnm}>
                  {m.llmvendornm} → {m.llmmodelnm}
                </option>
              ))}
            </select>
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

          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('thd.usetypecd_thd')}:</label>
            <select
              value={form.usetypecd}
              onChange={(e) => handleUsetypeChange(e.target.value)}
              required
            >
              <option value="">{t('msg.select.placeholder')}</option>
              <option value="R">Round</option>
              <option value="D">Direct</option>
              <option value="N">No</option>
            </select>
          </div>

          <div className="form-group">
            <label>{t('lbl.note')}:</label>
            <select
              value={form.desc}
              disabled={form.usetypecd !== 'D'}
              onChange={(e) => setForm((f) => ({ ...f, desc: e.target.value }))}
            >
              <option value="">{t('msg.select.placeholder')}</option>
              {tenants.map((ten) => (
                <option key={ten.tenantnm} value={ten.tenantnm}>{ten.tenantnm}</option>
              ))}
            </select>
          </div>
        </div>
      </div>
    </div>
  )
}
