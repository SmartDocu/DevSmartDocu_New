import { useState } from 'react'
import { App, Alert, Button, Space, Tag } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useMenuCodes } from '@/hooks/useMenus'
import {
  useTenantManageSubscriptions,
  useRequestTenantCancel,
  useUndoTenantCancel,
} from '@/hooks/useSettings'
import { useOpenInTab } from '@/hooks/useOpenInTab'
import TenantCancelModal from '@/components/payment/TenantCancelModal'

export default function OrgTenantCancelPage() {
  const { message } = App.useApp()
  useLangStore((s) => s.translations)
  const openInTab = useOpenInTab()

  const { data: subData = {}, isLoading } = useTenantManageSubscriptions()
  const subscriptions = (subData.subscriptions || []).filter((s) => !!s.productcd)
  const tenantCancelRequested = subData.tenant_cancel_requested
  const tenantCancelRequestedDt = subData.tenant_cancel_requested_dt

  const { data: serviceCodes = [] } = useMenuCodes('servicecd')
  const serviceLabel = (cd) => {
    const found = serviceCodes.find((c) => c.codevalue === cd)
    return found ? (t(found.term_key) || found.default_name) : cd
  }
  const { data: cancelReasonCodes = [] } = useMenuCodes('cancel_reasoncd')

  const requestMutation = useRequestTenantCancel()
  const undoMutation = useUndoTenantCancel()
  const [modalOpen, setModalOpen] = useState(false)

  // 아직 활성인데 해지 예약이 안 된 서비스가 하나라도 있으면 테넌트 해지를 막는다
  const pendingServices = subscriptions.filter((s) => s.servicestatus === 'Active' && !s.cancel_reserved)
  const canRequestCancel = pendingServices.length === 0

  const handleSubmit = (payload) => {
    requestMutation.mutate(payload, {
      onSuccess: () => {
        message.success(t('msg.tenant_cancel.reserved'))
        setModalOpen(false)
      },
      onError: (err) => {
        const detail = err.response?.data?.detail
        message.error(detail ? t(detail) : t('msg.save.error'))
      },
    })
  }

  const handleUndo = () => {
    undoMutation.mutate(undefined, {
      onSuccess: () => { message.success(t('msg.tenant_cancel.undo.success')) },
      onError: (err) => {
        const detail = err.response?.data?.detail
        message.error(detail ? t(detail) : t('msg.save.error'))
      },
    })
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.tenant_cancel')}</div>
        </div>
      </div>

      {tenantCancelRequested ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message={(
            <Space>
              <Tag color="orange">{t('lbl.tenant_cancel.reserved')}{tenantCancelRequestedDt ? ` (${tenantCancelRequestedDt})` : ''}</Tag>
              <Button size="small" loading={undoMutation.isPending} onClick={handleUndo}>{t('btn.tenant_cancel.undo')}</Button>
            </Space>
          )}
        />
      ) : !canRequestCancel ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message={t('msg.tenant_cancel.precondition_banner')}
          action={(
            <Button size="small" onClick={() => openInTab('org/subscription-manage', '', t('ttl.tenant.manage.subscription'))}>
              {t('btn.tenant_cancel.go_to_subscriptions')}
            </Button>
          )}
        />
      ) : null}

      <div className="table-container">
        <table className="table table-bordered table-sm" style={{ tableLayout: 'fixed', width: '100%' }}>
          <thead>
            <tr>
              <th style={{ width: '25%' }}>{t('lbl.service_name_lbl')}</th>
              <th style={{ width: '40%' }}>{t('lbl.product')}</th>
              <th style={{ width: '35%' }} />
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={3} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
            ) : subscriptions.length === 0 ? (
              <tr><td colSpan={3} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
            ) : subscriptions.map((s) => (
              <tr key={s.servicecd}>
                <td>{serviceLabel(s.servicecd)}</td>
                <td>{s.productnm || '-'}</td>
                <td>
                  {s.servicestatus === 'Active' ? (
                    s.cancel_reserved ? (
                      <Tag color="orange">{t('lbl.pro.cancel.reserved')}{s.cancel_effective_date ? ` (${s.cancel_effective_date})` : ''}</Tag>
                    ) : (
                      <Tag color="red">{t('msg.tenant_cancel.services_not_cancelled')}</Tag>
                    )
                  ) : s.servicestatus ? (
                    <Tag>{s.servicestatus}</Tag>
                  ) : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ marginTop: 20, textAlign: 'right' }}>
        <Button
          danger
          disabled={!canRequestCancel || !!tenantCancelRequested}
          onClick={() => setModalOpen(true)}
        >
          {t('btn.tenant_cancel')}
        </Button>
      </div>

      <TenantCancelModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSubmit={handleSubmit}
        loading={requestMutation.isPending}
        reasonCodes={cancelReasonCodes}
      />
    </div>
  )
}
