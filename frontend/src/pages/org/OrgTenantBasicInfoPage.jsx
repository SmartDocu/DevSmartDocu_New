import { useEffect, useState } from 'react'
import { App, Card } from 'antd'
import { SaveOutlined } from '@ant-design/icons'
import { useLangStore, t } from '@/stores/langStore'
import { useTenantManageBasicInfo, useSaveTenantManageBasicInfo } from '@/hooks/useSettings'
import { getErrorMessage } from '@/utils/apiError'

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

  useEffect(() => {
    setDisptenantnm(data.disptenantnm || '')
    setLanguagecd(data.languagecd || '')
    setTimezoneVal(data.timezone || '')
    setEmail(data.email || '')
    setTelno(data.telno || '')
  }, [data.disptenantnm, data.languagecd, data.timezone, data.email, data.telno])

  const languages = data.languages || []
  const timezones = data.timezones || []

  const handleSave = () => {
    const fd = new FormData()
    if (disptenantnm) fd.append('disptenantnm', disptenantnm)
    if (languagecd) fd.append('languagecd', languagecd)
    if (timezoneVal) fd.append('timezone', timezoneVal)
    if (email) fd.append('email', email)
    if (telno) fd.append('telno', telno)
    saveMutation.mutate(fd, {
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
          <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
        </button>
      </div>

      <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start', paddingRight: 10 }}>
        {/* 영역 1: tenants — 언어 / 타임존 */}
        <Card size="small" title={t('ttl.tenant.manage.basic_info.tenant')} style={{ flex: 1, minWidth: 0 }} loading={isLoading}>
          <div className="form-group">
            <label>{t('lbl.disptenantnm')}:</label>
            <input type="text" value={disptenantnm} style={{ height: 38 }} onChange={(e) => setDisptenantnm(e.target.value)} />
          </div>

          <div className="form-group">
            <label>{t('thd.languagenm')}:</label>
            <select value={languagecd} style={{ height: 38 }} onChange={(e) => setLanguagecd(e.target.value)}>
              <option value="">{t('msg.select')}</option>
              {languages.map((lang) => (
                <option key={lang.languagecd} value={lang.languagecd}>{lang.languagenm}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>{t('lbl.timezone')}:</label>
            <select value={timezoneVal} style={{ height: 38 }} onChange={(e) => setTimezoneVal(e.target.value)}>
              <option value="">{t('msg.select')}</option>
              {timezones.map((tz) => (
                <option key={tz} value={tz}>{tz}</option>
              ))}
            </select>
          </div>
        </Card>

        {/* 영역 2: accounts — 담당자 연락처 */}
        <Card size="small" title={t('ttl.tenant.manage.basic_info.account')} style={{ flex: 1, minWidth: 0 }} loading={isLoading}>
          <div className="form-group">
            <label>{t('lbl.email')}:</label>
            <input type="text" value={email} style={{ height: 38 }} onChange={(e) => setEmail(e.target.value)} />
          </div>

          <div className="form-group">
            <label>{t('lbl.telno')}:</label>
            <input type="text" value={telno} style={{ height: 38 }} onChange={(e) => setTelno(e.target.value)} />
          </div>
        </Card>
      </div>
    </div>
  )
}
