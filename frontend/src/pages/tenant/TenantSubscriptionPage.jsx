import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, Form, Input, Select } from 'antd'
import { SaveOutlined } from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useTabStore } from '@/stores/tabStore'
import { useLangStore, t } from '@/stores/langStore'
import { useTenantSubscriptionInit, useCreateTenantSubscription } from '@/hooks/useSettings'
import { getErrorMessage } from '@/utils/apiError'

export default function TenantSubscriptionPage() {
  useLangStore((s) => s.translations)
  const { message } = App.useApp()
  const navigate = useNavigate()
  const { user, switchTenant, updateUser } = useAuthStore()
  const clearTabs = useTabStore((s) => s.clearTabs)
  const queryClient = useQueryClient()

  const { data = {}, isLoading } = useTenantSubscriptionInit()
  const createTenant = useCreateTenantSubscription()

  const [tenantnm, setTenantnm] = useState('')
  const [languagecd, setLanguagecd] = useState(null)
  const [tz, setTz] = useState(null)

  const languages = data.languages || []
  const timezones = data.timezones || []

  useEffect(() => {
    if (data.default_languagecd) setLanguagecd(data.default_languagecd)
    if (data.default_timezone) setTz(data.default_timezone)
  }, [data.default_languagecd, data.default_timezone])

  const handleSave = async () => {
    if (!tenantnm.trim()) { message.warning(t('msg.tenantnm.required')); return }
    try {
      const created = await createTenant.mutateAsync({ tenantnm, languagecd, timezone: tz })
      const sw = await apiClient.post('/auth/switch-tenant', {
        tenantid: created.tenantid,
        refresh_token: useAuthStore.getState().refreshToken,
      })
      switchTenant(created.tenantid)
      updateUser({
        tenantnm: sw.data.tenantnm,
        tenanticonurl: sw.data.tenanticonurl,
        accountuid: sw.data.accountuid,
        tenantmanager: sw.data.tenantmanager ?? 'N',
        accountmanager: sw.data.accountmanager ?? 'N',
        issystemtenant: sw.data.issystemtenant ?? null,
        tenants: [...(user?.tenants || []), { tenantid: String(created.tenantid), tenantnm: sw.data.tenantnm }],
      })
      queryClient.invalidateQueries()
      clearTabs()
      message.success(t('msg.save.success'))
      navigate('/launcher')
    } catch (err) {
      message.error(getErrorMessage(err, 'msg.save.error'))
    }
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('ttl.tenant.subscription')}</div>
        </div>
      </div>

      <div className="panel-section" style={{ maxWidth: 480 }}>
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', height: 60,
          margin: '-16px -18px 16px', padding: '16px 18px 12px',
          borderBottom: '1px solid var(--border-color, #e3e6eb)',
        }}>
          <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
          <button className="btn btn-primary" type="button" onClick={handleSave} disabled={createTenant.isPending}>
            <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
          </button>
        </div>

        <Form layout="vertical">
          <Form.Item label={t('lbl.tenantnm')} required>
            <Input value={tenantnm} onChange={(e) => setTenantnm(e.target.value)} disabled={isLoading} />
          </Form.Item>
          <Form.Item label={t('lbl.languagecd')}>
            <Select
              value={languagecd}
              onChange={setLanguagecd}
              loading={isLoading}
              options={languages.map((l) => ({ label: l.languagenm, value: l.languagecd }))}
            />
          </Form.Item>
          <Form.Item label={t('lbl.timezone')}>
            <Select
              value={tz}
              onChange={setTz}
              loading={isLoading}
              showSearch
              options={timezones.map((z) => ({ label: z, value: z }))}
            />
          </Form.Item>
        </Form>
      </div>
    </div>
  )
}
