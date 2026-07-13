import { useEffect, useState } from 'react'
import { App, Button, Card, Row, Col, Table, Tag, Descriptions, Select } from 'antd'
import { CreditCardOutlined, HistoryOutlined } from '@ant-design/icons'
import { useLangStore, t } from '@/stores/langStore'
import { useOpenInTab } from '@/hooks/useOpenInTab'
import {
  useTenantManageSubscriptions,
  useTenantManageLangTimezone,
  useSaveTenantManageLangTimezone,
  useTenantManageOtherSubscriptions,
  useTenantManageCreditSubscriptions,
  useTenantManageOverview,
} from '@/hooks/useSettings'
import { useMenuCodes } from '@/hooks/useMenus'

function PlaceholderCard({ icon, titleKey, onClick }) {
  return (
    <Card hoverable onClick={onClick} style={{ textAlign: 'center', height: '100%' }}>
      <div style={{ fontSize: 32, color: '#163E64', marginBottom: 12 }}>{icon}</div>
      <div style={{ fontWeight: 600, marginBottom: 8 }}>{t(titleKey)}</div>
      <Tag>{t('msg.coming.soon')}</Tag>
    </Card>
  )
}

function TenantLangTimezoneCard() {
  const { message } = App.useApp()
  const { data = {}, isLoading } = useTenantManageLangTimezone()
  const saveMutation = useSaveTenantManageLangTimezone()

  const [languagecd, setLanguagecd] = useState(null)
  const [timezoneVal, setTimezoneVal] = useState(null)

  useEffect(() => {
    setLanguagecd(data.languagecd || null)
    setTimezoneVal(data.timezone || null)
  }, [data.languagecd, data.timezone])

  const languages = data.languages || []
  const timezones = data.timezones || []

  const handleSave = () => {
    saveMutation.mutate(
      { languagecd, timezone: timezoneVal },
      {
        onSuccess: () => { message.success(t('msg.save.success')) },
        onError: (err) => { message.error(err.response?.data?.detail || t('msg.save.error')) },
      },
    )
  }

  return (
    <Card
      size="small"
      title={t('ttl.tenant.manage.lang_timezone')}
      extra={(
        <Button size="small" type="primary" loading={saveMutation.isPending} onClick={handleSave}>
          {t('btn.save')}
        </Button>
      )}
      loading={isLoading}
      style={{ height: '100%' }}
    >
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label={t('thd.languagenm')}>
          <Select
            value={languagecd}
            onChange={setLanguagecd}
            style={{ width: '100%' }}
            size="small"
            options={languages.map((l) => ({ label: l.languagenm, value: l.languagecd }))}
          />
        </Descriptions.Item>
        <Descriptions.Item label={t('lbl.timezone')}>
          <Select
            value={timezoneVal}
            onChange={setTimezoneVal}
            style={{ width: '100%' }}
            size="small"
            showSearch
            options={timezones.map((tz) => ({ label: tz, value: tz }))}
          />
        </Descriptions.Item>
      </Descriptions>
    </Card>
  )
}

export default function OrgTenantManagePage() {
  const { message } = App.useApp()
  useLangStore((s) => s.translations)
  const openInTab = useOpenInTab()

  const comingSoon = () => { message.info(t('msg.coming.soon')) }

  const { data: subData = {}, isLoading: subsLoading } = useTenantManageSubscriptions()
  const subscriptions = (subData.subscriptions || []).filter((s) => !!s.productcd)
  const { data: planCodes = [] } = useMenuCodes('plancd')
  const planLabel = (cd) => {
    const found = planCodes.find((c) => c.codevalue === cd)
    return found ? (t(found.term_key) || found.default_name) : cd
  }

  const { data: otherSubData = {}, isLoading: otherSubsLoading } = useTenantManageOtherSubscriptions()
  const otherOwned = otherSubData.owned || []

  const { data: creditSubData = {}, isLoading: creditSubsLoading } = useTenantManageCreditSubscriptions()
  const creditOwned = creditSubData.owned || []

  const { data: overviewData = {}, isLoading: overviewLoading } = useTenantManageOverview()
  const serviceOverviews = overviewData.services || []
  const { data: serviceCodes = [] } = useMenuCodes('servicecd')
  const serviceLabel = (cd) => {
    const found = serviceCodes.find((c) => c.codevalue === cd)
    return found ? (t(found.term_key) || found.default_name) : cd
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('mnu.tenant_mgr.manage.overview')}</div>
        </div>
      </div>

      <Row gutter={20} style={{ marginBottom: 20, paddingRight: 10 }}>
        {/* 언어 정보 & 타임존 설정: 테넌트 전체 기본값 */}
        <Col flex="20 1 0">
          <TenantLangTimezoneCard />
        </Col>

        {/* 제품 구독 관리: 상단 좌측 제목 / 상단 우측 이동 버튼, 하단 구독 리스트 */}
        <Col flex="20 1 0">
          <Card
            size="small"
            title={t('ttl.tenant.manage.subscription')}
            extra={(
              <Button
                size="small"
                onClick={() => openInTab('org/subscription-manage', '', t('ttl.tenant.manage.subscription'))}
              >
                {t('btn.subscription.manage')}
              </Button>
            )}
            style={{ height: '100%' }}
          >
            <Table
              size="small"
              pagination={false}
              loading={subsLoading}
              dataSource={subscriptions}
              rowKey="servicecd"
              scroll={{ y: 195 }}
              locale={{ emptyText: t('msg.no.data') }}
              columns={[
                { title: t('lbl.product'), dataIndex: 'productnm', key: 'productnm' },
                { title: t('lbl.plan'), key: 'plancd', render: (_, row) => planLabel(row.plancd) },
              ]}
            />
          </Card>
        </Col>

        {/* 기타 구독 정보: User/Feature 상품 보유 현황 */}
        <Col flex="20 1 0">
          <Card
            size="small"
            title={t('ttl.tenant.manage.other_subscription')}
            extra={(
              <Button
                size="small"
                onClick={() => openInTab('org/other-subscription-manage', '', t('ttl.tenant.manage.other_subscription'))}
              >
                {t('btn.subscription.manage')}
              </Button>
            )}
            style={{ height: '100%' }}
          >
            <Table
              size="small"
              pagination={false}
              loading={otherSubsLoading}
              dataSource={otherOwned}
              rowKey="subscriptionuid"
              scroll={{ y: 195 }}
              locale={{ emptyText: t('msg.no.data') }}
              columns={[
                { title: t('lbl.product'), dataIndex: 'productnm', key: 'productnm' },
              ]}
            />
          </Card>
        </Col>

        {/* 크레딧 구매 내역 */}
        <Col flex="40 1 0">
          <Card
            size="small"
            title={t('ttl.tenant.manage.credit')}
            extra={(
              <Button
                size="small"
                onClick={() => openInTab('org/credit-manage', '', t('ttl.tenant.manage.credit'))}
              >
                {t('btn.subscription.manage')}
              </Button>
            )}
            style={{ height: '100%' }}
          >
            <Table
              size="small"
              pagination={false}
              loading={creditSubsLoading}
              dataSource={creditOwned}
              rowKey="subscriptionuid"
              scroll={{ y: 195 }}
              locale={{ emptyText: t('msg.no.data') }}
              columns={[
                { title: t('lbl.product'), dataIndex: 'productnm', key: 'productnm' },
                { title: t('lbl.credit'), dataIndex: 'quantity', key: 'quantity' },
              ]}
            />
          </Card>
        </Col>
      </Row>

      {/* 전체 현황: 서비스별 프로젝트/인원/크레딧 현황 */}
      <Row gutter={20} style={{ marginBottom: 20, paddingRight: 10 }}>
        <Col span={24}>
          <Card
            size="small"
            title={t('ttl.tenant.manage.overview.services')}
            extra={<span>{t('lbl.current.user.count')}: {overviewData.total_users ?? 0}</span>}
            loading={overviewLoading}
          >
            <Table
              size="small"
              pagination={false}
              dataSource={serviceOverviews}
              rowKey="servicecd"
              scroll={{ y: 195 }}
              locale={{ emptyText: t('msg.no.data') }}
              columns={[
                { title: t('lbl.service_name_lbl'), key: 'servicecd', render: (_, row) => serviceLabel(row.servicecd) },
                { title: t('thd.project_count_thd'), dataIndex: 'projects', key: 'projects' },
                { title: t('thd.total_users_thd'), dataIndex: 'total_users', key: 'total_users' },
                { title: t('thd.used_users_thd'), dataIndex: 'used_users', key: 'used_users' },
                { title: t('thd.total_credit_thd'), dataIndex: 'total_credit', key: 'total_credit' },
                { title: t('thd.used_credit_thd'), dataIndex: 'used_credit', key: 'used_credit' },
                { title: t('thd.remain_credit_thd'), dataIndex: 'remain_credit', key: 'remain_credit' },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={20} style={{ paddingRight: 10 }}>
        <Col span={12}>
          <PlaceholderCard icon={<HistoryOutlined />} titleKey="ttl.tenant.manage.billing_history" onClick={comingSoon} />
        </Col>
        <Col span={12}>
          <PlaceholderCard icon={<CreditCardOutlined />} titleKey="ttl.tenant.manage.payment" onClick={comingSoon} />
        </Col>
      </Row>
    </div>
  )
}
