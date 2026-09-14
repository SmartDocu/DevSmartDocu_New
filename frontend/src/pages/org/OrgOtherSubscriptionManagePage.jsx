import { useState } from 'react'
import { App, Alert, Modal, Select, Input, InputNumber, Tag, Switch, Spin } from 'antd'
import { ShoppingCartOutlined } from '@ant-design/icons'
import { useLangStore, t } from '@/stores/langStore'
import { useMenuCodes } from '@/hooks/useMenus'
import {
  useTenantManageOtherSubscriptions,
  usePurchaseTenantManageOtherSubscription,
  useCancelTenantManageOtherSubscription,
  useCancelUndoTenantManageOtherSubscription,
  useUpdateTenantManageOtherSubscriptionQuantity,
  useTenantManageMfaConfig,
  useSaveTenantManageMfaConfig,
} from '@/hooks/useSettings'
import { usePaymentGate, PAYMENT_METHOD_REQUIRED } from '@/hooks/usePayments'
import { getErrorMessage } from '@/utils/apiError'

export default function OrgOtherSubscriptionManagePage() {
  const { message, modal } = App.useApp()
  useLangStore((s) => s.translations)

  const { data = {}, isLoading } = useTenantManageOtherSubscriptions()
  const owned = data.owned || []
  const products = data.products || []

  const { data: serviceCodes = [] } = useMenuCodes('servicecd')
  const { data: producttypeCodes = [] } = useMenuCodes('producttype')
  const { data: cancelReasonCodes = [] } = useMenuCodes('cancel_reasoncd')

  const { hasPaymentMethod, promptCardRegistration } = usePaymentGate('org/payment-manage')
  const purchaseMutation = usePurchaseTenantManageOtherSubscription()
  const cancelMutation = useCancelTenantManageOtherSubscription()
  const cancelUndoMutation = useCancelUndoTenantManageOtherSubscription()
  const quantityMutation = useUpdateTenantManageOtherSubscriptionQuantity()

  const [purchaseQty, setPurchaseQty] = useState({})
  const [deltaQty, setDeltaQty] = useState({})

  const { data: mfaConfig = {}, isLoading: mfaLoading } = useTenantManageMfaConfig()
  const saveMfaConfig = useSaveTenantManageMfaConfig()
  const handleMfaToggle = (checked) => {
    saveMfaConfig.mutate({ is_mfa: checked })
  }

  const [cancelTarget, setCancelTarget] = useState(null)
  const [cancelReasonCd, setCancelReasonCd] = useState(null)
  const [cancelReasonDesc, setCancelReasonDesc] = useState('')

  const codeLabel = (codes, cd) => {
    const found = codes.find((c) => c.codevalue === cd)
    return found ? (t(found.term_key) || found.default_name) : cd
  }
  const serviceLabel = (cd) => (!cd || cd === 'Tenant' ? t('lbl.common.tenant') : codeLabel(serviceCodes, cd))

  const handlePurchase = (product) => {
    if (!hasPaymentMethod) {
      promptCardRegistration()
      return
    }
    const qty = product.producttype === 'User' ? (purchaseQty[product.productcd] || 1) : 1
    const totalTxt = product.price != null ? `${Number(product.price * qty).toLocaleString()} ${product.currencycd || ''}` : '-'
    modal.confirm({
      content: product.producttype === 'User'
        ? t('msg.confirm.purchase.qty').replace('{qty}', qty).replace('{total}', totalTxt)
        : t('msg.confirm.purchase'),
      onOk: () => {
        purchaseMutation.mutate(
          { productcd: product.productcd, quantity: qty },
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

  const handleQuantityIncrease = (row) => {
    if (!hasPaymentMethod) {
      promptCardRegistration()
      return
    }
    const delta = deltaQty[row.subscriptionuid] || 1
    const totalTxt = row.unit_price != null ? `${Number(row.unit_price * delta).toLocaleString()} ${row.currencycd || ''}` : '-'
    modal.confirm({
      content: t('msg.confirm.purchase.qty').replace('{qty}', delta).replace('{total}', totalTxt),
      onOk: () => {
        quantityMutation.mutate(
          { subscriptionuid: row.subscriptionuid, delta },
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

  const handleQuantityDecrease = (row) => {
    const delta = deltaQty[row.subscriptionuid] || 1
    if (delta > row.quantity - row.pending_decrease_qty) {
      message.warning(t('msg.quantity.decrease.max_exceeded'))
      return
    }
    modal.confirm({
      content: t('msg.confirm.quantity.decrease.generic').replace('{qty}', delta),
      onOk: () => {
        quantityMutation.mutate(
          { subscriptionuid: row.subscriptionuid, delta: -delta },
          {
            onSuccess: (res) => {
              message.success(t('msg.quantity.decrease.scheduled').replace('{qty}', delta).replace('{date}', res.effective_date || ''))
            },
            onError: (err) => { message.error(getErrorMessage(err, 'msg.save.error')) },
          },
        )
      },
    })
  }

  const handleCancel = (subscriptionuid) => {
    setCancelTarget(subscriptionuid)
    setCancelReasonCd(null)
    setCancelReasonDesc('')
  }

  const handleCancelSubmit = () => {
    if (!cancelReasonCd) { message.warning(t('msg.select.placeholder')); return }
    cancelMutation.mutate(
      {
        subscriptionuid: cancelTarget,
        cancel_reasoncd: cancelReasonCd,
        cancel_reasondesc: cancelReasonDesc || null,
      },
      {
        onSuccess: () => { message.success(t('msg.subscription.cancel.reserved')); setCancelTarget(null) },
        onError: (err) => { message.error(getErrorMessage(err, 'msg.save.error')) },
      },
    )
  }

  const handleCancelUndo = (subscriptionuid) => {
    cancelUndoMutation.mutate(
      { subscriptionuid },
      {
        onSuccess: () => { message.success(t('msg.subscription.cancel.undo.success')) },
        onError: (err) => { message.error(getErrorMessage(err, 'msg.save.error')) },
      },
    )
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('ttl.tenant.manage.other_subscription')}</div>
        </div>
      </div>

      <div className="panel-section" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div>
          <div style={{ fontWeight: 600 }}>{t('lbl.tenant.mfa.enable')}</div>
          <div style={{ fontSize: 12, color: '#888', marginTop: 2 }}>{t('inf.mfa.free.notice')}</div>
        </div>
        <Switch
          checked={!!mfaConfig.is_mfa}
          loading={mfaLoading || saveMfaConfig.isPending}
          onChange={handleMfaToggle}
        />
      </div>

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
        {/* 좌측(7): 보유 중인 User/Feature 상품 목록 */}
        <div className="panel-section" style={{ flex: 7, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 320px)' }}>
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
                  <th>{t('thd.producttype_thd')}</th>
                  <th>{t('lbl.quantity')}</th>
                  <th>{t('thd.updatedts_thd')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : owned.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : owned.map((row) => (
                  <tr key={row.subscriptionuid}>
                    <td>{serviceLabel(row.servicecd)}</td>
                    <td>{row.productnm}</td>
                    <td>{codeLabel(producttypeCodes, row.producttype)}</td>
                    <td>
                      {row.producttype === 'User' ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <button
                              className="btn btn-secondary"
                              type="button"
                              style={{ height: 28, width: 28, padding: 0 }}
                              disabled={row.cancel_reserved || quantityMutation.isPending || (deltaQty[row.subscriptionuid] || 1) > row.quantity - row.pending_decrease_qty}
                              onClick={() => handleQuantityDecrease(row)}
                            >-</button>
                            <span style={{ minWidth: 28, textAlign: 'center', fontWeight: 600 }}>{row.quantity}</span>
                            <button
                              className="btn btn-secondary"
                              type="button"
                              style={{ height: 28, width: 28, padding: 0 }}
                              disabled={row.cancel_reserved || quantityMutation.isPending}
                              onClick={() => handleQuantityIncrease(row)}
                            >+</button>
                            <InputNumber
                              size="small"
                              min={1}
                              value={deltaQty[row.subscriptionuid] || 1}
                              onChange={(v) => setDeltaQty((s) => ({ ...s, [row.subscriptionuid]: v || 1 }))}
                              style={{ width: 56 }}
                              disabled={row.cancel_reserved}
                            />
                          </div>
                          {row.pending_decrease_qty > 0 && (
                            row.pending_decrease_blocked ? (
                              <Tag color="red" style={{ margin: 0 }}>
                                {t('inf.quantity.pending_decrease_blocked').replace('{qty}', row.pending_decrease_qty)}
                              </Tag>
                            ) : (
                              <Tag color="gold" style={{ margin: 0 }}>
                                {t('inf.quantity.pending_decrease').replace('{qty}', row.pending_decrease_qty).replace('{date}', row.pending_decrease_applydt || '')}
                              </Tag>
                            )
                          )}
                        </div>
                      ) : (row.users ? `${row.users} users` : '-')}
                    </td>
                    <td>{row.updatedts}</td>
                    <td style={{ textAlign: 'center' }}>
                      {row.cancel_reserved ? (
                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                          <Tag color="orange">
                            {t('lbl.pro.cancel.reserved')}{row.cancel_effective_date ? ` (${row.cancel_effective_date})` : ''}
                          </Tag>
                          <button className="btn btn-secondary" type="button" style={{ height: 28, padding: '0 10px' }} disabled={cancelUndoMutation.isPending} onClick={() => handleCancelUndo(row.subscriptionuid)}>
                            {t('btn.pro.cancel.undo')}
                          </button>
                        </div>
                      ) : row.producttype === 'User' ? (
                        // Add User는 전체 행을 몰수 취소하는 버튼 대신 수량(-) 조정으로 0까지 줄이도록 유도 — 혼동 방지
                        <span style={{ color: '#bbb' }}>-</span>
                      ) : (
                        <button
                          className="btn btn-danger"
                          type="button"
                          onClick={() => handleCancel(row.subscriptionuid)}
                        >
                          {t('btn.subscription.cancel')}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </div>
        </div>

        {/* 우측(3): 구매 가능 상품 목록 (즉시 구매) */}
        <div className="panel-section" style={{ flex: 3, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 320px)' }}>
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
                  {serviceLabel(p.servicecd)} · {codeLabel(producttypeCodes, p.producttype)}
                  {p.users ? ` · ${p.users} users` : ''}
                </div>
                {p.price != null && (
                  <div style={{ fontSize: 14, fontWeight: 600, color: '#163E64', marginTop: 4 }}>
                    {Number(p.price * (p.producttype === 'User' ? (purchaseQty[p.productcd] || 1) : 1)).toLocaleString()} {p.currencycd}
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {p.producttype === 'User' && (
                  <InputNumber
                    size="small"
                    min={1}
                    value={purchaseQty[p.productcd] || 1}
                    onChange={(v) => setPurchaseQty((s) => ({ ...s, [p.productcd]: v || 1 }))}
                    style={{ width: 56 }}
                  />
                )}
                <button
                  className="btn btn-primary"
                  type="button"
                  disabled={purchaseMutation.isPending}
                  onClick={() => handlePurchase(p)}
                >
                  <ShoppingCartOutlined style={{ marginRight: 6 }} />{t('btn.purchase')}
                </button>
              </div>
            </div>
          ))}
          </div>
        </div>
      </div>

      <Modal
        title={t('btn.subscription.cancel')}
        open={!!cancelTarget}
        onOk={handleCancelSubmit}
        onCancel={() => setCancelTarget(null)}
        confirmLoading={cancelMutation.isPending}
        okType="danger"
      >
        <div className="form-group">
          <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.cancel_reasoncd')}:</label>
          <Select
            value={cancelReasonCd}
            onChange={setCancelReasonCd}
            style={{ width: '100%' }}
            placeholder={t('msg.select.placeholder')}
            options={cancelReasonCodes.map((c) => ({
              label: t(c.term_key) || c.default_name,
              value: c.codevalue,
            }))}
          />
        </div>
        <div className="form-group">
          <label>{t('lbl.cancel_reasondesc')}:</label>
          <Input.TextArea
            rows={3}
            style={{ resize: 'vertical' }}
            value={cancelReasonDesc}
            onChange={(e) => setCancelReasonDesc(e.target.value)}
          />
        </div>
      </Modal>

      {/* 로딩 오버레이 */}
      {(purchaseMutation.isPending || cancelMutation.isPending || cancelUndoMutation.isPending || quantityMutation.isPending) && (
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
