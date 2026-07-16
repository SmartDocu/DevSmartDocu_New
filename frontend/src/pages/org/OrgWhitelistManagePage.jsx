import { useEffect, useState } from 'react'
import { App } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useAuthStore } from '@/stores/authStore'
import {
  useWhitelists, useSaveWhitelist, useDeleteWhitelist,
  useWhitelistConfig, useSaveWhitelistConfig,
} from '@/hooks/useWhitelists'

const IPTYPES = ['IP', 'CIDR', 'RANGE']

const EMPTY_FORM = { whitelistuid: '', iptype: 'IP', ipvalue: '', desc: '', useyn: true }

function ipvalueHint(iptype) {
  if (iptype === 'IP') return t('inf.ipvalue_ip')
  if (iptype === 'CIDR') return t('inf.ipvalue_cidr')
  if (iptype === 'RANGE') return t('inf.ipvalue_range')
  return ''
}

export default function OrgWhitelistManagePage() {
  const { modal } = App.useApp()
  useLangStore((s) => s.translations)
  const user = useAuthStore((s) => s.user)
  const isEditYn = user?.tenantmanager === 'Y'

  const { data: whitelists = [], isLoading } = useWhitelists()
  const saveWhitelist = useSaveWhitelist()
  const deleteWhitelist = useDeleteWhitelist()

  const { data: config, isLoading: configLoading } = useWhitelistConfig()
  const saveConfig = useSaveWhitelistConfig()
  const [configForm, setConfigForm] = useState({ is_manager_ip_allow: false, is_user_ip_allow: false })

  useEffect(() => {
    if (config) {
      setConfigForm({
        is_manager_ip_allow: !!config.is_manager_ip_allow,
        is_user_ip_allow: !!config.is_user_ip_allow,
      })
    }
  }, [config])

  const handleSaveConfig = () => {
    if ((configForm.is_manager_ip_allow || configForm.is_user_ip_allow) && whitelists.length === 0) {
      alert(t('msg.whitelist.config.empty.warning'))
      return
    }
    saveConfig.mutate(configForm)
  }

  const [selected, setSelected] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)

  const selectRow = (row) => {
    setSelected(row)
    setForm({
      whitelistuid: row.whitelistuid,
      iptype: row.iptype,
      ipvalue: row.ipvalue || '',
      desc: row.desc || '',
      useyn: row.useyn ?? true,
    })
  }

  const handleNew = () => {
    setSelected(null)
    setForm(EMPTY_FORM)
  }

  const handleSave = () => {
    if (!form.iptype || !form.ipvalue.trim()) { alert(t('msg.whitelist.required')); return }
    const payload = {
      whitelistuid: form.whitelistuid || null,
      iptype: form.iptype,
      ipvalue: form.ipvalue.trim(),
      desc: form.desc || null,
      useyn: form.useyn,
    }
    saveWhitelist.mutate(payload, { onSuccess: handleNew })
  }

  const handleDelete = () => {
    if (!form.whitelistuid) { alert(t('msg.whitelist.select.delete')); return }
    modal.confirm({
      content: t('msg.confirm.delete'),
      okType: 'danger',
      onOk: () => deleteWhitelist.mutate(form.whitelistuid, { onSuccess: handleNew }),
    })
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('mnu.tenant_mgr.whitelist')}</div>
        </div>
      </div>

      {/* IP 제한 적용 설정 */}
      <div style={{ marginBottom: 24, paddingRight: 10 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
          <h3 style={{ margin: 0 }}>{t('ttl.whitelist.config')}</h3>
          {isEditYn && (
            <button className="btn btn-primary" type="button" onClick={handleSaveConfig} disabled={saveConfig.isPending || configLoading}>
              {t('btn.save')}
            </button>
          )}
        </div>
        <div style={{ border: '1px solid #f0f0f0', borderRadius: 4, padding: '12px 16px' }}>
          <div style={{ display: 'flex', gap: 32, marginBottom: 8 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: isEditYn ? 'pointer' : 'default' }}>
              <input
                type="checkbox"
                checked={configForm.is_manager_ip_allow}
                disabled={!isEditYn || configLoading}
                onChange={(e) => setConfigForm((f) => ({ ...f, is_manager_ip_allow: e.target.checked }))}
              />
              {t('lbl.whitelist.manager_ip_allow')}
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: isEditYn ? 'pointer' : 'default' }}>
              <input
                type="checkbox"
                checked={configForm.is_user_ip_allow}
                disabled={!isEditYn || configLoading}
                onChange={(e) => setConfigForm((f) => ({ ...f, is_user_ip_allow: e.target.checked }))}
              />
              {t('lbl.whitelist.user_ip_allow')}
            </label>
          </div>
          <div style={{ fontSize: 12, color: '#d46b08' }}>
            {t('inf.whitelist.config.warning')}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측: 목록 */}
        <div style={{ flex: 4, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            {isEditYn && (
              <button className="btn btn-primary" type="button" onClick={handleNew}>
                {t('btn.new')}
              </button>
            )}
          </div>
          <div className="table-container">
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th style={{ width: '20%' }}>{t('thd.iptype_thd')}</th>
                  <th style={{ width: '35%' }}>{t('thd.ipvalue_thd')}</th>
                  <th style={{ width: '30%' }}>{t('thd.desc_whitelist')}</th>
                  <th style={{ width: '15%', textAlign: 'center' }}>{t('thd.useyn_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : whitelists.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : whitelists.map((row) => (
                  <tr
                    key={row.whitelistuid}
                    className={selected?.whitelistuid === row.whitelistuid ? 'selected-row' : ''}
                    style={{ cursor: 'pointer' }}
                    onClick={() => selectRow(row)}
                  >
                    <td>{row.iptype}</td>
                    <td>{row.ipvalue}</td>
                    <td>{row.desc || ''}</td>
                    <td style={{ textAlign: 'center' }}>{row.useyn ? '✔' : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측: 상세 */}
        <div style={{ flex: 6, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            {isEditYn && (
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveWhitelist.isPending}>
                  {t('btn.save')}
                </button>
                {form.whitelistuid && (
                  <button className="btn btn-danger" type="button" onClick={handleDelete} disabled={deleteWhitelist.isPending}>
                    {t('btn.delete')}
                  </button>
                )}
              </div>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="wl-iptype"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.iptype')}:</label>
            <select
              id="wl-iptype"
              value={form.iptype}
              disabled={!isEditYn}
              onChange={(e) => setForm((f) => ({ ...f, iptype: e.target.value }))}
            >
              {IPTYPES.map((v) => (
                <option key={v} value={v}>{t(`cod.iptype_${v.toLowerCase()}`) || v}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="wl-ipvalue">
              <span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.ipvalue')}:
              <span style={{ fontSize: 12, color: '#888', fontWeight: 'normal', marginLeft: 6 }}>
                {ipvalueHint(form.iptype)}
              </span>
            </label>
            <input
              id="wl-ipvalue"
              type="text"
              value={form.ipvalue}
              disabled={!isEditYn}
              onChange={(e) => setForm((f) => ({ ...f, ipvalue: e.target.value }))}
            />
          </div>

          <div className="form-group">
            <label htmlFor="wl-desc">{t('lbl.desc_lbl')}:</label>
            <textarea
              id="wl-desc"
              rows={3}
              style={{ resize: 'vertical' }}
              value={form.desc}
              disabled={!isEditYn}
              onChange={(e) => setForm((f) => ({ ...f, desc: e.target.value }))}
            />
          </div>

          <div className="form-group">
            <label htmlFor="wl-useyn"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.useyn_lbl')}:</label>
            <input
              id="wl-useyn"
              type="checkbox"
              checked={!!form.useyn}
              disabled={!isEditYn}
              onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
