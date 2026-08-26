import { useState } from 'react'
import { useOpenInTab } from '@/hooks/useOpenInTab'
import {
  App, Button, Card, Col, Descriptions, Form, Input, Modal, Popconfirm, Row, Select, Space, Switch, Table, Tag, Typography,
} from 'antd'
import { EditOutlined, LockOutlined, SaveOutlined } from '@ant-design/icons'
import {
  useMyInfo, useUpdateUsername, useUpdateTimezone, useUpdateMarketing, useMySubscriptions, useTenantManageOtherSubscriptions,
  useMyInfoCreditPurchase, useProCancel, useProCancelUndo,
} from '@/hooks/useSettings'
import { useMfaFactors } from '@/hooks/useMfa'
import { useMenuCodes } from '@/hooks/useMenus'
import { useLangStore, t } from '@/stores/langStore'

const { Title } = Typography

export default function MyInfoPage() {
  useLangStore((s) => s.translations)
  const { message } = App.useApp()
  const openInTab = useOpenInTab()
  const { data = {}, isLoading } = useMyInfo()
  const updateUsername = useUpdateUsername()
  const updateTimezone = useUpdateTimezone()
  const updateMarketing = useUpdateMarketing()

  const { data: factorsData, isLoading: factorsLoading } = useMfaFactors()
  const { data: subsData, isLoading: subsLoading } = useMySubscriptions()
  const { data: otherSubData } = useTenantManageOtherSubscriptions()
  const { data: cancelReasonCodes = [] } = useMenuCodes('cancel_reasoncd')
  const hasMfaFeature = (otherSubData?.owned || []).some((o) => o.productcd === 'mfa')
  const [editingName, setEditingName] = useState(false)
  const [editingTimezone, setEditingTimezone] = useState(false)
  const [timezoneVal, setTimezoneVal] = useState(null)
  const [form] = Form.useForm()

  const proCancelMutation = useProCancel()
  const proCancelUndoMutation = useProCancelUndo()
  const [cancelTarget, setCancelTarget] = useState(null)
  const [cancelReasonCd, setCancelReasonCd] = useState(null)
  const [cancelReasonDesc, setCancelReasonDesc] = useState('')

  const userInfo = data.user_info || {}
  const tenant = data.tenant || {}
  const tenantuser = data.tenantuser || {}
  const projectUsers = data.project_users || []
  const timezones = data.timezones || []
  const currentTimezone = data.timezone || null

  const isMfaEnabled = factorsData?.mfa_enabled ?? false
  const subscriptions = subsData?.subscriptions || []
  const isSystemTenant = tenant.issystemtenant === true

  // 크레딧 구매는 개인(시스템) 테넌트 전용 화면이라, 기업 테넌트에서는 애초에 요청하지 않는다
  // (백엔드가 403을 정상적으로 돌려주더라도, 전역 인터셉터가 GET 403마다 토스트를 띄우기 때문에
  //  기업 테넌트 사용자에게는 매번 에러 알림이 뜨는 문제가 있었다 — 2026-08-19).
  const { data: creditPurchaseData, isLoading: creditPurchaseLoading } = useMyInfoCreditPurchase(isSystemTenant)
  const ownedCredits = creditPurchaseData?.owned || []

  const isAgreed = (v) => v === 'Y' || v === true

  const handleEditName = () => {
    form.setFieldsValue({ usernm: userInfo.usernm || '' })
    setEditingName(true)
  }

  const handleSaveName = async () => {
    const values = await form.validateFields()
    updateUsername.mutate({ usernm: values.usernm }, { onSuccess: () => setEditingName(false) })
  }

  const handleEditTimezone = () => {
    setTimezoneVal(currentTimezone)
    setEditingTimezone(true)
  }

  const handleSaveTimezone = () => {
    updateTimezone.mutate({ timezone: timezoneVal }, { onSuccess: () => setEditingTimezone(false) })
  }

  const handleToggleMarketing = () => {
    updateMarketing.mutate({ marketingyn: isAgreed(userInfo.marketingyn) ? 'N' : 'Y' })
  }

  const handleProCancel = (servicecd) => {
    setCancelTarget(servicecd)
    setCancelReasonCd(null)
    setCancelReasonDesc('')
  }

  const handleProCancelSubmit = () => {
    if (!cancelReasonCd) { message.warning(t('msg.select.placeholder')); return }
    proCancelMutation.mutate(
      { servicecd: cancelTarget, cancel_reasoncd: cancelReasonCd, cancel_reasondesc: cancelReasonDesc || null },
      {
        onSuccess: () => { message.success(t('msg.subscription.cancel.reserved')); setCancelTarget(null) },
        onError: (err) => { message.error(err.response?.data?.detail || t('msg.save.error')) },
      },
    )
  }

  const handleProCancelUndo = (servicecd) => {
    proCancelUndoMutation.mutate(
      { servicecd },
      {
        onSuccess: () => { message.success(t('msg.subscription.cancel.undo.success')) },
        onError: (err) => { message.error(err.response?.data?.detail || t('msg.save.error')) },
      },
    )
  }

  const roleLabel = (v) => v === 'M' ? t('cod.rolecd_M') : v === 'U' ? t('cod.rolecd_U') : v || '-'

  const projectColumns = [
    { title: t('thd.projectnm_thd'), dataIndex: 'projectnm', key: 'projectnm' },
    { title: t('thd.rolecd_thd'), dataIndex: 'rolecd', key: 'rolecd', width: 100, render: roleLabel },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>{t('ttl.myinfo.personal')}</Title>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        {/* 개인 정보 */}
        <Col span={12}>
          <Card size="small" title={t('ttl.myinfo.personal')} loading={isLoading} style={{ height: '100%' }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label={t('lbl.email')}>{userInfo.email || '-'}</Descriptions.Item>
              <Descriptions.Item label={t('lbl.usernm')}>
                {editingName ? (
                  <Form form={form} layout="inline" size="small">
                    <Form.Item name="usernm" rules={[{ required: true }]} style={{ marginBottom: 0 }}>
                      <Input style={{ width: 160 }} />
                    </Form.Item>
                    <Space>
                      <Button size="small" type="primary" icon={<SaveOutlined />} loading={updateUsername.isPending} onClick={handleSaveName}>
                        {t('btn.save')}
                      </Button>
                      <Button size="small" onClick={() => setEditingName(false)}>{t('btn.cancel')}</Button>
                    </Space>
                  </Form>
                ) : (
                  <Space>
                    <span>{userInfo.usernm || '-'}</span>
                    <Button size="small" icon={<EditOutlined />} onClick={handleEditName} type="text" />
                  </Space>
                )}
              </Descriptions.Item>
              <Descriptions.Item label={t('lbl.timezone')}>
                {editingTimezone ? (
                  <Space>
                    <Select
                      value={timezoneVal}
                      onChange={setTimezoneVal}
                      style={{ width: 220 }}
                      size="small"
                      showSearch
                      options={timezones.map((tz) => ({ label: tz, value: tz }))}
                    />
                    <Button size="small" type="primary" icon={<SaveOutlined />} loading={updateTimezone.isPending} onClick={handleSaveTimezone}>
                      {t('btn.save')}
                    </Button>
                    <Button size="small" onClick={() => setEditingTimezone(false)}>{t('btn.cancel')}</Button>
                  </Space>
                ) : (
                  <Space>
                    <span>{currentTimezone || '-'}</span>
                    <Button size="small" icon={<EditOutlined />} onClick={handleEditTimezone} type="text" />
                  </Space>
                )}
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>

        {/* 약관 동의 여부 */}
        <Col span={12}>
          <Card size="small" title={t('ttl.myinfo.terms')} loading={isLoading} style={{ height: '100%' }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label={`${t('lbl.terms.privacy')} (${t('lbl.required')})`}>
                {isAgreed(userInfo.userinfoyn) ? <Tag color="default">{t('lbl.agreed')}</Tag> : <Tag color="red">{t('lbl.not.agreed')}</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label={`${t('lbl.terms.service')} (${t('lbl.required')})`}>
                {isAgreed(userInfo.termsofuseyn) ? <Tag color="default">{t('lbl.agreed')}</Tag> : <Tag color="red">{t('lbl.not.agreed')}</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label={`${t('lbl.terms.electronic')} (${t('lbl.required')})`}>
                {isAgreed(userInfo.electronicfinancialtermsyn) ? <Tag color="default">{t('lbl.agreed')}</Tag> : <Tag color="red">{t('lbl.not.agreed')}</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label={`${t('lbl.terms.marketing')} (${t('lbl.optional')})`}>
                <Popconfirm
                  title={t('msg.marketing.consent.confirm')}
                  okText={t('btn.confirm')}
                  cancelText={t('btn.cancel')}
                  onConfirm={handleToggleMarketing}
                  rootClassName="popconfirm-reverse-actions"
                >
                  <Switch
                    checked={isAgreed(userInfo.marketingyn)}
                    loading={updateMarketing.isPending}
                    checkedChildren={t('lbl.agreed')}
                    unCheckedChildren={t('lbl.not.agreed')}
                  />
                </Popconfirm>
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        {/* 요금제 */}
        <Col span={12}>
          <Card
            size="small"
            title={t('ttl.myinfo.plan')}
            extra={isSystemTenant ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Button size="small" onClick={() => openInTab('payment-manage', '', t('ttl.tenant.manage.payment'))}>{t('btn.payment.manage')}</Button>
                <span style={{ color: '#d9d9d9' }}>|</span>
                <Button size="small" onClick={() => openInTab('billing-history', '', t('ttl.tenant.manage.billing_history'))}>{t('ttl.tenant.manage.billing_history')}</Button>
                <span style={{ color: '#d9d9d9' }}>|</span>
                <Button size="small" onClick={() => openInTab('tenant-subscription', '', t('ttl.tenant.subscription'))}>{t('ttl.tenant.subscription')}</Button>
              </div>
            ) : null}
            loading={subsLoading}
            style={{ height: '100%' }}
          >
            <Table
              size="small"
              pagination={false}
              dataSource={subscriptions}
              rowKey="productcd"
              columns={[
                { title: t('lbl.product'), dataIndex: 'productnm', key: 'productnm' },
                {
                  title: t('lbl.upgrade'),
                  key: 'actions',
                  render: (_, row) => {
                    if (!isSystemTenant) return null
                    if (row.plancd === 'Fr') return (
                      <Button size="small" onClick={() => openInTab('upgrade', `?servicecd=${row.servicecd}&plancd=Pr`)}>{t('btn.upgrade.pro')}</Button>
                    )
                    if (row.cancel_reserved) return (
                      <Space size="small">
                        <Tag color="orange">{t('lbl.pro.cancel.reserved')}{row.cancel_effective_date ? ` (${row.cancel_effective_date})` : ''}</Tag>
                        <Button size="small" loading={proCancelUndoMutation.isPending} onClick={() => handleProCancelUndo(row.servicecd)}>{t('btn.pro.cancel.undo')}</Button>
                      </Space>
                    )
                    return (
                      <Button size="small" danger onClick={() => handleProCancel(row.servicecd)}>{t('btn.subscription.cancel')}</Button>
                    )
                  },
                },
              ]}
            />
          </Card>
        </Col>

        {/* 크레딧 구매 — 개인(시스템 테넌트) 계정 전용. 보유 내역만 여기 표시하고,
            실제 구매(상품 선택)는 요금제 카드의 '구독 관리'와 동일한 패턴으로 별도 페이지에서 진행 */}
        {isSystemTenant && (
          <Col span={12}>
            <Card
              size="small"
              title={t('ttl.myinfo.credit.purchase')}
              extra={<Button size="small" onClick={() => openInTab('credit-purchase', '', t('ttl.myinfo.credit.purchase'))}>{t('btn.purchase')}</Button>}
              loading={creditPurchaseLoading}
              style={{ height: '100%' }}
            >
              <Table
                size="small"
                pagination={false}
                dataSource={ownedCredits}
                rowKey="subscriptionuid"
                locale={{ emptyText: t('msg.no.data') }}
                columns={[
                  { title: t('lbl.product'), dataIndex: 'productnm', key: 'productnm' },
                  { title: t('lbl.credit'), dataIndex: 'quantity', key: 'quantity', align: 'right' },
                  { title: t('lbl.expiresdts'), dataIndex: 'expiresdts', key: 'expiresdts' },
                ]}
              />
            </Card>
          </Col>
        )}
      </Row>

      {/* 보안 설정 (MFA) — 현재 테넌트가 MFA 기능을 구독 중일 때만 노출 ───────── */}
      {hasMfaFeature && (
        <Card
          size="small"
          title={t('ttl.myinfo.security')}
          loading={factorsLoading}
          style={{ marginBottom: 16 }}
        >
          <div style={{ fontSize: 12, color: '#888', marginBottom: 8 }}>
            {t('msg.mfa.account_wide_notice')}
          </div>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label={t('ttl.mfa.status')}>
              <Space>
                {isMfaEnabled ? (
                  <Tag color="green">{t('btn.mfa.enable')}</Tag>
                ) : (
                  <Tag color="default">{t('btn.mfa.disable')}</Tag>
                )}
                <Button
                  htmlType="button"
                  size="small"
                  icon={<LockOutlined />}
                  onClick={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    openInTab('settings/mfa', '', t('ttl.mfa.setup'))
                  }}
                >
                  {isMfaEnabled ? t('btn.mfa.manage') : t('ttl.mfa.setup')}
                </Button>
              </Space>
            </Descriptions.Item>
          </Descriptions>
        </Card>
      )}

      {/* 소속 */}
      <Card size="small" title={t('ttl.myinfo.belong')} loading={isLoading} style={{ marginBottom: 16 }}>
        <Table
          columns={[
            {
              title: t('lbl.tenantnm'), dataIndex: 'tenantnm', key: 'tenantnm',
              onCell: (_, idx) => {
                if (idx === 0 || projectUsers[idx]?.tenantid !== projectUsers[idx - 1]?.tenantid)
                  return { rowSpan: projectUsers.filter(r => r.tenantid === projectUsers[idx]?.tenantid).length }
                return { rowSpan: 0 }
              },
              render: (v) => v || '-',
            },
            {
              title: t('lbl.myrole'), key: 'tenantrole', width: 100,
              onCell: (_, idx) => {
                if (idx === 0 || projectUsers[idx]?.tenantid !== projectUsers[idx - 1]?.tenantid)
                  return { rowSpan: projectUsers.filter(r => r.tenantid === projectUsers[idx]?.tenantid).length }
                return { rowSpan: 0 }
              },
              render: (_, row) => roleLabel(row.tenant_rolecd),
            },
            { title: t('thd.projectnm_thd'), dataIndex: 'projectnm', key: 'projectnm' },
            { title: t('thd.rolecd_thd'), dataIndex: 'rolecd', key: 'rolecd', width: 100, render: roleLabel },
          ]}
          dataSource={projectUsers.length > 0 ? projectUsers : [{ tenantnm: tenant.tenantnm, tenant_rolecd: tenantuser.rolecd }]}
          rowKey={(_, idx) => idx}
          size="small"
          pagination={false}
        />
      </Card>

      <Modal
        title={t('btn.subscription.cancel')}
        open={!!cancelTarget}
        onOk={handleProCancelSubmit}
        onCancel={() => setCancelTarget(null)}
        confirmLoading={proCancelMutation.isPending}
        okType="danger"
      >
        <div style={{ marginBottom: 12, color: '#888', fontSize: 12 }}>{t('inf.pro.cancel.notice')}</div>
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
    </div>
  )
}