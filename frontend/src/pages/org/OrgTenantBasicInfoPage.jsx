import { useEffect, useRef, useState } from 'react'
import { App, Card } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useTenantManageBasicInfo, useSaveTenantManageBasicInfo } from '@/hooks/useSettings'

export default function OrgTenantBasicInfoPage() {
  const { message } = App.useApp()
  useLangStore((s) => s.translations)

  const { data = {}, isLoading } = useTenantManageBasicInfo()
  const saveMutation = useSaveTenantManageBasicInfo()

  const [disptenantnm, setDisptenantnm] = useState('')
  const [languagecd, setLanguagecd] = useState('')
  const [timezoneVal, setTimezoneVal] = useState('')
  const [email, setEmail] = useState('')
  const [telno, setTelno] = useState('')

  const iconFileRef = useRef(null)
  const [iconFile, setIconFile] = useState(null)
  const [iconFileNm, setIconFileNm] = useState('')
  const [iconFileUrl, setIconFileUrl] = useState('')
  const [iconPreviewUrl, setIconPreviewUrl] = useState('')

  useEffect(() => {
    setDisptenantnm(data.disptenantnm || '')
    setLanguagecd(data.languagecd || '')
    setTimezoneVal(data.timezone || '')
    setEmail(data.email || '')
    setTelno(data.telno || '')
    setIconFile(null)
    setIconFileNm(data.iconfilenm || '')
    setIconFileUrl(data.iconfileurl || '')
  }, [data.disptenantnm, data.languagecd, data.timezone, data.email, data.telno, data.iconfilenm, data.iconfileurl])

  useEffect(() => {
    if (iconFile) {
      const objUrl = URL.createObjectURL(iconFile)
      setIconPreviewUrl(objUrl)
      return () => URL.revokeObjectURL(objUrl)
    }
    setIconPreviewUrl(iconFileUrl || '')
  }, [iconFile, iconFileUrl])

  const languages = data.languages || []
  const timezones = data.timezones || []

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

  const handleSave = () => {
    const fd = new FormData()
    if (disptenantnm) fd.append('disptenantnm', disptenantnm)
    if (languagecd) fd.append('languagecd', languagecd)
    if (timezoneVal) fd.append('timezone', timezoneVal)
    if (email) fd.append('email', email)
    if (telno) fd.append('telno', telno)
    if (iconFile) fd.append('iconfile', iconFile)
    saveMutation.mutate(fd, {
      onSuccess: () => { message.success(t('msg.save.success')) },
      onError: (err) => { message.error(t(err.response?.data?.detail) || t('msg.save.error')) },
    })
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.tenant.manage.basic_info')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12, paddingRight: 10 }}>
        <button
          className="btn btn-primary"
          type="button"
          onClick={handleSave}
          disabled={saveMutation.isPending || isLoading}
        >
          {t('btn.save')}
        </button>
      </div>

      <div style={{ maxWidth: 640, paddingRight: 10 }}>
        {/* 영역 1: tenants — 아이콘 / 언어 / 타임존 */}
        <Card size="small" title={t('ttl.tenant.manage.basic_info.tenant')} style={{ marginBottom: 20 }} loading={isLoading}>
          <div className="form-group">
            <label>{t('lbl.disptenantnm')}:</label>
            <input type="text" value={disptenantnm} onChange={(e) => setDisptenantnm(e.target.value)} />
          </div>

          <div className="form-group">
            <label>{t('lbl.tenant.icon')}:</label>
            <input type="file" ref={iconFileRef} style={{ display: 'none' }} accept="image/*" onChange={handleIconFileChange} />
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
              {iconPreviewUrl && (
                <img
                  src={iconPreviewUrl}
                  alt=""
                  style={{
                    width: 60, height: 60, objectFit: 'contain',
                    border: '1px solid #eee', borderRadius: 4, padding: 4,
                  }}
                />
              )}
            </div>
          </div>

          <div className="form-group">
            <label>{t('thd.languagenm')}:</label>
            <select value={languagecd} onChange={(e) => setLanguagecd(e.target.value)}>
              <option value="">{t('msg.select')}</option>
              {languages.map((lang) => (
                <option key={lang.languagecd} value={lang.languagecd}>{lang.languagenm}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>{t('lbl.timezone')}:</label>
            <select value={timezoneVal} onChange={(e) => setTimezoneVal(e.target.value)}>
              <option value="">{t('msg.select')}</option>
              {timezones.map((tz) => (
                <option key={tz} value={tz}>{tz}</option>
              ))}
            </select>
          </div>
        </Card>

        {/* 영역 2: accounts — 담당자 연락처 */}
        <Card size="small" title={t('ttl.tenant.manage.basic_info.account')} loading={isLoading}>
          <div className="form-group">
            <label>{t('lbl.email')}:</label>
            <input type="text" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>

          <div className="form-group">
            <label>{t('lbl.telno')}:</label>
            <input type="text" value={telno} onChange={(e) => setTelno(e.target.value)} />
          </div>
        </Card>
      </div>
    </div>
  )
}
