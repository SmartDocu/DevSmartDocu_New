import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Spin, Segmented, Switch, Table } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import apiClient from '@/api/client'

const SERVICE_ORDER = ['Do', 'Ch', 'In']
const PLAN_ORDER = ['Fr', 'Pr', 'Te', 'En']
const CURRENCIES = ['KRW', 'USD']

export default function PricingPage() {
  useLangStore((s) => s.translations)

  const [currencycd, setCurrencycd] = useState('KRW')

  const { data, isLoading } = useQuery({
    queryKey: ['public-pricing', currencycd],
    queryFn: () => apiClient.get('/misc/pricing', { params: { currencycd } }).then((r) => r.data.products),
  })
  const products = data || []

  const availableServices = useMemo(() => {
    const set = new Set(products.filter((p) => p.producttype === 'Service').map((p) => p.servicecd))
    return SERVICE_ORDER.filter((s) => set.has(s))
  }, [products])

  const [selectedService, setSelectedService] = useState(null)
  const [byok, setByok] = useState(false)

  const activeService = availableServices.includes(selectedService) ? selectedService : availableServices[0]

  const serviceLabel = (cd) => t(`cod.servicecd_${cd}`) || cd
  const planLabel = (cd) => t(`cod.plancd_${cd}`) || cd

  const formatPrice = (p) => {
    if (!p) return '-'
    if (p.plancd === 'Fr') return t('lbl.pricing.free') || '무료'
    if (p.price == null) return '-'
    return `${Number(p.price).toLocaleString()} ${p.currencycd || ''}`
  }

  const pickPlan = (plancd) => {
    const candidates = products.filter(
      (p) => p.servicecd === activeService && p.plancd === plancd && p.producttype === 'Service',
    )
    if (plancd === 'Fr') return candidates[0]
    return candidates.find((p) => !!p.is_customeraikey === byok) || candidates[0]
  }

  const addonUsers = products.filter((p) => p.servicecd === activeService && p.producttype === 'User')
  const addonCredits = products.filter((p) => p.servicecd === activeService && p.producttype === 'Credit')
  const tenantFeatures = products.filter((p) => p.servicecd === 'Tenant' && p.producttype === 'Feature')

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.pricing.page')}</div>
        </div>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
      ) : (
        <div>
          <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 24, flexWrap: 'wrap' }}>
            <Segmented
              value={activeService}
              onChange={setSelectedService}
              options={availableServices.map((s) => ({ label: serviceLabel(s), value: s }))}
            />
            <Segmented
              value={currencycd}
              onChange={setCurrencycd}
              options={CURRENCIES.map((cd) => ({ label: cd, value: cd }))}
            />
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, cursor: 'pointer' }}>
              <Switch checked={byok} onChange={setByok} />
              {t('lbl.pricing.byok')}
            </label>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 32 }}>
            {PLAN_ORDER.map((plancd) => {
              const p = pickPlan(plancd)
              if (!p) return null
              return (
                <div key={plancd} style={{ border: '1px solid #e8e8e8', borderRadius: 8, padding: 20, textAlign: 'center' }}>
                  <div style={{ fontSize: 13, color: '#888', marginBottom: 4 }}>{planLabel(plancd)}</div>
                  <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 12 }}>{formatPrice(p)}</div>
                  <div style={{ fontSize: 13, color: '#555', textAlign: 'left', display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <div>{t('lbl.pricing.included_users')}: {p.users ?? '-'}</div>
                    <div>{t('lbl.pricing.included_credit')}: {p.credit ?? '-'}</div>
                  </div>
                </div>
              )
            })}
          </div>

          {(addonUsers.length > 0 || addonCredits.length > 0) && (
            <div style={{ display: 'flex', gap: 24, marginBottom: 32, flexWrap: 'wrap' }}>
              {addonUsers.length > 0 && (
                <div style={{ flex: '1 1 320px' }}>
                  <h3 style={{ marginBottom: 8 }}>{t('ttl.pricing.addon_users')}</h3>
                  <Table
                    size="small"
                    pagination={false}
                    dataSource={addonUsers}
                    rowKey="productcd"
                    tableLayout="fixed"
                    columns={[
                      { title: t('lbl.pricing.included_users'), dataIndex: 'users', key: 'users', width: '50%' },
                      { title: t('lbl.price'), key: 'price', width: '50%', render: (_, r) => formatPrice(r) },
                    ]}
                  />
                </div>
              )}
              {addonCredits.length > 0 && (
                <div style={{ flex: '1 1 320px' }}>
                  <h3 style={{ marginBottom: 8 }}>{t('ttl.pricing.addon_credits')}</h3>
                  <Table
                    size="small"
                    pagination={false}
                    dataSource={addonCredits}
                    rowKey="productcd"
                    tableLayout="fixed"
                    columns={[
                      { title: t('lbl.pricing.included_credit'), dataIndex: 'credit', key: 'credit', width: '50%' },
                      { title: t('lbl.price'), key: 'price', width: '50%', render: (_, r) => formatPrice(r) },
                    ]}
                  />
                </div>
              )}
            </div>
          )}

          {tenantFeatures.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <h3 style={{ marginBottom: 8 }}>{t('ttl.pricing.tenant_features')}</h3>
              <Table
                size="small"
                pagination={false}
                dataSource={tenantFeatures}
                rowKey="productcd"
                tableLayout="fixed"
                columns={[
                  { title: t('lbl.product'), dataIndex: 'productnm', key: 'productnm', width: '50%' },
                  { title: t('lbl.price'), key: 'price', width: '50%', render: (_, r) => formatPrice(r) },
                ]}
              />
            </div>
          )}

          <div style={{ fontSize: 12, color: '#888', marginTop: 24 }}>{t('inf.pricing.notice')}</div>
          {currencycd === 'USD' && (
            <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>{t('inf.pricing.usd_notice')}</div>
          )}
        </div>
      )}
    </div>
  )
}
