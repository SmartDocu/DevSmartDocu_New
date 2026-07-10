import { useRef, useState } from 'react'
import { App } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useSettingsTenants, useSaveTenant } from '@/hooks/useSettings'

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

  const iconFileRef = useRef(null)
  const [iconFile, setIconFile] = useState(null)
  const [iconFileNm, setIconFileNm] = useState('')
  const [iconFileUrl, setIconFileUrl] = useState('')

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
    setIconFile(null)
    setIconFileNm(row.iconfilenm || '')
    setIconFileUrl(row.iconfileurl || '')
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
    if (iconFile) fd.append('iconfile', iconFile)
    saveTenant.mutate(fd, {
      onSuccess: () => { message.success(t('msg.save.success')) },
      onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
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
      <div style={{ color: '#888', fontSize: 13, marginBottom: 12 }}>
        ※ 이 화면은 기존 기업의 사용여부·연락처·명칭 등 정보 수정만 가능합니다. (신규 생성·삭제 불가)
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측 패널: 기업 목록 */}
        <div style={{ flex: 3, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <div />
          </div>
          <div className="table-container">
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
              <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveTenant.isPending || !selectedId}>
                {t('btn.save')}
              </button>
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
