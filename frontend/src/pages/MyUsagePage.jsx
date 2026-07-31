import { useEffect, useState } from 'react'
import { Card, Col, DatePicker, Row, Segmented, Statistic, Table, Tag } from 'antd'
import dayjs from 'dayjs'
import { useMySubscriptions, useMyUsage } from '@/hooks/useSettings'
import { useMenuCodes } from '@/hooks/useMenus'
import { useLangStore, t } from '@/stores/langStore'

const { RangePicker } = DatePicker

export default function MyUsagePage() {
  useLangStore((s) => s.translations)
  const [dates, setDates] = useState([dayjs().subtract(29, 'day'), dayjs()])
  const [servicecd, setServicecd] = useState('Do')

  const { data: subsData = {} } = useMySubscriptions()
  const subscriptions = subsData.subscriptions || []

  const { data: serviceCodes = [] } = useMenuCodes('servicecd')
  const serviceLabel = (cd) => {
    const found = serviceCodes.find((c) => c.codevalue === cd)
    return found ? (t(found.term_key) || found.default_name) : cd
  }

  // 구독 목록이 로드되면, 현재 선택값이 구독하지 않은 서비스일 경우 첫 번째 구독 서비스로 보정
  useEffect(() => {
    if (subscriptions.length === 0) return
    if (!subscriptions.some((s) => s.servicecd === servicecd)) {
      setServicecd(subscriptions[0].servicecd)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subscriptions])

  const startDate = dates[0]?.format('YYYY-MM-DD')
  const endDate = dates[1]?.format('YYYY-MM-DD')
  const { data = {}, isLoading } = useMyUsage(startDate, endDate, servicecd)

  const totals = data.totals || { doc_count: 0, chapter_count: 0, object_count: 0, total: 0 }
  const daily = [...(data.daily || [])].sort((a, b) => b.date.localeCompare(a.date))
  const credit = data.credit
  const creditHistory = data.credit_history || []

  const { data: chargeCodes = [] } = useMenuCodes('creditchargecd')
  const chargeLabel = (cd) => {
    const found = chargeCodes.find((c) => c.codevalue === cd)
    return found ? (t(found.term_key) || found.default_name) : cd
  }

  const dailyColumns = [
    { title: t('thd.date_thd'), dataIndex: 'date', key: 'date' },
    { title: t('lbl.myusage.doc_count'), dataIndex: 'doc_count', key: 'doc_count', align: 'right' },
    { title: t('lbl.myusage.chapter_count'), dataIndex: 'chapter_count', key: 'chapter_count', align: 'right' },
    { title: t('lbl.myusage.object_count'), dataIndex: 'object_count', key: 'object_count', align: 'right' },
    { title: t('lbl.myusage.total'), dataIndex: 'total', key: 'total', align: 'right' },
  ]

  const bucketColumns = [
    { title: t('thd.creditchargecd_thd'), dataIndex: 'creditchargecd', key: 'creditchargecd', render: (v) => <Tag>{chargeLabel(v)}</Tag> },
    { title: t('lbl.myusage.credit.charge'), dataIndex: 'chargecredit', key: 'chargecredit', align: 'right' },
    { title: t('lbl.myusage.credit.used'), dataIndex: 'usecredit', key: 'usecredit', align: 'right' },
    { title: t('lbl.myusage.credit.remain'), dataIndex: 'remaincredit', key: 'remaincredit', align: 'right' },
    { title: t('lbl.expiresdts'), dataIndex: 'expiredts', key: 'expiredts' },
  ]

  const historyColumns = [
    { title: t('thd.date_thd'), dataIndex: 'date', key: 'date' },
    {
      title: t('thd.usetypecd_thd'), dataIndex: 'kind', key: 'kind',
      render: (v) => v === 'doc' ? t('lbl.doc') : v === 'chapter' ? t('lbl.chapter') : v === 'object' ? t('lbl.object') : v,
    },
    { title: t('lbl.name'), dataIndex: 'name', key: 'name', render: (v, r) => v || (r.kind === 'object' ? t('lbl.myusage.object_count') : v) },
    { title: t('thd.beforecredit_thd'), dataIndex: 'beforecredit', key: 'beforecredit', align: 'right' },
    { title: t('lbl.myusage.credit.used'), dataIndex: 'usecredit', key: 'usecredit', align: 'right' },
    { title: t('thd.aftercredit_thd'), dataIndex: 'aftercredit', key: 'aftercredit', align: 'right' },
  ]

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.myusage')}</div>
        </div>
      </div>

      {/* 서비스 선택 */}
      {subscriptions.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <Segmented
            value={servicecd}
            onChange={setServicecd}
            options={subscriptions.map((s) => ({ label: serviceLabel(s.servicecd), value: s.servicecd }))}
          />
        </div>
      )}

      {/* 크레딧 현황 (테넌트 공용) */}
      <Card size="small" title={t('ttl.myusage.credit')} loading={isLoading} style={{ marginBottom: 16 }}>
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={8}>
            <Statistic title={t('lbl.myusage.credit.charge')} value={credit?.total_charge ?? 0} />
          </Col>
          <Col span={8}>
            <Statistic title={t('lbl.myusage.credit.used')} value={credit?.total_use ?? 0} />
          </Col>
          <Col span={8}>
            <Statistic title={t('lbl.myusage.credit.remain')} value={credit?.total_remain ?? 0} />
          </Col>
        </Row>
        <Table
          size="small"
          columns={bucketColumns}
          dataSource={credit?.buckets || []}
          rowKey={(r, idx) => `${r.creditchargecd}-${idx}`}
          pagination={false}
          locale={{ emptyText: t('msg.no.data') }}
        />
      </Card>

      {/* 생성 활동 건수 / 크레딧 사용 내역 — 아직 Do(문서작성) 서비스에만 존재하는 개념 */}
      {servicecd === 'Do' && (
        <>
          {/* 기간 선택 + 생성 활동 건수 */}
          <div style={{ marginBottom: 16 }}>
            <RangePicker value={dates} onChange={(v) => v && setDates(v)} allowClear={false} />
          </div>

          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}>
              <Card size="small" loading={isLoading}>
                <Statistic title={t('lbl.myusage.doc_count')} value={totals.doc_count} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" loading={isLoading}>
                <Statistic title={t('lbl.myusage.chapter_count')} value={totals.chapter_count} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" loading={isLoading}>
                <Statistic title={t('lbl.myusage.object_count')} value={totals.object_count} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" loading={isLoading}>
                <Statistic title={t('lbl.myusage.total')} value={totals.total} />
              </Card>
            </Col>
          </Row>

          <Card size="small" title={t('ttl.myusage.daily')} loading={isLoading} style={{ marginBottom: 16 }}>
            <Table
              size="small"
              columns={dailyColumns}
              dataSource={daily}
              rowKey="date"
              pagination={{ pageSize: 15 }}
              locale={{ emptyText: t('msg.no.data') }}
            />
          </Card>

          {/* 본인 크레딧 사용 내역 — 선택 기간 내 본인이 생성한 문서/챕터로 인한 차감분만 */}
          <Card size="small" title={t('ttl.myusage.credit.history')} loading={isLoading}>
            <Table
              size="small"
              columns={historyColumns}
              dataSource={creditHistory}
              rowKey={(r, idx) => idx}
              pagination={{ pageSize: 10 }}
              locale={{ emptyText: t('msg.no.data') }}
            />
          </Card>
        </>
      )}
    </div>
  )
}
