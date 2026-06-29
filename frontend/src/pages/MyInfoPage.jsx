import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Button, Card, Col, Descriptions, Form, Input, Row, Select, Space, Table, Tag, Typography, Alert,
} from 'antd'
import { EditOutlined, LockOutlined, SaveOutlined } from '@ant-design/icons'
import { useMyInfo, useUpdateUsername, useUpdateTimezone } from '@/hooks/useSettings'
import { useMfaFactors } from '@/hooks/useMfa'
import { useLangStore, t } from '@/stores/langStore'

const { Title } = Typography

export default function MyInfoPage() {
  useLangStore((s) => s.translations)
  const navigate = useNavigate()
  const { data = {}, isLoading } = useMyInfo()
  const updateUsername = useUpdateUsername()
  const updateTimezone = useUpdateTimezone()
  
  const { data: factorsData, isLoading: factorsLoading } = useMfaFactors()
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

  const projectColumns = [
    { title: t('thd.projectnm_thd'), dataIndex: 'projectnm', key: 'projectnm' },
    {
      title: t('thd.rolecd_thd'),
      dataIndex: 'rolecd',
      key: 'rolecd',
      width: 100,
      render: (v) => v === 'M' ? t('cod.rolecd_M') : v === 'U' ? t('cod.rolecd_U') : v || '-',
    },
  ]

  const createdts = tenant.createdts || '-'

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>{t('ttl.myinfo.personal')}</Title>

      <Row gutter={16}>
        {/* 개인 정보 */}
        <Col span={12}>
          <Card size="small" title={t('ttl.myinfo.personal')} loading={isLoading} style={{ marginBottom: 16 }}>
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

        {/* 기업(테넌트) 정보 */}
        <Col span={12}>
          <Card size="small" title={t('ttl.myinfo.tenant')} loading={isLoading} style={{ marginBottom: 16 }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label={t('lbl.tenantnm')}>{tenant.tenantnm || '-'}</Descriptions.Item>
              <Descriptions.Item label={t('lbl.myrole')}>
                {tenantuser.rolecd === 'M' ? t('cod.rolecd_M') : tenantuser.rolecd === 'U' ? t('cod.rolecd_U') : tenantuser.rolecd || '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('lbl.joindt')}>{createdts}</Descriptions.Item>
            </Descriptions>
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

    </div>
  )
}