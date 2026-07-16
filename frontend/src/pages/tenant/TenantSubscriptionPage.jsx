import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, Button, Form, Input, Select } from 'antd'
import { useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useTabStore } from '@/stores/tabStore'
import { useLangStore, t } from '@/stores/langStore'
import { useTenantSubscriptionInit, useCreateTenantSubscription } from '@/hooks/useSettings'

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
      message.error(err.response?.data?.detail || t('msg.save.error'))
    }
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.tenant.subscription')}</div>
        </div>
      </div>

      <Form layout="vertical" style={{ maxWidth: 480 }}>
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
        <Form.Item>
          <Button type="primary" onClick={handleSave} loading={createTenant.isPending}>
            {t('btn.save')}
          </Button>
        </Form.Item>
      </Form>
    </div>
  )
}
