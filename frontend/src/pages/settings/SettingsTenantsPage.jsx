import { useRef, useState } from 'react'
import { App } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useSettingsTenants, useSaveTenant, useDeleteTenant } from '@/hooks/useSettings'

const BILLING_OPTIONS = [
  { value: 'Fr' },
  { value: 'Pr' },
  { value: 'Te' },
  { value: 'En' },
]

const IANA_TIMEZONES = [
  'Africa/Cairo', 'Africa/Johannesburg', 'Africa/Lagos', 'Africa/Nairobi',
  'America/Anchorage', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
  'America/Mexico_City', 'America/New_York', 'America/Phoenix', 'America/Sao_Paulo',
  'America/Toronto', 'America/Vancouver',
  'Asia/Bangkok', 'Asia/Dhaka', 'Asia/Dubai', 'Asia/Hong_Kong',
  'Asia/Jakarta', 'Asia/Karachi', 'Asia/Kolkata', 'Asia/Kuala_Lumpur',
  'Asia/Manila', 'Asia/Riyadh', 'Asia/Seoul', 'Asia/Shanghai',
  'Asia/Singapore', 'Asia/Taipei', 'Asia/Tehran', 'Asia/Tokyo', 'Asia/Yangon',
  'Atlantic/Azores',
  'Australia/Adelaide', 'Australia/Brisbane', 'Australia/Melbourne',
  'Australia/Perth', 'Australia/Sydney',
  'Europe/Amsterdam', 'Europe/Athens', 'Europe/Berlin', 'Europe/Brussels',
  'Europe/Budapest', 'Europe/Copenhagen', 'Europe/Dublin', 'Europe/Helsinki',
  'Europe/Istanbul', 'Europe/Kiev', 'Europe/Lisbon', 'Europe/London',
  'Europe/Madrid', 'Europe/Moscow', 'Europe/Oslo', 'Europe/Paris',
  'Europe/Prague', 'Europe/Rome', 'Europe/Stockholm', 'Europe/Vienna',
  'Europe/Warsaw', 'Europe/Zurich',
  'Pacific/Auckland', 'Pacific/Fiji', 'Pacific/Guam', 'Pacific/Honolulu',
  'UTC',
]

const EMPTY_FORM = {
  tenantid: '', tenantnm: '', useyn: true, billingmodelcd: 'Fr',
  billingusercnt: '', llmlimityn: false, email: '', telno: '',
  languagecd: '', timezone: '', issystemtenant: false,
}

export default function SettingsTenantsPage() {
  const { message, modal } = App.useApp()
  useLangStore((s) => s.translations)
  const { data = {}, isLoading } = useSettingsTenants()
  const saveTenant = useSaveTenant()
  const deleteTenant = useDeleteTenant()

  const [form, setForm] = useState(EMPTY_FORM)
  const [selectedId, setSelectedId] = useState(null)

  const iconFileRef = useRef(null)
  const [iconFile, setIconFile] = useState(null)
  const [iconFileNm, setIconFileNm] = useState('')
  const [iconFileUrl, setIconFileUrl] = useState('')

  const [creatornm, setCreatornm] = useState('')
  const [createdts, setCreatedts] = useState('')

  const tenants = data.tenants || []
  const languages = data.languages || []

  const handleRowSelect = (row) => {
    setSelectedId(row.tenantid)
    setForm({
      tenantid: row.tenantid,
      tenantnm: row.tenantnm || '',
      useyn: !!row.useyn,
      billingmodelcd: row.billingmodelcd || 'Fr',
      billingusercnt: row.billingusercnt ?? '',
      llmlimityn: !!row.llmlimityn,
      email: row.decemail || '',
      telno: row.dectelno || '',
      languagecd: row.languagecd || '',
      timezone: row.timezone || '',
      issystemtenant: !!row.issystemtenant,
    })
    setIconFile(null)
    setIconFileNm(row.iconfilenm || '')
    setIconFileUrl(row.iconfileurl || '')
    setCreatornm(row.creatornm || '')
    setCreatedts(row.createdts || '')
  }

  const handleNew = () => {
    setSelectedId(null)
    setForm(EMPTY_FORM)
    setIconFile(null)
    setIconFileNm('')
    setIconFileUrl('')
    setCreatornm('')
    setCreatedts('')
  }

  const handleSave = () => {
    if (!form.tenantnm.trim()) { message.warning(t('msg.tenantnm.required')); return }
    const fd = new FormData()
    if (form.tenantid) fd.append('tenantid', form.tenantid)
    fd.append('tenantnm', form.tenantnm)
    fd.append('useyn', form.useyn ? 'true' : 'false')
    fd.append('billingmodelcd', form.billingmodelcd || 'Fr')
    if (form.billingusercnt !== '') fd.append('billingusercnt', String(form.billingusercnt))
    fd.append('llmlimityn', form.llmlimityn ? 'true' : 'false')
    if (form.email) fd.append('email', form.email)
    if (form.telno) fd.append('telno', form.telno)
    if (form.languagecd) fd.append('languagecd', form.languagecd)
    if (form.timezone) fd.append('timezone', form.timezone)
    fd.append('issystemtenant', form.issystemtenant ? 'true' : 'false')
    if (iconFile) fd.append('iconfile', iconFile)
    saveTenant.mutate(fd, {
      onSuccess: () => { message.success(t('msg.save.success')); handleNew() },
      onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
    })
  }

  const handleDelete = () => {
    if (!selectedId) { message.warning(t('msg.select.delete')); return }
    modal.confirm({
      title: t('btn.delete'),
      content: t('msg.confirm.delete'),
      okText: t('btn.delete'), cancelText: t('btn.cancel'), okButtonProps: { danger: true },
      onOk: () => deleteTenant.mutate(selectedId, {
        onSuccess: () => { message.success(t('msg.delete.success')); handleNew() },
        onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
      }),
    })
  }

  const handleIconUploadClick = () => iconFileRef.current?.click()

  const handleIconFileChange = (e) => {
    const file = e.target.files?.[0]
    if (file) {
      setIconFile(file)
      setIconFileNm(file.name)
      setIconFileUrl('')
    }
    e.target.value = ''
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('mnu.company.tenants')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측 패널: 기업 목록 */}
        <div style={{ flex: 3, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleNew}>{t('btn.new')}</button>
          </div>
          <div className="table-container">
            {isLoading ? (
              <div style={{ textAlign: 'center', padding: 32 }}><div className="spinner" /></div>
            ) : (
              <table className="table table-bordered table-sm">
                <thead>
                  <tr>
                    <th style={{ width: '50%' }}>{t('thd.tenantnm_thd')}</th>
                    <th style={{ width: '35%' }}>{t('thd.billingmodelcd')}</th>
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
                      <td>{t(`cod.billing_${row.billingmodelcd}`)}</td>
                      <td style={{ textAlign: 'center' }}>{row.useyn ? '✔' : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* 우측 패널: 기업 상세 */}
        <div style={{ flex: 7, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveTenant.isPending}>
                {t('btn.save')}
              </button>
              {selectedId && (
                <button className="btn btn-danger" type="button" onClick={handleDelete} disabled={deleteTenant.isPending}>
                  {t('btn.delete')}
                </button>
              )}
            </div>
          </div>

          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.tenantnm')}:</label>
            <input type="text" value={form.tenantnm}
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
            <label>{t('lbl.plan')}:</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 24, paddingLeft: 60 }}>
              {BILLING_OPTIONS.map((o) => (
                <span key={o.value} style={{ display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }}>
                  <input type="radio" name="billingmodelcd" value={o.value}
                    checked={form.billingmodelcd === o.value}
                    onChange={() => setForm((f) => ({ ...f, billingmodelcd: o.value }))} />
                  <span>{t(`cod.billing_${o.value}`)}</span>
                </span>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label>{t('lbl.billingusercnt')}:</label>
            <input type="number" value={form.billingusercnt} style={{ width: 120 }}
              onChange={(e) => setForm((f) => ({ ...f, billingusercnt: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.llmlimityn')}:</label>
            <div style={{ paddingLeft: 60 }}>
              <input type="checkbox" checked={form.llmlimityn}
                onChange={(e) => setForm((f) => ({ ...f, llmlimityn: e.target.checked }))} />
            </div>
          </div>

          <div className="form-group">
            <label>{t('lbl.email')}:</label>
            <input type="text" value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.telno')}:</label>
            <input type="text" value={form.telno}
              onChange={(e) => setForm((f) => ({ ...f, telno: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('thd.languagenm')}:</label>
            <select value={form.languagecd}
              onChange={(e) => setForm((f) => ({ ...f, languagecd: e.target.value }))}>
              <option value="">{t('msg.select')}</option>
              {languages.map((lang) => (
                <option key={lang.languagecd} value={lang.languagecd}>{lang.languagenm}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>{t('lbl.timezone')}:</label>
            <select value={form.timezone}
              onChange={(e) => setForm((f) => ({ ...f, timezone: e.target.value }))}>
              <option value="">{t('msg.select')}</option>
              {IANA_TIMEZONES.map((tz) => (
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

          <div className="form-group">
            <label>{t('lbl.tenant.icon')}:</label>
            <input type="file" ref={iconFileRef} style={{ display: 'none' }}
              accept="image/*" onChange={handleIconFileChange} />
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <button type="button" className="btn btn-primary" onClick={handleIconUploadClick}>
                {t('btn.upload_btn')}
              </button>
              <span
                style={{
                  cursor: iconFileUrl ? 'pointer' : 'default',
                  textDecoration: iconFileUrl ? 'underline' : 'none',
                  color: iconFileUrl ? 'blue' : 'black',
                }}
                onClick={() => iconFileUrl && window.open(iconFileUrl, '_blank')}
              >
                {iconFileNm || t('msg.no.image')}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
