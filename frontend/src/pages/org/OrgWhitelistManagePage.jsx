import { useEffect, useState } from 'react'
import { App } from 'antd'
import { PlusOutlined, SaveOutlined, DeleteOutlined, CheckCircleFilled } from '@ant-design/icons'
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
  const { message, modal } = App.useApp()
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
      message.warning(t('msg.whitelist.config.empty.warning'))
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
    if (!form.iptype || !form.ipvalue.trim()) { message.warning(t('msg.whitelist.required')); return }
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
    if (!form.whitelistuid) { message.warning(t('msg.whitelist.select.delete')); return }
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
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('ttl.tenant_mgr.whitelist')}</div>
        </div>
      </div>

      {/* IP 제한 적용 설정 */}
      <div className="panel-section" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 12 }}>
          <h3 style={{ margin: 0 }}>{t('ttl.whitelist.config')}</h3>
          {isEditYn && (
            <button className="btn btn-primary" type="button" onClick={handleSaveConfig} disabled={saveConfig.isPending || configLoading}>
              <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
            </button>
          )}
        </div>
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

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
        {/* 좌측: 목록 */}
        <div className="panel-section" style={{ flex: 1.5, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 373px)' }}>
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
                {t('lbl.count.docs').replace('{n}', whitelists.length)}
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
                    <td style={{ textAlign: 'center' }}>{row.useyn && <CheckCircleFilled style={{ color: '#2f7d4f' }} title={t('thd.useyn_thd')} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </div>
        </div>

        {/* 우측: 상세 */}
        <div className="panel-section" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 373px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            {isEditYn && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveWhitelist.isPending || deleteWhitelist.isPending}>
                  <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
                </button>
                {form.whitelistuid && (
                  <button
                    className="btn btn-danger"
                    type="button"
                    onClick={handleDelete}
                    disabled={deleteWhitelist.isPending}
                    title={t('btn.delete')}
                    style={{ width: 38, height: 38, padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                  >
                    <DeleteOutlined />
                  </button>
                )}
              </div>
            )}
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>

          <div className="form-group">
            <label htmlFor="wl-iptype"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.iptype')}:</label>
            <select
              id="wl-iptype"
              value={form.iptype}
              disabled={!isEditYn}
              style={{ height: 38 }}
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
              style={{ height: 38 }}
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
            <div style={{ paddingLeft: 60 }}>
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
      </div>
    </div>
  )
}
