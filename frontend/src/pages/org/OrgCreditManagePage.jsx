import { App } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useMenuCodes } from '@/hooks/useMenus'
import {
  useTenantManageCreditSubscriptions,
  usePurchaseTenantManageCreditSubscription,
} from '@/hooks/useSettings'
import { usePaymentGate, PAYMENT_METHOD_REQUIRED } from '@/hooks/usePayments'

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
            onSuccess: () => { message.success(t('msg.save.success')) },
            onError: (err) => {
              const detail = err.response?.data?.detail
              if (detail === PAYMENT_METHOD_REQUIRED) {
                promptCardRegistration()
                return
              }
              message.error(detail || t('msg.save.error'))
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
          <div className="gradient-bar" />
          <div>{t('ttl.tenant.manage.credit')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측(7): 크레딧 구매 내역 */}
        <div style={{ flex: 7, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <div />
          </div>
          <div className="table-container">
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

        {/* 우측(3): 구매 가능한 크레딧 상품 (즉시 구매) */}
        <div style={{ flex: 3, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div />
          </div>

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
                {t('btn.purchase')}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
