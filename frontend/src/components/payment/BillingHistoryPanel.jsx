import { useState } from 'react'
import { DatePicker, Table, Tag } from 'antd'
import dayjs from 'dayjs'
import { t } from '@/stores/langStore'
import { useMenuCodes } from '@/hooks/useMenus'
import { usePaymentHistory } from '@/hooks/usePayments'

const { RangePicker } = DatePicker

const STATUS_COLORS = {
  Success: 'green',
  Pending: 'blue',
  Processing: 'blue',
  Failed: 'red',
  Refunded: 'orange',
  Partial_Refunded: 'orange',
  VOID: 'default',
}

/**
 * 결제 이력 조회 공용 패널. 기업(org/billing-history)과 개인(billing-history) 화면이 공유한다
 * (PaymentManagePanel.jsx와 동일 패턴) — 백엔드 /payments/history가 기업/개인 계정을 함께 처리한다.
 */
export default function BillingHistoryPanel({ pageTitle }) {
  const [dates, setDates] = useState([dayjs().subtract(1, 'month'), dayjs()])
  const startDate = dates[0]?.format('YYYY-MM-DD')
  const endDate = dates[1]?.format('YYYY-MM-DD')

  const { data = {}, isLoading } = usePaymentHistory(startDate, endDate)
  const payments = data.payments || []

  const { data: statusCodes = [] } = useMenuCodes('payment_status')
  const statusLabel = (cd) => {
    const found = statusCodes.find((c) => c.codevalue === cd)
    return found ? (t(found.term_key) || found.default_name) : cd
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{pageTitle}</div>
        </div>
      </div>

      <div style={{ marginBottom: 12 }}>
        <RangePicker value={dates} onChange={(v) => v && setDates(v)} allowClear={false} />
      </div>

      <Table
        size="small"
        loading={isLoading}
        pagination={false}
        dataSource={payments}
        rowKey="paymentuid"
        locale={{ emptyText: t('msg.no.data') }}
        columns={[
          { title: t('thd.createdts_thd'), dataIndex: 'createdts', key: 'createdts', width: 160 },
          { title: t('thd.product_thd'), key: 'productnm', render: (_, r) => r.productnm || r.productcd || '-' },
          { title: t('thd.quantity_thd'), dataIndex: 'quantity', key: 'quantity', width: 100, align: 'center', render: (v) => v ?? '-' },
          {
            title: t('thd.amount_thd'), key: 'amount', width: 160, align: 'right',
            render: (_, r) => `${Number(r.payment_amount).toLocaleString()} ${r.currencycd || ''}`,
          },
          {
            title: t('thd.payment_status_thd'), dataIndex: 'payment_status', key: 'payment_status', width: 120, align: 'center',
            render: (v) => <Tag color={STATUS_COLORS[v] || 'default'}>{statusLabel(v)}</Tag>,
          },
        ]}
      />
    </div>
  )
}
