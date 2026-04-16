import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Button, Card, Form, Input, Select, Steps, Typography,
  Divider, Checkbox, Row, Col, InputNumber,
} from 'antd'
import {
  MailOutlined, LockOutlined, UserOutlined, PhoneOutlined,
} from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { useSendSms, useVerifySms, useRegister } from '@/hooks/useAuth'

const { Title, Text } = Typography

const BILLING_OPTIONS = [
  { value: 'single', label: '개인 (Free)' },
  { value: 'Pr', label: '개인 (Pro)' },
  { value: 'teams', label: '단체' },
]

export default function RegisterPage() {
  const [current, setCurrent] = useState(0) // 0: SMS, 1: 회원가입 폼
  const [verifiedPhone, setVerifiedPhone] = useState(null)
  const [form] = Form.useForm()
  const [smsForm] = Form.useForm()
  const [smsCodeForm] = Form.useForm()
  const [codeSent, setCodeSent] = useState(false)

  const sendSmsMutation = useSendSms()
  const verifySmsMutation = useVerifySms()
  const registerMutation = useRegister()

  const { data: tenantsData } = useQuery({
    queryKey: ['tenants'],
    queryFn: () => apiClient.get('/auth/tenants').then((r) => r.data),
  })

  const handleSendSms = async () => {
    const values = await smsForm.validateFields(['phone_number'])
    sendSmsMutation.mutate(values.phone_number, {
      onSuccess: () => setCodeSent(true),
    })
  }

  const handleVerifySms = async () => {
    const values = await smsCodeForm.validateFields(['code'])
    const phone = smsForm.getFieldValue('phone_number')
    verifySmsMutation.mutate(
      { phone_number: phone, code: values.code },
      {
        onSuccess: () => {
          setVerifiedPhone(phone)
          setCurrent(1)
        },
      },
    )
  }

  const handleRegister = (values) => {
    const billingmodelcd = values.billingmodelcd || 'single'
    const isTeam = billingmodelcd === 'teams'
    registerMutation.mutate({
      email: values.email,
      password: values.password,
      usernm: values.usernm,
      phone: verifiedPhone || '',
      billingmodelcd,
      tenantid: isTeam ? values.tenantid : undefined,
      termsofuseyn: values.terms?.includes('terms') ? 'Y' : 'N',
      userinfoyn: values.terms?.includes('privacy') ? 'Y' : 'N',
      marketingyn: values.terms?.includes('marketing') ? 'Y' : 'N',
    })
  }

  const billingmodelcd = Form.useWatch('billingmodelcd', form)
  const isTeam = billingmodelcd === 'teams'

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#f0f2f5',
        padding: '24px 0',
      }}
    >
      <Card style={{ width: 480, boxShadow: '0 4px 20px rgba(0,0,0,0.1)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={3} style={{ margin: 0 }}>회원가입</Title>
        </div>

        <Steps
          current={current}
          items={[{ title: 'SMS 인증' }, { title: '정보 입력' }]}
          style={{ marginBottom: 32 }}
          size="small"
        />

        {/* ── Step 0: SMS 인증 ──────────────────────────── */}
        {current === 0 && (
          <>
            <Form form={smsForm} layout="vertical" size="large">
              <Form.Item
                name="phone_number"
                label="휴대폰 번호"
                rules={[{ required: true, message: '휴대폰 번호를 입력해주세요.' }]}
              >
                <Input
                  prefix={<PhoneOutlined />}
                  placeholder="01012345678"
                  maxLength={13}
                />
              </Form.Item>
              <Button
                type="primary"
                block
                onClick={handleSendSms}
                loading={sendSmsMutation.isPending}
              >
                인증번호 받기
              </Button>
            </Form>

            {codeSent && (
              <Form form={smsCodeForm} layout="vertical" size="large" style={{ marginTop: 16 }}>
                <Form.Item
                  name="code"
                  label="인증번호"
                  rules={[{ required: true, message: '인증번호를 입력해주세요.' }]}
                >
                  <Input placeholder="6자리 인증번호" maxLength={6} />
                </Form.Item>
                <Row gutter={8}>
                  <Col span={12}>
                    <Button
                      block
                      onClick={handleSendSms}
                      loading={sendSmsMutation.isPending}
                    >
                      재발송
                    </Button>
                  </Col>
                  <Col span={12}>
                    <Button
                      type="primary"
                      block
                      onClick={handleVerifySms}
                      loading={verifySmsMutation.isPending}
                    >
                      인증하기
                    </Button>
                  </Col>
                </Row>
              </Form>
            )}
          </>
        )}

        {/* ── Step 1: 회원가입 폼 ───────────────────────── */}
        {current === 1 && (
          <Form form={form} onFinish={handleRegister} layout="vertical" size="large">
            <Form.Item
              name="usernm"
              label="이름"
              rules={[{ required: true, message: '이름을 입력해주세요.' }]}
            >
              <Input prefix={<UserOutlined />} placeholder="홍길동" />
            </Form.Item>

            <Form.Item
              name="email"
              label="이메일"
              rules={[
                { required: true, message: '이메일을 입력해주세요.' },
                { type: 'email', message: '올바른 이메일 형식이 아닙니다.' },
              ]}
            >
              <Input prefix={<MailOutlined />} placeholder="example@email.com" />
            </Form.Item>

            <Form.Item
              name="password"
              label="비밀번호"
              rules={[
                { required: true, message: '비밀번호를 입력해주세요.' },
                { min: 8, message: '비밀번호는 8자 이상이어야 합니다.' },
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="8자 이상" />
            </Form.Item>

            <Form.Item
              name="password_confirm"
              label="비밀번호 확인"
              dependencies={['password']}
              rules={[
                { required: true, message: '비밀번호를 다시 입력해주세요.' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) {
                      return Promise.resolve()
                    }
                    return Promise.reject(new Error('비밀번호가 일치하지 않습니다.'))
                  },
                }),
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="비밀번호 재입력" />
            </Form.Item>

            <Form.Item name="billingmodelcd" label="요금제" initialValue="single">
              <Select options={BILLING_OPTIONS} />
            </Form.Item>

            {isTeam && (
              <Form.Item
                name="tenantid"
                label="소속 기업"
                rules={[{ required: true, message: '소속 기업을 선택해주세요.' }]}
              >
                <Select
                  showSearch
                  placeholder="기업을 선택하세요"
                  filterOption={(input, option) =>
                    option?.label?.toLowerCase().includes(input.toLowerCase())
                  }
                  options={(tenantsData?.tenants || []).map((t) => ({
                    value: t.id,
                    label: t.tenantname,
                  }))}
                />
              </Form.Item>
            )}

            <Form.Item
              name="terms"
              rules={[
                {
                  validator(_, value) {
                    const required = ['terms', 'privacy']
                    const missing = required.filter((r) => !value?.includes(r))
                    if (missing.length > 0) {
                      return Promise.reject(new Error('필수 약관에 동의해주세요.'))
                    }
                    return Promise.resolve()
                  },
                },
              ]}
            >
              <Checkbox.Group style={{ width: '100%' }}>
                <Row>
                  <Col span={24}>
                    <Checkbox value="terms">
                      (필수) SmartDoc 이용약관 동의
                    </Checkbox>
                  </Col>
                  <Col span={24}>
                    <Checkbox value="privacy">
                      (필수) 개인정보 수집 및 이용 동의
                    </Checkbox>
                  </Col>
                  <Col span={24}>
                    <Checkbox value="marketing">
                      (선택) 마케팅 정보 수신 동의
                    </Checkbox>
                  </Col>
                </Row>
              </Checkbox.Group>
            </Form.Item>

            <Form.Item>
              <Button
                type="primary"
                htmlType="submit"
                block
                loading={registerMutation.isPending}
              >
                가입하기
              </Button>
            </Form.Item>
          </Form>
        )}

        <Divider />
        <div style={{ textAlign: 'center' }}>
          <Text type="secondary">이미 계정이 있으신가요? </Text>
          <Link to="/login">로그인</Link>
        </div>
      </Card>
    </div>
  )
}
