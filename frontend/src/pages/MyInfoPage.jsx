import { useState } from 'react'
import {
  Button, Card, Col, Descriptions, Form, Input, Row, Space, Table, Tag, Typography, Alert,
} from 'antd'
import { EditOutlined, SaveOutlined } from '@ant-design/icons'
import { useMyInfo, useUpdateUsername } from '@/hooks/useSettings'
import { useLangStore, t } from '@/stores/langStore'

const { Title } = Typography

const BILLING_LABELS = { Fr: 'Free', Pr: 'Pro', Te: 'Teams', En: 'Enterprise' }
const BILLING_COLORS = { Fr: 'default', Pr: 'blue', Te: 'green', En: 'gold' }
const APPROVE_LABELS = { A: '대기중', D: '승인 거절' }

export default function MyInfoPage() {
  useLangStore((s) => s.translations)
  const { data = {}, isLoading } = useMyInfo()
  const updateUsername = useUpdateUsername()
  const [editingName, setEditingName] = useState(false)
  const [form] = Form.useForm()

  const userInfo = data.user_info || {}
  const tenant = data.tenant || {}
  const tenantuser = data.tenantuser || {}
  const projectUsers = data.project_users || []
  const tenantChange = data.tenant_change || null

  const isAgreed = (v) => v === 'Y' || v === true

  const handleEditName = () => {
    form.setFieldsValue({ usernm: userInfo.usernm || '' })
    setEditingName(true)
  }

  const handleSaveName = async () => {
    const values = await form.validateFields()
    updateUsername.mutate({ usernm: values.usernm }, { onSuccess: () => setEditingName(false) })
  }

  const projectColumns = [
    { title: t('thd.projectnm_thd'), dataIndex: 'projectnm', key: 'projectnm' },
    {
      title: t('thd.rolecd_thd'),
      dataIndex: 'rolecd',
      key: 'rolecd',
      width: 100,
      render: (v) => v === 'M' ? 'Manager' : v === 'U' ? 'User' : v || '-',
    },
  ]

  const createdts = tenant.createdts
    ? new Date(tenant.createdts).toLocaleDateString()
    : '-'

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>My Page</Title>

      <Row gutter={16}>
        {/* 개인 정보 */}
        <Col span={12}>
          <Card size="small" title={t('ttl.myinfo.personal')} loading={isLoading} style={{ marginBottom: 16 }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="Email">{userInfo.email || '-'}</Descriptions.Item>
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
              <Descriptions.Item label={t('lbl.plan')}>
                <Space>
                  <Tag color={BILLING_COLORS[userInfo.billingmodelcd] || 'default'}>
                    {BILLING_LABELS[userInfo.billingmodelcd] || userInfo.billingmodelcd || '-'}
                  </Tag>
                  {userInfo.billingmodelcd === 'Fr' && (
                    <Button size="small" type="primary" onClick={() => alert(t('msg.preparing'))}>
                      {t('btn.upgrade')}
                    </Button>
                  )}
                </Space>
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>

        {/* 기업(테넌트) 정보 */}
        <Col span={12}>
          <Card size="small" title={t('ttl.myinfo.tenant')} loading={isLoading} style={{ marginBottom: 16 }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label={t('lbl.tenantnm')}>{tenant.tenantnm || '-'}</Descriptions.Item>
              <Descriptions.Item label={t('lbl.myrole')}>
                {tenantuser.rolecd === 'M' ? 'Manager' : tenantuser.rolecd === 'U' ? 'User' : tenantuser.rolecd || '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('lbl.joindt')}>{createdts}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
      </Row>

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

      {/* 소속 프로젝트 */}
      <Card size="small" title={t('ttl.myinfo.projects')} loading={isLoading} style={{ marginBottom: 16 }}>
        <Table
          columns={projectColumns}
          dataSource={projectUsers}
          rowKey={(row) => row.projectid || Math.random()}
          size="small"
          pagination={false}
        />
      </Card>

      {/* 기업 변경 이력 */}
      <Card size="small" title={t('ttl.myinfo.tenant.history')} loading={isLoading}>
        {tenantChange ? (
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label={t('lbl.tenantnm')}>{tenantChange.tenantnm || '-'}</Descriptions.Item>
            <Descriptions.Item label={t('lbl.status')}>
              {APPROVE_LABELS[tenantChange.approvecd] || tenantChange.approvecd || '-'}
            </Descriptions.Item>
            <Descriptions.Item label={t('lbl.note')}>
              {tenantChange.approvecd === 'D' ? tenantChange.approvenote || '-' : '-'}
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <span style={{ color: '#aaa', fontSize: 13 }}>{t('msg.no.change.history')}</span>
        )}
      </Card>
    </div>
  )
}
