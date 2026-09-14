import { useMemo, useState } from 'react'
import { App } from 'antd'
import { PlusOutlined, SaveOutlined, DeleteOutlined, CheckCircleFilled } from '@ant-design/icons'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useLlmKeysInit, useLlmKeys, useSaveLlmKey, useDeleteLlmKey } from '@/hooks/useLlmKeys'

const EMPTY_FORM = {
  llmkeyuid: '',
  servicecd: '',
  llmvendornm: '',
  apikey: '',
  llmmodelnm: '',
  llmmodelnm_smart: '',
  llmmodelnm_expert: '',
  useyn: true,
  orderno: 0,
}

const roStyle = { backgroundColor: '#f0f0f0', color: '#555', border: '1px solid #ccc', height: 38 }
const editStyle = { height: 38 }

export default function SettingsLlmKeysPage() {
  const { message, modal } = App.useApp()
  useLangStore((s) => s.translations)
  const { user } = useAuthStore()
  const isEditYn = user?.editbuttonyn === 'Y'

  const [form, setForm] = useState(EMPTY_FORM)
  const [selectedId, setSelectedId] = useState(null)

  const { data: initData = {} } = useLlmKeysInit()
  const { data: listData = {}, isLoading } = useLlmKeys()
  const saveMutation = useSaveLlmKey()
  const deleteMutation = useDeleteLlmKey()

  const { vendors = [], llmmodels = [], servicecodes = [] } = initData
  const { llmkeys = [] } = listData

  // 선택된 vendor에 해당하는 모델 목록
  const filteredModels = useMemo(
    () => llmmodels.filter((m) => m.llmvendornm === form.llmvendornm),
    [llmmodels, form.llmvendornm],
  )

  const isInsight = form.servicecd === 'In'

  const handleRowClick = (row) => {
    setSelectedId(row.llmkeyuid)
    setForm({
      llmkeyuid: row.llmkeyuid || '',
      servicecd: row.servicecd || '',
      llmvendornm: row.llmvendornm || '',
      apikey: '',  // 보안상 빈 값으로 (기존 키 유지)
      llmmodelnm: row.llmmodelnm || '',
      llmmodelnm_smart: row.llmmodelnm_smart || '',
      llmmodelnm_expert: row.llmmodelnm_expert || '',
      useyn: row.useyn ?? true,
      orderno: row.orderno ?? 0,
    })
  }

  const handleNew = () => {
    setSelectedId(null)
    setForm(EMPTY_FORM)
  }

  const handleVendorChange = (vendor) => {
    setForm((f) => ({ ...f, llmvendornm: vendor, llmmodelnm: '', llmmodelnm_smart: '', llmmodelnm_expert: '' }))
  }

  const handleServiceChange = (scd) => {
    setForm((f) => ({
      ...f,
      servicecd: scd,
      llmmodelnm_smart: scd !== 'insight' ? '' : f.llmmodelnm_smart,
      llmmodelnm_expert: scd !== 'insight' ? '' : f.llmmodelnm_expert,
    }))
  }

  const handleSave = () => {
    if (!form.servicecd) { message.warning(t('msg.servicecd.required')); return }
    if (!form.llmvendornm) { message.warning(t('msg.llmvendornm.required')); return }

    saveMutation.mutate(
      {
        llmkeyuid: form.llmkeyuid || null,
        servicecd: form.servicecd,
        llmvendornm: form.llmvendornm,
        apikey: form.apikey || '',
        llmmodelnm: form.llmmodelnm || null,
        llmmodelnm_smart: isInsight ? (form.llmmodelnm_smart || null) : null,
        llmmodelnm_expert: isInsight ? (form.llmmodelnm_expert || null) : null,
        useyn: form.useyn,
        orderno: Number(form.orderno) || 0,
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
    if (!selectedId) return
    modal.confirm({
      title: t('msg.confirm.delete'),
      okText: t('btn.delete'),
      cancelText: t('btn.cancel'),
      okButtonProps: { danger: true },
      onOk: () => deleteMutation.mutate(selectedId, {
        onSuccess: () => { message.success(t('msg.delete.success')); handleNew() },
        onError: (err) => {
          const detail = err.response?.data?.detail
          message.error((typeof detail === 'string' && t(detail)) || t('msg.delete.error'))
        },
      }),
    })
  }

  const serviceLabel = (scd) => {
    const found = servicecodes.find((c) => c.codevalue === scd)
    return found ? (t(found.term_key) || found.default_name) : scd
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('mnu.tenant_mgr.org.llm')}</div>
        </div>
      </div>

      <div className="panel-section" style={{ background: '#f9fbe7', color: '#6a7d3c', fontSize: 13, marginBottom: 16, padding: '13px 18px' }}>
        ＊ {t('msg.llmkey.notice')}
      </div>

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
        {/* 좌측: 목록 */}
        <div className="panel-section" style={{ flex: 1.5, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 288px)' }}>
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
                {t('lbl.count.docs').replace('{n}', llmkeys.length)}
              </span>
            </div>
            {isEditYn && (
              <button className="btn btn-primary" type="button" onClick={handleNew}>
                <PlusOutlined style={{ marginRight: 6 }} />{t('btn.new')}
              </button>
            )}
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
            <table className="table table-bordered table-sm" style={{ cursor: 'pointer' }}>
              <thead>
                <tr>
                  <th style={{ width: '25%' }}>{t('thd.servicecd_thd')}</th>
                  <th style={{ width: '30%' }}>{t('thd.llmvendornm_thd')}</th>
                  <th style={{ width: '25%' }}>{t('thd.llmmodelnm_thd')}</th>
                  <th style={{ width: '10%' }}>{t('thd.orderno_thd')}</th>
                  <th style={{ width: '10%' }}>{t('thd.useyn_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={5} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : llmkeys.length === 0 ? (
                  <tr><td colSpan={5} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : llmkeys.map((row) => (
                  <tr
                    key={row.llmkeyuid}
                    className={selectedId === row.llmkeyuid ? 'selected-row' : ''}
                    onClick={() => handleRowClick(row)}
                  >
                    <td>{serviceLabel(row.servicecd)}</td>
                    <td>{row.llmvendornm}</td>
                    <td>{row.llmmodelnm}</td>
                    <td style={{ textAlign: 'center' }}>{row.orderno}</td>
                    <td style={{ textAlign: 'center' }}>{row.useyn && <CheckCircleFilled style={{ color: '#2f7d4f' }} title={t('thd.useyn_thd')} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </div>
        </div>

        {/* 우측: 상세 폼 */}
        <div className="panel-section" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 288px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            {isEditYn && (
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
            )}
            {!isEditYn && <div />}
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>

          {/* 서비스 */}
          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.servicecd')}:</label>
            <select
              value={form.servicecd}
              onChange={(e) => handleServiceChange(e.target.value)}
              disabled={!isEditYn}
              style={!isEditYn ? roStyle : editStyle}
            >
              <option value="">{t('lbl.select')}</option>
              {servicecodes.map((c) => (
                <option key={c.codevalue} value={c.codevalue}>
                  {t(c.term_key) || c.default_name}
                </option>
              ))}
            </select>
          </div>

          {/* LLM 벤더 */}
          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.llmvendornm')}:</label>
            <select
              value={form.llmvendornm}
              onChange={(e) => handleVendorChange(e.target.value)}
              disabled={!isEditYn}
              style={!isEditYn ? roStyle : editStyle}
            >
              <option value="">{t('lbl.select')}</option>
              {vendors.map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </div>

          {/* API Key */}
          <div className="form-group">
            <label>
              {t('lbl.apikey')}:
              {selectedId && (
                <span style={{ marginLeft: 8, fontSize: 12, color: '#888' }}>
                  {t('inf.apikey.empty.keep')}
                </span>
              )}
            </label>
            <input
              type="password"
              value={form.apikey}
              onChange={(e) => setForm((f) => ({ ...f, apikey: e.target.value }))}
              disabled={!isEditYn}
              style={!isEditYn ? roStyle : editStyle}
              autoComplete="new-password"
            />
          </div>

          {/* LLM 모델명 (기본) */}
          <div className="form-group">
            <label>{t('lbl.llmmodelnm')}:</label>
            <select
              value={form.llmmodelnm}
              onChange={(e) => setForm((f) => ({ ...f, llmmodelnm: e.target.value }))}
              disabled={!isEditYn || !form.llmvendornm}
              style={(!isEditYn || !form.llmvendornm) ? roStyle : editStyle}
            >
              <option value="">{t('lbl.select')}</option>
              {filteredModels.map((m) => (
                <option key={m.llmmodelnm} value={m.llmmodelnm}>{m.llmmodelnm}</option>
              ))}
            </select>
          </div>

          {/* insight 전용 필드 */}
          {isInsight && (
            <>
              <div className="form-group">
                <label>{t('lbl.llmmodelnm_smart')}:</label>
                <select
                  value={form.llmmodelnm_smart}
                  onChange={(e) => setForm((f) => ({ ...f, llmmodelnm_smart: e.target.value }))}
                  disabled={!isEditYn || !form.llmvendornm}
                  style={(!isEditYn || !form.llmvendornm) ? roStyle : editStyle}
                >
                  <option value="">{t('lbl.select')}</option>
                  {filteredModels.map((m) => (
                    <option key={m.llmmodelnm} value={m.llmmodelnm}>{m.llmmodelnm}</option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label>{t('lbl.llmmodelnm_expert')}:</label>
                <select
                  value={form.llmmodelnm_expert}
                  onChange={(e) => setForm((f) => ({ ...f, llmmodelnm_expert: e.target.value }))}
                  disabled={!isEditYn || !form.llmvendornm}
                  style={(!isEditYn || !form.llmvendornm) ? roStyle : editStyle}
                >
                  <option value="">{t('lbl.select')}</option>
                  {filteredModels.map((m) => (
                    <option key={m.llmmodelnm} value={m.llmmodelnm}>{m.llmmodelnm}</option>
                  ))}
                </select>
              </div>
            </>
          )}

          {/* 순번 */}
          <div className="form-group">
            <label>{t('lbl.orderno')}:</label>
            <input
              type="number"
              value={form.orderno}
              onChange={(e) => setForm((f) => ({ ...f, orderno: e.target.value }))}
              disabled={!isEditYn}
              style={!isEditYn ? roStyle : editStyle}
            />
          </div>

          {/* 사용 여부 */}
          <div className="form-group">
            <label>{t('lbl.useyn_lbl')}:</label>
            <div style={{ paddingLeft: 60 }}>
              <input
                type="checkbox"
                checked={form.useyn}
                onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
                disabled={!isEditYn}
              />
            </div>
          </div>
          </div>
        </div>
      </div>
    </div>
  )
}
