import { useState } from 'react'
import { App } from 'antd'
import { SaveOutlined, CheckCircleFilled } from '@ant-design/icons'
import { useLangStore, t } from '@/stores/langStore'
import { useSettingsTenants, useSaveTenant } from '@/hooks/useSettings'
import { getErrorMessage } from '@/utils/apiError'

const EMPTY_FORM = {
  tenantid: '', tenantnm: '', useyn: true,
  email: '', telno: '',
  languagecd: '', timezone: '', issystemtenant: false,
}

export default function SettingsTenantsPage() {
  const { message } = App.useApp()
  useLangStore((s) => s.translations)
  const { data = {}, isLoading } = useSettingsTenants()
  const saveTenant = useSaveTenant()

  const [form, setForm] = useState(EMPTY_FORM)
  const [selectedId, setSelectedId] = useState(null)

  const [creatornm, setCreatornm] = useState('')
  const [createdts, setCreatedts] = useState('')

  const tenants = data.tenants || []
  const languages = data.languages || []
  const timezones = data.timezones || []

  const handleRowSelect = (row) => {
    setSelectedId(row.tenantid)
    setForm({
      tenantid: row.tenantid,
      tenantnm: row.tenantnm || '',
      useyn: !!row.useyn,
      email: row.decemail || '',
      telno: row.dectelno || '',
      languagecd: row.languagecd || '',
      timezone: row.timezone || '',
      issystemtenant: !!row.issystemtenant,
    })
    setCreatornm(row.creatornm || '')
    setCreatedts(row.createdts || '')
  }

  const handleSave = () => {
    if (!selectedId) { message.warning(t('msg.select.update')); return }
    if (!form.tenantnm.trim()) { message.warning(t('msg.tenantnm.required')); return }
    const fd = new FormData()
    fd.append('tenantid', form.tenantid)
    fd.append('tenantnm', form.tenantnm)
    fd.append('useyn', form.useyn ? 'true' : 'false')
    if (form.email) fd.append('email', form.email)
    if (form.telno) fd.append('telno', form.telno)
    if (form.languagecd) fd.append('languagecd', form.languagecd)
    if (form.timezone) fd.append('timezone', form.timezone)
    fd.append('issystemtenant', form.issystemtenant ? 'true' : 'false')
    saveTenant.mutate(fd, {
      onSuccess: () => { message.success(t('msg.save.success')) },
      onError: (err) => { message.error(getErrorMessage(err, 'msg.save.error')) },
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
          <div>{t('mnu.company.tenants')}</div>
        </div>
      </div>

      <div className="panel-section" style={{ background: '#f9fbe7', color: '#6a7d3c', fontSize: 13, marginBottom: 16, padding: '13px 18px' }}>
        ＊ 이 화면은 기존 기업의 사용여부·연락처·명칭 등 정보 수정만 가능합니다. (신규 생성·삭제 불가)
      </div>

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
        {/* 좌측 패널: 기업 목록 */}
        <div className="panel-section" style={{ flex: 1.5, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 287px)' }}>
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
                {t('lbl.count.docs').replace('{n}', tenants.length)}
              </span>
            </div>
            <div />
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
            {isLoading ? (
              <div style={{ textAlign: 'center', padding: 32 }}><div className="spinner" /></div>
            ) : (
              <table className="table table-bordered table-sm">
                <thead>
                  <tr>
                    <th style={{ width: '85%' }}>{t('thd.tenantnm_thd')}</th>
                    <th style={{ width: '15%' }}>{t('thd.useyn_thd')}</th>
                  </tr>
                </thead>
                <tbody>
                  {tenants.map((row) => (
                    <tr
                      key={row.tenantid}
                      className={row.tenantid === selectedId ? 'selected-row' : ''}
                      style={{ cursor: 'pointer' }}
                      onClick={() => handleRowSelect(row)}
                    >
                      <td>{row.tenantnm}</td>
                      <td style={{ textAlign: 'center' }}>{row.useyn && <CheckCircleFilled style={{ color: '#2f7d4f' }} title={t('thd.useyn_thd')} />}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          </div>
        </div>

        {/* 우측 패널: 기업 상세 */}
        <div className="panel-section" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 287px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveTenant.isPending || !selectedId}>
                <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
              </button>
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>

          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.tenantnm')}:</label>
            <input type="text" value={form.tenantnm} style={{ height: 38 }}
              onChange={(e) => setForm((f) => ({ ...f, tenantnm: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.useyn_lbl')}:</label>
            <div style={{ paddingLeft: 60 }}>
              <input type="checkbox" checked={form.useyn}
                onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))} />
            </div>
          </div>

          <div className="form-group">
            <label>{t('lbl.email')}:</label>
            <input type="email" value={form.email} style={{ height: 38 }}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.telno')}:</label>
            <input type="text" value={form.telno} style={{ height: 38 }}
              onChange={(e) => setForm((f) => ({ ...f, telno: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('thd.languagenm')}:</label>
            <select value={form.languagecd} style={{ height: 38 }}
              onChange={(e) => setForm((f) => ({ ...f, languagecd: e.target.value }))}>
              <option value="">{t('msg.select')}</option>
              {languages.map((lang) => (
                <option key={lang.languagecd} value={lang.languagecd}>{lang.languagenm}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>{t('lbl.timezone')}:</label>
            <select value={form.timezone} style={{ height: 38 }}
              onChange={(e) => setForm((f) => ({ ...f, timezone: e.target.value }))}>
              <option value="">{t('msg.select')}</option>
              {timezones.map((tz) => (
                <option key={tz} value={tz}>{tz}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>{t('lbl.issystemtenant')}:</label>
            <div style={{ paddingLeft: 60 }}>
              <input type="checkbox" checked={form.issystemtenant}
                onChange={(e) => setForm((f) => ({ ...f, issystemtenant: e.target.checked }))} />
            </div>
          </div>

          </div>
        </div>
      </div>
    </div>
  )
}
