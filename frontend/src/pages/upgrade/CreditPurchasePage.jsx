import { App } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useMyInfoCreditPurchase, usePurchaseMyInfoCredit } from '@/hooks/useSettings'

export default function CreditPurchasePage() {
  useLangStore((s) => s.translations)
  const { message, modal } = App.useApp()

  const { data = {}, isLoading } = useMyInfoCreditPurchase()
  const purchaseMutation = usePurchaseMyInfoCredit()

  const products = data.products || []
  const owned = data.owned || []

  const handlePurchase = (productcd) => {
    modal.confirm({
      content: t('msg.confirm.purchase'),
      onOk: () => {
        purchaseMutation.mutate(
          { productcd },
          {
            onSuccess: () => { message.success(t('msg.save.success')) },
            onError: (err) => { message.error(err.response?.data?.detail || t('msg.save.error')) },
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
          <div>{t('ttl.myinfo.credit.purchase')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측(7): 보유 중인 크레딧 내역 */}
        <div style={{ flex: 7, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <div />
          </div>
          <div className="table-container">
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th>{t('lbl.product')}</th>
                  <th>{t('lbl.credit')}</th>
                  <th>{t('thd.createdts_thd')}</th>
                  <th>{t('lbl.expiresdts')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : owned.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : owned.map((row) => (
                  <tr key={row.subscriptionuid}>
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

        {/* 우측(3): 구매 가능한 크레딧 상품 */}
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
                <div style={{ fontSize: 12, color: '#888' }}>{p.credit} credit</div>
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
