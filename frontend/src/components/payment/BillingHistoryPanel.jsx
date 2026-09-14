import { useEffect, useState } from 'react'
import { DatePicker, Pagination, Table, Tag } from 'antd'
import dayjs from 'dayjs'
import { t } from '@/stores/langStore'
import { useMenuCodes } from '@/hooks/useMenus'
import { usePaymentHistory } from '@/hooks/usePayments'

const { RangePicker } = DatePicker
const PAGE_SIZE = 10

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
  const hasExpandableRows = payments.some((p) => Array.isArray(p.items) && p.items.length > 0)

  const [page, setPage] = useState(1)
  useEffect(() => { setPage(1) }, [startDate, endDate])
  const pagedPayments = payments.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const { data: statusCodes = [] } = useMenuCodes('payment_status')
  const statusLabel = (cd) => {
    const found = statusCodes.find((c) => c.codevalue === cd)
    return found ? (t(found.term_key) || found.default_name) : cd
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{pageTitle}</div>
        </div>
      </div>

      <div className="panel-section" style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
        <div className="filter-item">
          <label style={{ fontWeight: 'bold' }}>{t('lbl.period')}</label>
          <RangePicker value={dates} onChange={(v) => v && setDates(v)} allowClear={false} />
        </div>
      </div>

      <div className="panel-section" style={{ height: 'calc(100vh - 306px)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <Table
          size="small"
          loading={isLoading}
          pagination={false}
          dataSource={pagedPayments}
          rowKey="paymentuid"
          locale={{ emptyText: t('msg.no.data') }}
          expandable={!hasExpandableRows ? undefined : {
            rowExpandable: (r) => Array.isArray(r.items) && r.items.length > 0,
            expandedRowRender: (r) => (
              <table className="table table-sm table-bordered" style={{ marginBottom: 0 }}>
                <thead>
                  <tr>
                    <th>{t('thd.product_thd')}</th>
                    <th style={{ width: 100, textAlign: 'center' }}>{t('thd.quantity_thd')}</th>
                    <th style={{ width: 160, textAlign: 'right' }}>{t('thd.amount_thd')}</th>
                  </tr>
                </thead>
                <tbody>
                  {r.items.map((it, idx) => (
                    <tr key={idx}>
                      <td>{it.desc || it.productcd}</td>
                      <td style={{ textAlign: 'center' }}>{it.quantity}</td>
                      <td style={{ textAlign: 'right' }}>{Number(it.amount).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ),
          }}
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
        <div style={{ marginTop: 'auto', paddingTop: 12, display: 'flex', justifyContent: 'center' }}>
          <Pagination
            current={page}
            pageSize={PAGE_SIZE}
            total={payments.length}
            showSizeChanger={false}
            onChange={setPage}
          />
        </div>
      </div>
    </div>
  )
}
