import { Button, Card, Row, Col, Table } from 'antd'
import { CreditCardOutlined, HistoryOutlined } from '@ant-design/icons'
import { useLangStore, t } from '@/stores/langStore'
import { useOpenInTab } from '@/hooks/useOpenInTab'
import {
  useTenantManageSubscriptions,
  useTenantManageTenantInfo,
  useTenantManageOverview,
} from '@/hooks/useSettings'
import { useMenuCodes } from '@/hooks/useMenus'

function NavCard({ icon, titleKey, routePath, openInTab }) {
  return (
    <Card
      hoverable
      onClick={() => openInTab(routePath, '', t(titleKey))}
      style={{ textAlign: 'center', height: '100%' }}
    >
      <div style={{ fontSize: 32, color: '#163E64', marginBottom: 12 }}>{icon}</div>
      <div style={{ fontWeight: 600, marginBottom: 8 }}>{t(titleKey)}</div>
    </Card>
  )
}

function PaymentCard({ openInTab }) {
  return (
    <Card
      hoverable
      onClick={() => openInTab('org/payment-manage', '', t('ttl.tenant.manage.payment'))}
      style={{ textAlign: 'center', height: '100%' }}
    >
      <div style={{ fontSize: 32, color: '#163E64', marginBottom: 12 }}><CreditCardOutlined /></div>
      <div style={{ fontWeight: 600, marginBottom: 8 }}>{t('ttl.tenant.manage.payment')}</div>
    </Card>
  )
}

function TenantInfoCard({ openInTab }) {
  const { data = {}, isLoading } = useTenantManageTenantInfo()

  return (
    <Card
      size="small"
      title={t('ttl.tenant.manage.tenant_info')}
      extra={(
        <Button
          size="small"
          onClick={() => openInTab('org/tenant-basic-info', '', t('ttl.tenant.manage.basic_info'))}
        >
          {t('btn.setting')}
        </Button>
      )}
      loading={isLoading}
      style={{ height: '100%' }}
    >
      <div style={{ border: '1px solid #f0f0f0', borderBottom: 'none', fontSize: 12 }}>
        {[
          [t('lbl.disptenantnm'), data.disptenantnm],
          [t('lbl.email'), data.email],
          [t('lbl.telno'), data.telno],
          [t('thd.languagenm'), data.languagenm || data.languagecd],
          [t('lbl.timezone'), data.timezone],
          [t('lbl.tenant.manage.ip_whitelist'), data.is_whitelist_subscribed ? t('lbl.service.subscribed') : t('lbl.service.not_subscribed')],
        ].map(([label, value]) => (
          <div key={label} style={{ display: 'flex', borderBottom: '1px solid #f0f0f0' }}>
            <div style={{ flex: '0 0 90px', padding: '6px 8px', background: '#fafafa', borderRight: '1px solid #f0f0f0' }}>
              {label}
            </div>
            <div
              title={value || ''}
              style={{ flex: '1 1 0', minWidth: 0, padding: '6px 8px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            >
              {value || '-'}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

export default function OrgTenantManagePage() {
  useLangStore((s) => s.translations)
  const openInTab = useOpenInTab()

  const { data: subData = {}, isLoading: subsLoading } = useTenantManageSubscriptions()
  const subscriptions = (subData.subscriptions || []).filter((s) => !!s.productcd)
  const { data: planCodes = [] } = useMenuCodes('plancd')
  const planLabel = (cd) => {
    const found = planCodes.find((c) => c.codevalue === cd)
    return found ? (t(found.term_key) || found.default_name) : cd
  }

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

      <Row gutter={20} wrap={false} style={{ marginBottom: 20, paddingRight: 10 }}>
        {/* 테넌트 정보: 담당자 연락처 + 언어·타임존 (표시 전용, 수정은 별도 페이지) */}
        <Col flex="30 1 0" style={{ minWidth: 0 }}>
          <TenantInfoCard openInTab={openInTab} />
        </Col>

        {/* 구독 통합 카드: 구독 + 기타 구독 + 크레딧 영역 통합 */}
        <Col flex="70 1 0" style={{ minWidth: 0 }}>
          <Card
            size="small"
            title={t('ttl.tenant.manage.subscription')}
            extra={(
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Button
                  size="small"
                  onClick={() => openInTab('org/other-subscription-manage', '', t('ttl.tenant.manage.other_subscription'))}
                >
                  {t('btn.other.manage')}
                </Button>
                <span style={{ color: '#d9d9d9' }}>|</span>
                <Button
                  size="small"
                  onClick={() => openInTab('org/subscription-manage', '', t('ttl.tenant.manage.subscription'))}
                >
                  {t('btn.product.manage')}
                </Button>
              </div>
            )}
            style={{ height: '100%' }}
          >
            <Table
              size="small"
              pagination={false}
              loading={subsLoading}
              dataSource={subscriptions}
              rowKey="servicecd"
              locale={{ emptyText: t('msg.no.data') }}
              columns={[
                { title: t('lbl.product'), dataIndex: 'productnm', key: 'productnm' },
                { title: t('lbl.plan'), key: 'plancd', render: (_, row) => planLabel(row.plancd) },
                { title: t('thd.included_users_thd'), dataIndex: 'included_users', key: 'included_users', align: 'center' },
                { title: t('thd.add_users_thd'), dataIndex: 'add_users', key: 'add_users', align: 'center' },
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
            extra={(
              <Button
                size="small"
                onClick={() => openInTab('org/credit-manage', '', t('ttl.tenant.manage.credit'))}
              >
                {t('btn.credit.manage')}
              </Button>
            )}
            loading={overviewLoading}
          >
            <Table
              size="small"
              pagination={false}
              dataSource={serviceOverviews}
              rowKey="servicecd"
              locale={{ emptyText: t('msg.no.data') }}
              columns={[
                { title: t('lbl.service_name_lbl'), key: 'servicecd', render: (_, row) => serviceLabel(row.servicecd) },
                { title: t('thd.project_count_thd'), dataIndex: 'projects', key: 'projects' },
                { title: t('thd.total_users_thd'), dataIndex: 'total_users', key: 'total_users' },
                { title: t('thd.used_users_thd'), dataIndex: 'used_users', key: 'used_users' },
                { title: t('thd.total_credit_thd'), dataIndex: 'total_credit', key: 'total_credit', render: (v) => Number(v || 0).toLocaleString() },
                { title: t('thd.used_credit_thd'), dataIndex: 'used_credit', key: 'used_credit', render: (v) => Number(v || 0).toLocaleString() },
                { title: t('thd.remain_credit_thd'), dataIndex: 'remain_credit', key: 'remain_credit', render: (v) => Number(v || 0).toLocaleString() },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={20} style={{ paddingRight: 10 }}>
        <Col span={12}>
          <NavCard icon={<HistoryOutlined />} titleKey="ttl.tenant.manage.billing_history" routePath="org/billing-history" openInTab={openInTab} />
        </Col>
        <Col span={12}>
          <PaymentCard openInTab={openInTab} />
        </Col>
      </Row>
    </div>
  )
}
