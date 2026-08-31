import { useEffect, useState } from 'react'
import { App, InputNumber, Modal } from 'antd'
import * as PortOne from '@portone/browser-sdk/v2'
import { t } from '@/stores/langStore'
import { useMenuCodes } from '@/hooks/useMenus'
import {
  usePaymentConfig,
  usePaymentMethods,
  useSaveBillingKey,
  useDeletePaymentMethod,
  useSetDefaultPaymentMethod,
  useChargePaymentMethod,
  useBillingStatus,
  useRetryBilling,
} from '@/hooks/usePayments'

function getErrorMessage(err, fallback) {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => d?.msg || JSON.stringify(d)).join(', ')
  return fallback
}

/**
 * 결제수단(빌링키) 등록/삭제/테스트결제 공용 패널.
 * 기업(org/payment-manage)과 개인(payment-manage) 화면이 이 컴포넌트를 공유하고,
 * 청구서 발급 시 사용할 고객정보(customerInfo)만 각자 다른 소스에서 내려준다.
 */
export default function PaymentManagePanel({ pageTitle, customerInfo }) {
  const { message, modal } = App.useApp()
  const [issuing, setIssuing] = useState(false)

  const { data: config = {} } = usePaymentConfig()
  const { data: methodsData = {}, isLoading } = usePaymentMethods()
  const methods = methodsData.methods || []

  const { data: billingStatus = {} } = useBillingStatus()
  const retryMutation = useRetryBilling()
  const handleRetryBilling = () => {
    retryMutation.mutate(undefined, {
      onSuccess: () => { message.success(t('msg.billing.retry.success')) },
      onError: (err) => { message.error(getErrorMessage(err, t('msg.billing.retry.error'))) },
    })
  }

  const { data: statusCodes = [] } = useMenuCodes('payment_method_status')
  const statusLabel = (cd) => {
    const found = statusCodes.find((c) => c.codevalue === cd)
    return found ? (t(found.term_key) || found.default_name) : cd
  }

  const saveMutation = useSaveBillingKey()
  const deleteMutation = useDeletePaymentMethod()
  const setDefaultMutation = useSetDefaultPaymentMethod()
  const chargeMutation = useChargePaymentMethod()
  const [chargeTarget, setChargeTarget] = useState(null)
  const [chargeAmount, setChargeAmount] = useState(1000)

  const completeBillingKey = (billingKeyId) => {
    saveMutation.mutate(
      { billing_key_id: billingKeyId, is_default: methods.length === 0 },
      {
        onSuccess: () => { message.success(t('msg.save.success')) },
        onError: (err) => { message.error(getErrorMessage(err, t('msg.save.error'))) },
      },
    )
  }

  // 공동인증서 등 일부 인증수단은 팝업이 아니라 전체 페이지 리다이렉트로 진행된다.
  // redirectUrl로 돌아왔을 때 쿼리스트링에 실린 결과를 처리한다.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const billingKey = params.get('billingKey')
    const code = params.get('code')
    const returnedMessage = params.get('message')
    if (!billingKey && !code) return

    if (code) {
      message.error(returnedMessage || t('msg.payment.issue.error'))
    } else if (billingKey) {
      completeBillingKey(billingKey)
    }
    window.history.replaceState({}, '', window.location.pathname)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleAddBillingKey = async () => {
    if (!config.storeId || !config.channelKey) {
      message.error(t('msg.payment.config.missing'))
      return
    }

    setIssuing(true)
    try {
      const response = await PortOne.requestIssueBillingKey({
        storeId: config.storeId,
        channelKey: config.channelKey,
        billingKeyMethod: 'CARD',
        issueId: `bk-${Date.now()}`,
        issueName: `${customerInfo.fullName || ''} ${pageTitle}`.trim(),
        // PortOne는 customer.phoneNumber를 REQUIRED + NON_EMPTY_STRING으로 요구한다.
        // 개인 계정은 전화번호를 별도로 안 받기 때문에 값이 없으면 더미값으로 채운다
        // (백엔드 즉시결제 엔드포인트에서도 동일하게 처리 중 — payments.py 참고).
        customer: {
          fullName: customerInfo.fullName || '',
          email: customerInfo.email || '',
          phoneNumber: customerInfo.phoneNumber || '01000000000',
        },
        redirectUrl: `${window.location.origin}${window.location.pathname}`,
      })

      // redirectUrl로 전체 리다이렉트가 발생하는 인증수단은 여기서 response가 없거나
      // 페이지 자체가 새로 로드되므로 이 이후 코드가 실행되지 않을 수 있다.
      console.log('[PortOne] requestIssueBillingKey response:', response)

      if (!response || response.code != null) {
        message.error(response?.message || t('msg.payment.issue.error'))
        return
      }

      if (!response.billingKey) {
        message.error(t('msg.payment.issue.error'))
        return
      }

      completeBillingKey(response.billingKey)
    } catch (e) {
      message.error(e?.message || t('msg.payment.issue.error'))
    } finally {
      setIssuing(false)
    }
  }

  const handleSetDefault = (row) => {
    setDefaultMutation.mutate(row.payment_methoduid, {
      onSuccess: () => { message.success(t('msg.save.success')) },
      onError: (err) => { message.error(getErrorMessage(err, t('msg.save.error'))) },
    })
  }

  const handleDelete = (row) => {
    modal.confirm({
      content: t('msg.confirm.delete'),
      onOk: () => {
        deleteMutation.mutate(row.payment_methoduid, {
          onSuccess: () => { message.success(t('msg.delete.success')) },
          onError: (err) => { message.error(getErrorMessage(err, t('msg.delete.error'))) },
        })
      },
    })
  }

  const handleChargeConfirm = () => {
    chargeMutation.mutate(
      { paymentMethoduid: chargeTarget.payment_methoduid, amount: chargeAmount, orderName: t('btn.payment.test_charge') },
      {
        onSuccess: (data) => {
          message.success(`${t('msg.payment.charge.success')} (${data.pgTxId || '-'})`)
          setChargeTarget(null)
        },
        onError: (err) => { message.error(getErrorMessage(err, t('msg.payment.charge.error'))) },
      },
    )
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{pageTitle}</div>
        </div>
      </div>

      {(billingStatus.billing_status === 'PastDue' || billingStatus.billing_status === 'Suspended') && (
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16,
          border: '1px solid #ffccc7', background: '#fff2f0', borderRadius: 6,
          padding: '12px 16px', marginBottom: 16,
        }}>
          <div style={{ color: '#cf1322' }}>
            {billingStatus.billing_status === 'PastDue'
              ? t('inf.billing.pastdue_notice').replace('{date}', billingStatus.grace_until_dt || '')
              : t('inf.billing.suspended_notice')}
          </div>
          <button
            className="btn btn-primary"
            type="button"
            disabled={retryMutation.isPending}
            onClick={handleRetryBilling}
          >
            {t('btn.retry_billing')}
          </button>
        </div>
      )}

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 좌측(7): 등록된 결제수단 목록 */}
        <div style={{ flex: 7, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <div />
          </div>
          <div className="table-container">
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th>{t('lbl.card_brand')}</th>
                  <th>{t('lbl.card_no')}</th>
                  <th>{t('lbl.expiry')}</th>
                  <th>{t('lbl.status')}</th>
                  <th>{t('lbl.default')}</th>
                  <th style={{ textAlign: 'center' }}>{t('btn.payment.test_charge')}</th>
                  <th style={{ textAlign: 'center' }}>{t('btn.delete')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={7} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : methods.length === 0 ? (
                  <tr><td colSpan={7} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : methods.map((row) => (
                  <tr key={row.payment_methoduid}>
                    <td>{row.display_nm || row.card_brand || '-'}</td>
                    <td>{'*'.repeat(Math.max(0, 4 - (row.card_last4?.length || 0))) + (row.card_last4 || '')}</td>
                    <td>{row.expiry_month ? `${row.expiry_month}/${row.expiry_year}` : '-'}</td>
                    <td>{statusLabel(row.payment_method_status)}</td>
                    <td style={{ textAlign: 'center' }}>
                      {row.is_default ? t('lbl.default') : row.payment_method_status === 'Active' && (
                        <button
                          className="btn btn-primary"
                          type="button"
                          disabled={setDefaultMutation.isPending}
                          onClick={() => handleSetDefault(row)}
                        >
                          {t('btn.payment.set_default')}
                        </button>
                      )}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <button
                        className="btn btn-primary"
                        type="button"
                        onClick={() => { setChargeTarget(row); setChargeAmount(1000) }}
                      >
                        {t('btn.payment.test_charge')}
                      </button>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <button
                        className="btn btn-danger"
                        type="button"
                        disabled={deleteMutation.isPending}
                        onClick={() => handleDelete(row)}
                      >
                        {t('btn.delete')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측(3): 결제수단 등록 */}
        <div style={{ flex: 3, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div />
          </div>
          <div style={{ border: '1px solid #eee', borderRadius: 6, padding: 16, textAlign: 'center' }}>
            <div style={{ color: '#888', marginBottom: 12 }}>{t('inf.payment.add.card')}</div>
            <button
              className="btn btn-primary"
              type="button"
              disabled={issuing || saveMutation.isPending}
              onClick={handleAddBillingKey}
            >
              {t('btn.payment.register')}
            </button>
          </div>
        </div>
      </div>

      <Modal
        title={t('btn.payment.test_charge')}
        open={!!chargeTarget}
        onOk={handleChargeConfirm}
        onCancel={() => setChargeTarget(null)}
        confirmLoading={chargeMutation.isPending}
        okText={t('btn.confirm')}
        cancelText={t('btn.cancel')}
      >
        <InputNumber
          style={{ width: '100%' }}
          min={100}
          step={100}
          value={chargeAmount}
          onChange={(v) => setChargeAmount(v)}
          addonAfter="KRW"
        />
        <div style={{ fontSize: 12, color: '#888', marginTop: 8 }}>{t('inf.payment.test_charge.notice')}</div>
      </Modal>
    </div>
  )
}
