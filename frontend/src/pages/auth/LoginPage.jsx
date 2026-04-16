import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, Form, Input, Typography, Divider } from 'antd'
import { MailOutlined, LockOutlined } from '@ant-design/icons'
import { useLogin, useSendResetEmail } from '@/hooks/useAuth'

const { Title, Text } = Typography

export default function LoginPage() {
  const [mode, setMode] = useState('login') // 'login' | 'reset'
  const [form] = Form.useForm()
  const [resetForm] = Form.useForm()

  const loginMutation = useLogin()
  const resetMutation = useSendResetEmail()

  const handleLogin = (values) => {
    loginMutation.mutate({ email: values.email, password: values.password })
  }

  const handleReset = (values) => {
    resetMutation.mutate(values.email)
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#f0f2f5',
      }}
    >
      <Card style={{ width: 400, boxShadow: '0 4px 20px rgba(0,0,0,0.1)' }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <Title level={3} style={{ margin: 0 }}>
            Smart Document
          </Title>
          <Text type="secondary">
            {mode === 'login' ? '로그인' : '비밀번호 재설정'}
          </Text>
        </div>

        {mode === 'login' ? (
          <Form form={form} onFinish={handleLogin} layout="vertical" size="large">
            <Form.Item
              name="email"
              rules={[
                { required: true, message: '이메일을 입력해주세요.' },
                { type: 'email', message: '올바른 이메일 형식이 아닙니다.' },
              ]}
            >
              <Input prefix={<MailOutlined />} placeholder="이메일" />
            </Form.Item>

            <Form.Item
              name="password"
              rules={[{ required: true, message: '비밀번호를 입력해주세요.' }]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="비밀번호" />
            </Form.Item>

            <Form.Item style={{ marginBottom: 8 }}>
              <Button
                type="primary"
                htmlType="submit"
                block
                loading={loginMutation.isPending}
              >
                로그인
              </Button>
            </Form.Item>

            <div style={{ textAlign: 'center' }}>
              <Button type="link" onClick={() => setMode('reset')}>
                비밀번호를 잊으셨나요?
              </Button>
            </div>

            <Divider />

            <div style={{ textAlign: 'center' }}>
              <Text type="secondary">계정이 없으신가요? </Text>
              <Link to="/register">회원가입</Link>
            </div>
          </Form>
        ) : (
          <Form form={resetForm} onFinish={handleReset} layout="vertical" size="large">
            <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
              가입한 이메일 주소를 입력하면 비밀번호 재설정 링크를 보내드립니다.
            </Text>

            <Form.Item
              name="email"
              rules={[
                { required: true, message: '이메일을 입력해주세요.' },
                { type: 'email', message: '올바른 이메일 형식이 아닙니다.' },
              ]}
            >
              <Input prefix={<MailOutlined />} placeholder="이메일" />
            </Form.Item>

            <Form.Item>
              <Button
                type="primary"
                htmlType="submit"
                block
                loading={resetMutation.isPending}
              >
                재설정 이메일 발송
              </Button>
            </Form.Item>

            <div style={{ textAlign: 'center' }}>
              <Button type="link" onClick={() => setMode('login')}>
                로그인으로 돌아가기
              </Button>
            </div>
          </Form>
        )}
      </Card>
    </div>
  )
}
