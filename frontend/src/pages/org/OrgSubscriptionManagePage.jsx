import { useState, useEffect } from 'react'
import { App, Radio } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useMenuCodes } from '@/hooks/useMenus'
import {
  useTenantManageSubscriptions,
  useTenantManageTeamProducts,
  useChangeTenantSubscription,
} from '@/hooks/useSettings'

export default function OrgSubscriptionManagePage() {
  const { message, modal } = App.useApp()
  useLangStore((s) => s.translations)

  const { data: subData = {}, isLoading: subsLoading } = useTenantManageSubscriptions()
  const subscriptions = subData.subscriptions || []

  const { data: serviceCodes = [] } = useMenuCodes('servicecd')
  const { data: planCodes = [] } = useMenuCodes('plancd')

  const [selectedServicecd, setSelectedServicecd] = useState(null)
  const [selectedProductcd, setSelectedProductcd] = useState(null)

  const { data: prodData = {}, isLoading: prodsLoading } = useTenantManageTeamProducts(selectedServicecd)
  const products = prodData.products || []

  const changeMutation = useChangeTenantSubscription()

  // 상품 목록 로딩 완료 시 현재 구독 중인 상품을 기본 선택
  useEffect(() => {
    if (!selectedServicecd || products.length === 0) return
    const current = subscriptions.find((s) => s.servicecd === selectedServicecd)
    if (current && products.some((p) => p.productcd === current.productcd)) {
      setSelectedProductcd(current.productcd)
    }
  }, [selectedServicecd, products, subscriptions])

  const codeLabel = (codes, cd) => {
    const found = codes.find((c) => c.codevalue === cd)
    return found ? (t(found.term_key) || found.default_name) : cd
  }

  const handleSelectRow = (row) => {
    setSelectedServicecd(row.servicecd)
    setSelectedProductcd(null)
  }

  const handleSave = () => {
    if (!selectedServicecd || !selectedProductcd) { message.warning(t('msg.select.placeholder')); return }

    const currentSub = subscriptions.find((s) => s.servicecd === selectedServicecd)
    if (currentSub && currentSub.productcd === selectedProductcd) {
      message.warning(t('msg.subscription.already'))
      return
    }

    modal.confirm({
      content: t('msg.confirm.subscription.change'),
      onOk: () => {
        changeMutation.mutate(
          { servicecd: selectedServicecd, productcd: selectedProductcd },
          {
            onSuccess: () => { message.success(t('msg.save.success')); setSelectedProductcd(null) },
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
          <div>{t('ttl.tenant.manage.subscription')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측(7): 현재 구독 중인 서비스 목록 */}
        <div style={{ flex: 7, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <div />
          </div>
          <div className="table-container">
            <table className="table table-bordered table-sm" style={{ cursor: 'pointer' }}>
              <thead>
                <tr>
                  <th>{t('lbl.service_name_lbl')}</th>
                  <th>{t('lbl.product')}</th>
                  <th>{t('lbl.plan')}</th>
                  <th>{t('lbl.items')}</th>
                </tr>
              </thead>
              <tbody>
                {subsLoading ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : subscriptions.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : subscriptions.map((s) => (
                  <tr
                    key={s.servicecd}
                    className={selectedServicecd === s.servicecd ? 'selected-row' : ''}
                    onClick={() => handleSelectRow(s)}
                  >
                    <td>{codeLabel(serviceCodes, s.servicecd)}</td>
                    <td>{s.productnm || '-'}</td>
                    <td>{s.plancd ? codeLabel(planCodes, s.plancd) : '-'}</td>
                    <td>{s.users ? `${s.users} users / ${s.credit ?? 0} credit` : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측(3): 선택한 서비스의 Team/Enterprise 상품 선택 */}
        <div style={{ flex: 3, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <button
              className="btn btn-primary"
              type="button"
              onClick={handleSave}
              disabled={changeMutation.isPending || !selectedProductcd}
            >
              {t('btn.save')}
            </button>
          </div>

          {!selectedServicecd ? (
            <div style={{ color: '#999', padding: '40px 0', textAlign: 'center' }}>{t('msg.select.placeholder')}</div>
          ) : prodsLoading ? (
            <div style={{ textAlign: 'center', padding: 40 }}>{t('msg.loading')}</div>
          ) : products.length === 0 ? (
            <div style={{ color: '#999', padding: '40px 0', textAlign: 'center' }}>{t('msg.no.data')}</div>
          ) : (
            <Radio.Group
              style={{ width: '100%' }}
              value={selectedProductcd}
              onChange={(e) => setSelectedProductcd(e.target.value)}
            >
              {products.map((p) => (
                <div
                  key={p.productcd}
                  style={{ border: '1px solid #eee', borderRadius: 6, padding: 12, marginBottom: 10 }}
                >
                  <Radio value={p.productcd} style={{ width: '100%' }}>
                    <div style={{ fontWeight: 600 }}>{p.productnm}</div>
                    <div style={{ fontSize: 12, color: '#888' }}>
                      {codeLabel(planCodes, p.plancd)} · {p.billingtermcd} · {p.users} users · {p.credit} credit
                    </div>
                  </Radio>
                </div>
              ))}
            </Radio.Group>
          )}
        </div>
      </div>
    </div>
  )
}
