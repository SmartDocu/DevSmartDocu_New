import { useState } from 'react'
import {
  Button, Card, Col, Descriptions, Form, Input, Row, Space, Table, Tag, Typography,
} from 'antd'
import { EditOutlined, SaveOutlined } from '@ant-design/icons'
import { useMyInfo, useUpdateUsername } from '@/hooks/useSettings'

const { Title } = Typography

const BILLING_LABELS = { Fr: 'Free', Pr: 'Pro', Te: 'Teams', En: 'Enterprise' }
const BILLING_COLORS = { Fr: 'default', Pr: 'blue', Te: 'green', En: 'gold' }
const ROLE_LABELS = { M: '관리자', U: '사용자' }

export default function MyInfoPage() {
  const { data = {}, isLoading } = useMyInfo()
  const updateUsername = useUpdateUsername()
  const [editingName, setEditingName] = useState(false)
  const [form] = Form.useForm()

  const userInfo = data.user_info || {}
  const tenant = data.tenant || {}
  const tenantuser = data.tenantuser || {}
  const projectUsers = data.project_users || []

  const handleEditName = () => {
    form.setFieldsValue({ usernm: userInfo.usernm || '' })
    setEditingName(true)
  }

  const handleSaveName = async () => {
    const values = await form.validateFields()
    updateUsername.mutate({ usernm: values.usernm }, { onSuccess: () => setEditingName(false) })
  }

  const projectColumns = [
    { title: '프로젝트명', dataIndex: 'projectnm', key: 'projectnm' },
    {
      title: '역할',
      dataIndex: 'rolecd',
      key: 'rolecd',
      width: 100,
      render: (v) => ROLE_LABELS[v] || v || '-',
    },
    {
      title: '사용',
      dataIndex: 'useyn',
      key: 'useyn',
      width: 70,
      align: 'center',
      render: (v) => v ? '✔' : '',
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>My Page</Title>

      <Row gutter={16}>
        {/* 개인 정보 */}
        <Col span={12}>
          <Card size="small" title="개인 정보" loading={isLoading} style={{ marginBottom: 16 }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="Email">{userInfo.email || '-'}</Descriptions.Item>
              <Descriptions.Item label="사용자명">
                {editingName ? (
                  <Form form={form} layout="inline" size="small">
                    <Form.Item name="usernm" rules={[{ required: true }]} style={{ marginBottom: 0 }}>
                      <Input style={{ width: 160 }} />
                    </Form.Item>
                    <Space>
                      <Button size="small" type="primary" icon={<SaveOutlined />} loading={updateUsername.isPending} onClick={handleSaveName}>
                        저장
                      </Button>
                      <Button size="small" onClick={() => setEditingName(false)}>취소</Button>
                    </Space>
                  </Form>
                ) : (
                  <Space>
                    <span>{userInfo.usernm || '-'}</span>
                    <Button size="small" icon={<EditOutlined />} onClick={handleEditName} type="text" />
                  </Space>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="요금제">
                <Tag color={BILLING_COLORS[userInfo.billingmodelcd] || 'default'}>
                  {BILLING_LABELS[userInfo.billingmodelcd] || userInfo.billingmodelcd || '-'}
                </Tag>
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>

        {/* 기업(테넌트) 정보 */}
        <Col span={12}>
          <Card size="small" title="기업 정보" loading={isLoading} style={{ marginBottom: 16 }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="기업명">{tenant.tenantnm || '-'}</Descriptions.Item>
              <Descriptions.Item label="요금제">
                <Tag color={BILLING_COLORS[tenant.billingmodelcd] || 'default'}>
                  {BILLING_LABELS[tenant.billingmodelcd] || tenant.billingmodelcd || '-'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="내 역할">
                {ROLE_LABELS[tenantuser.rolecd] || tenantuser.rolecd || '-'}
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
      </Row>

      {/* 프로젝트 목록 */}
      <Card size="small" title="소속 프로젝트" loading={isLoading}>
        <Table
          columns={projectColumns}
          dataSource={projectUsers}
          rowKey={(row) => row.projectid || Math.random()}
          size="small"
          pagination={false}
        />
      </Card>
    </div>
  )
}
