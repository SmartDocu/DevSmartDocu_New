import { App, Alert, Spin } from 'antd'
import { ShoppingCartOutlined } from '@ant-design/icons'
import { useLangStore, t } from '@/stores/langStore'
import { useMenuCodes } from '@/hooks/useMenus'
import {
  useTenantManageCreditSubscriptions,
  usePurchaseTenantManageCreditSubscription,
} from '@/hooks/useSettings'
import { usePaymentGate, PAYMENT_METHOD_REQUIRED } from '@/hooks/usePayments'
import { getErrorMessage } from '@/utils/apiError'

export default function OrgCreditManagePage() {
  const { message, modal } = App.useApp()
  useLangStore((s) => s.translations)

  const { data = {}, isLoading } = useTenantManageCreditSubscriptions()
  const owned = data.owned || []
  const products = data.products || []

  const { data: serviceCodes = [] } = useMenuCodes('servicecd')
  const serviceLabel = (cd) => {
    const found = serviceCodes.find((c) => c.codevalue === cd)
    return found ? (t(found.term_key) || found.default_name) : cd
  }

  const { hasPaymentMethod, promptCardRegistration } = usePaymentGate('org/payment-manage')
  const purchaseMutation = usePurchaseTenantManageCreditSubscription()

  const handlePurchase = (productcd) => {
    if (!hasPaymentMethod) {
      promptCardRegistration()
      return
    }
    modal.confirm({
      content: t('msg.confirm.purchase'),
      onOk: () => {
        purchaseMutation.mutate(
          { productcd },
          {
            onSuccess: () => { message.success(t('msg.purchase.success')) },
            onError: (err) => {
              const detail = err.response?.data?.detail
              if (detail === PAYMENT_METHOD_REQUIRED) {
                promptCardRegistration()
                return
              }
              message.error(getErrorMessage(err, 'msg.save.error'))
            },
          },
        )
      },
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
          <div>{t('ttl.tenant.manage.credit')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
        {/* 좌측(7): 크레딧 구매 내역 */}
        <div className="panel-section" style={{ flex: 7, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 224px)' }}>
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
                {t('lbl.count.docs').replace('{n}', owned.length)}
              </span>
            </div>
            <div />
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th>{t('lbl.service_name_lbl')}</th>
                  <th>{t('lbl.product')}</th>
                  <th>{t('lbl.credit')}</th>
                  <th>{t('thd.createdts_thd')}</th>
                  <th>{t('lbl.expiresdts')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={5} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : owned.length === 0 ? (
                  <tr><td colSpan={5} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : owned.map((row) => (
                  <tr key={row.subscriptionuid}>
                    <td>{serviceLabel(row.servicecd)}</td>
                    <td>{row.productnm}</td>
                    <td>{row.quantity}</td>
                    <td>{row.createdts}</td>
                    <td>{row.expiresdts || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </div>
        </div>

        {/* 우측(3): 구매 가능한 크레딧 상품 (즉시 구매) */}
        <div className="panel-section" style={{ flex: 3, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 224px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div />
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>

          {products.some((p) => p.currencycd === 'USD') && (
            <Alert type="info" showIcon message={t('inf.pricing.usd_notice')} style={{ marginBottom: 10 }} />
          )}
          {products.length === 0 ? (
            <div style={{ color: '#999', padding: '40px 0', textAlign: 'center' }}>{t('msg.no.data')}</div>
          ) : products.map((p) => (
            <div
              key={p.productcd}
              style={{
                border: '1px solid #eee', borderRadius: 6, padding: 12, marginBottom: 10,
                display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8,
              }}
            >
              <div>
                <div style={{ fontWeight: 600 }}>{p.productnm}</div>
                <div style={{ fontSize: 12, color: '#888' }}>
                  {serviceLabel(p.servicecd)} · {p.credit} credit
                </div>
                {p.price != null && (
                  <div style={{ fontSize: 14, fontWeight: 600, color: '#163E64', marginTop: 4 }}>
                    {Number(p.price).toLocaleString()} {p.currencycd}
                  </div>
                )}
              </div>
              <button
                className="btn btn-primary"
                type="button"
                disabled={purchaseMutation.isPending}
                onClick={() => handlePurchase(p.productcd)}
              >
                <ShoppingCartOutlined style={{ marginRight: 6 }} />{t('btn.purchase')}
              </button>
            </div>
          ))}
          </div>
        </div>
      </div>

      {/* 로딩 오버레이 */}
      {purchaseMutation.isPending && (
        <div style={{
          position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
          background: 'rgba(0,0,0,0.5)',
          display: 'flex', justifyContent: 'center', alignItems: 'center',
          zIndex: 9999,
        }}>
          <div style={{
            background: '#fafae5', padding: '20px 30px', borderRadius: 8,
            fontSize: 16, fontWeight: 'bold', color: '#6c757d',
            boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
            display: 'flex', alignItems: 'center', gap: 12,
          }}>
            <Spin />
            <span>{t('msg.loading.wait')}</span>
          </div>
        </div>
      )}
    </div>
  )
}
