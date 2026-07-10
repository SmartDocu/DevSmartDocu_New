import { App, Button, Card, Row, Col, Table, Tag } from 'antd'
import { CreditCardOutlined, HistoryOutlined } from '@ant-design/icons'
import { useLangStore, t } from '@/stores/langStore'
import { useOpenInTab } from '@/hooks/useOpenInTab'
import { useTenantManageSubscriptions } from '@/hooks/useSettings'
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

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('mnu.tenant_mgr.manage.overview')}</div>
        </div>
      </div>

      <Row gutter={20} style={{ marginBottom: 20, paddingRight: 10 }}>
        {/* 제품 구독 관리: 상단 좌측 제목 / 상단 우측 이동 버튼, 하단 구독 리스트 */}
        <Col span={12}>
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
              locale={{ emptyText: t('msg.no.data') }}
              columns={[
                { title: t('lbl.product'), dataIndex: 'productnm', key: 'productnm' },
                { title: t('lbl.plan'), key: 'plancd', render: (_, row) => planLabel(row.plancd) },
              ]}
            />
          </Card>
        </Col>

        <Col span={12}>
          <PlaceholderCard icon={<HistoryOutlined />} titleKey="ttl.tenant.manage.billing_history" onClick={comingSoon} />
        </Col>
      </Row>

      <Row gutter={20} style={{ paddingRight: 10 }}>
        <Col span={24}>
          <PlaceholderCard icon={<CreditCardOutlined />} titleKey="ttl.tenant.manage.payment" onClick={comingSoon} />
        </Col>
      </Row>
    </div>
  )
}
