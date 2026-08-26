import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { App, Alert, Spin } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useUpgradeProducts, useUpgradePlan } from '@/hooks/useSettings'
import { useMenuCodes } from '@/hooks/useMenus'
import { usePaymentGate, PAYMENT_METHOD_REQUIRED } from '@/hooks/usePayments'

export default function UpgradePlanPage() {
  useLangStore((s) => s.translations)
  const { message } = App.useApp()
  const [searchParams] = useSearchParams()
  const servicecd = searchParams.get('servicecd') || ''
  const plancd = searchParams.get('plancd') || 'Pr'

  const [selectedProduct, setSelectedProduct] = useState(null)

  const { data: initData = {}, isLoading } = useUpgradeProducts(servicecd, plancd)
  const { data: serviceCodes = [] } = useMenuCodes('servicecd')
  const { hasPaymentMethod, promptCardRegistration } = usePaymentGate('payment-manage')
  const upgradeMutation = useUpgradePlan()

  const products = initData.products || []

  const serviceLabel = (scd) => {
    const found = serviceCodes.find((c) => c.codevalue === scd)
    return found ? (t(found.term_key) || found.default_name) : scd
  }

  const { data: billingTermCodes = [] } = useMenuCodes('billingtermcd')
  const billingLabel = (cd) => {
    const found = billingTermCodes.find((c) => c.codevalue === cd)
    return found ? (t(found.term_key) || found.default_name) : (cd || '-')
  }

  const handleUpgrade = () => {
    if (!selectedProduct) return
    if (!hasPaymentMethod) {
      promptCardRegistration()
      return
    }
    upgradeMutation.mutate(
      { productcd: selectedProduct.productcd, servicecd: selectedProduct.servicecd },
      {
        onSuccess: () => {
          message.success(t('msg.upgrade.success'))
          setSelectedProduct(null)
        },
        onError: (err) => {
          const detail = err.response?.data?.detail
          if (detail === PAYMENT_METHOD_REQUIRED) {
            promptCardRegistration()
            return
          }
          message.error(detail || t('msg.upgrade.error'))
        },
      },
    )
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.upgrade.available')}</div>
          <button
            className="btn btn-primary"
            type="button"
            style={{ marginLeft: 'auto' }}
            disabled={!selectedProduct || upgradeMutation.isPending}
            onClick={handleUpgrade}
          >
            {t('btn.upgrade')}
          </button>
        </div>
      </div>

      {products.some((p) => p.currencycd === 'USD') && (
        <Alert type="info" showIcon message={t('inf.pricing.usd_notice')} style={{ marginBottom: 10 }} />
      )}

      <div className="table-container">
        <table className="table table-bordered table-sm" style={{ cursor: 'pointer' }}>
          <thead>
            <tr>
              <th style={{ width: '30%' }}>{t('thd.productnm_thd')}</th>
              <th style={{ width: '15%' }}>{t('thd.servicecd_thd')}</th>
              <th style={{ width: '15%' }}>{t('thd.billingtermcd_thd')}</th>
              <th style={{ width: '15%' }}>{t('thd.credit_thd')}</th>
              <th style={{ width: '20%' }}>{t('thd.is_customeraikey_thd')}</th>
              <th style={{ width: '20%' }}>{t('lbl.price')}</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={6} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
            ) : products.length === 0 ? (
              <tr><td colSpan={6} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
            ) : products.map((p) => (
              <tr
                key={p.productcd}
                className={selectedProduct?.productcd === p.productcd ? 'selected-row' : ''}
                onClick={() => setSelectedProduct(selectedProduct?.productcd === p.productcd ? null : p)}
              >
                <td>{p.productnm || p.productcd}</td>
                <td>{serviceLabel(p.servicecd)}</td>
                <td>{billingLabel(p.billingtermcd)}</td>
                <td style={{ textAlign: 'center' }}>{p.credit ?? '-'}</td>
                <td style={{ textAlign: 'center' }}>{p.is_customeraikey ? '✔' : '-'}</td>
                <td style={{ textAlign: 'right' }}>{p.price != null ? `${Number(p.price).toLocaleString()} ${p.currencycd}` : '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 로딩 오버레이 */}
      {upgradeMutation.isPending && (
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
