import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useOpenInTab } from '@/hooks/useOpenInTab'
import {
  Button, Card, Col, Descriptions, Form, Input, Row, Select, Space, Table, Tag, Typography,
} from 'antd'
import { EditOutlined, LockOutlined, SaveOutlined } from '@ant-design/icons'
import { useMyInfo, useUpdateUsername, useUpdateTimezone, useMySubscriptions } from '@/hooks/useSettings'
import { useMfaFactors } from '@/hooks/useMfa'
import { useLangStore, t } from '@/stores/langStore'

const { Title } = Typography

export default function MyInfoPage() {
  useLangStore((s) => s.translations)
  const navigate = useNavigate()
  const openInTab = useOpenInTab()
  const { data = {}, isLoading } = useMyInfo()
  const updateUsername = useUpdateUsername()
  const updateTimezone = useUpdateTimezone()
  
  const { data: factorsData, isLoading: factorsLoading } = useMfaFactors()
  const { data: subsData, isLoading: subsLoading } = useMySubscriptions()
  const [editingName, setEditingName] = useState(false)
  const [editingTimezone, setEditingTimezone] = useState(false)
  const [timezoneVal, setTimezoneVal] = useState(null)
  const [form] = Form.useForm()

  const userInfo = data.user_info || {}
  const tenant = data.tenant || {}
  const tenantuser = data.tenantuser || {}
  const projectUsers = data.project_users || []
  const timezones = data.timezones || []
  const currentTimezone = data.timezone || null

  const isMfaEnabled = factorsData?.mfa_enabled ?? false
  const subscriptions = subsData?.subscriptions || []

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

        {/* 요금제 */}
        <Col span={12}>
          <Card
            size="small"
            title={t('ttl.myinfo.plan')}
            extra={<Button size="small" onClick={() => openInTab('tenant-subscription', '', t('ttl.tenant.subscription'))}>{t('ttl.tenant.subscription')}</Button>}
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
                    if (row.plancd === 'Fr') return (
                      <Button size="small" onClick={() => openInTab('upgrade', `?servicecd=${row.servicecd}&plancd=Pr`)}>{t('btn.upgrade.pro')}</Button>
                    )
                    return null
                  },
                },
              ]}
            />
          </Card>
        </Col>
      </Row>

      {/* 보안 설정 (MFA) ─────────────────────────────────────────────────── */}
      <Card
        size="small"
        title={t('ttl.myinfo.security')}
        loading={factorsLoading}
        style={{ marginBottom: 16 }}
      >
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
                  navigate('/settings/mfa')
                }}
              >
                {isMfaEnabled ? t('btn.mfa.manage') : t('ttl.mfa.setup')}
              </Button>
            </Space>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 약관 동의 여부 */}
      <Card size="small" title={t('ttl.myinfo.terms')} loading={isLoading} style={{ marginBottom: 16 }}>
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label={`${t('lbl.terms.service')} (${t('lbl.required')})`}>
            {isAgreed(userInfo.termsofuseyn) ? <Tag color="default">{t('lbl.agreed')}</Tag> : <Tag color="red">{t('lbl.not.agreed')}</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label={`${t('lbl.terms.privacy')} (${t('lbl.required')})`}>
            {isAgreed(userInfo.userinfoyn) ? <Tag color="default">{t('lbl.agreed')}</Tag> : <Tag color="red">{t('lbl.not.agreed')}</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label={`${t('lbl.terms.marketing')} (${t('lbl.optional')})`}>
            {isAgreed(userInfo.marketingyn) ? <Tag color="default">{t('lbl.agreed')}</Tag> : <Tag color="red">{t('lbl.not.agreed')}</Tag>}
          </Descriptions.Item>
        </Descriptions>
      </Card>

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

    </div>
  )
}