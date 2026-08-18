import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { App } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useUpgradeProducts, useUpgradePlan } from '@/hooks/useSettings'
import { useMenuCodes } from '@/hooks/useMenus'

export default function UpgradePlanPage() {
  useLangStore((s) => s.translations)
  const { message } = App.useApp()
  const [searchParams] = useSearchParams()
  const servicecd = searchParams.get('servicecd') || ''
  const plancd = searchParams.get('plancd') || 'Pr'

  const [selectedProduct, setSelectedProduct] = useState(null)

  const { data: initData = {}, isLoading } = useUpgradeProducts(servicecd, plancd)
  const { data: serviceCodes = [] } = useMenuCodes('servicecd')
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
    upgradeMutation.mutate(
      { productcd: selectedProduct.productcd, servicecd: selectedProduct.servicecd },
      {
        onSuccess: () => {
          message.success(t('msg.upgrade.success'))
          setSelectedProduct(null)
        },
        onError: (err) => message.error(err.response?.data?.detail || t('msg.upgrade.error')),
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

      <div className="table-container">
        <table className="table table-bordered table-sm" style={{ cursor: 'pointer' }}>
          <thead>
            <tr>
              <th style={{ width: '30%' }}>{t('thd.productnm_thd')}</th>
              <th style={{ width: '15%' }}>{t('thd.servicecd_thd')}</th>
              <th style={{ width: '15%' }}>{t('thd.billingtermcd_thd')}</th>
              <th style={{ width: '15%' }}>{t('thd.credit_thd')}</th>
              <th style={{ width: '25%' }}>{t('thd.is_customeraikey_thd')}</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={5} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
            ) : products.length === 0 ? (
              <tr><td colSpan={5} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
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
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
