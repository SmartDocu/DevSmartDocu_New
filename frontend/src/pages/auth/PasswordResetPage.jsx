import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, Button, Card, Form, Input, Typography } from 'antd'
import { LockOutlined } from '@ant-design/icons'
import { useMutation } from '@tanstack/react-query'
import apiClient from '@/api/client'

const { Title, Text } = Typography

export default function PasswordResetPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [tokens, setTokens] = useState({ accessToken: '', refreshToken: '' })
  const [tokenError, setTokenError] = useState(false)

  // Supabase 복구 링크: /password-reset#access_token=xxx&refresh_token=yyy&type=recovery
  useEffect(() => {
    const hash = window.location.hash.substring(1) // '#' 제거
    const params = new URLSearchParams(hash)
    const accessToken = params.get('access_token')
    const refreshToken = params.get('refresh_token')
    const type = params.get('type')

    if (!accessToken || type !== 'recovery') {
      setTokenError(true)
      return
    }
    setTokens({ accessToken, refreshToken: refreshToken || '' })
    // 브라우저 URL에서 fragment 제거 (보안)
    window.history.replaceState(null, '', window.location.pathname)
  }, [])

  const updateMutation = useMutation({
    mutationFn: ({ newPassword }) =>
      apiClient.post('/auth/update-password', {
        access_token: tokens.accessToken,
        refresh_token: tokens.refreshToken || undefined,
        new_password: newPassword,
      }).then((r) => r.data),
    onSuccess: () => {
      message.success('비밀번호가 변경되었습니다.')
      setTimeout(() => navigate('/login', { replace: true }), 1500)
    },
    onError: (err) => {
      const detail = err.response?.data?.detail || '비밀번호 변경에 실패했습니다.'
      message.error(detail)
    },
  })

  const handleSubmit = (values) => {
    if (values.password !== values.confirm) {
      message.error('비밀번호가 일치하지 않습니다.')
      return
    }
    updateMutation.mutate({ newPassword: values.password })
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
          <Title level={3} style={{ margin: 0 }}>Smart Document</Title>
          <Text type="secondary">비밀번호 재설정</Text>
        </div>

        {tokenError ? (
          <div style={{ textAlign: 'center' }}>
            <Text type="danger" style={{ display: 'block', marginBottom: 16 }}>
              유효하지 않은 재설정 링크입니다.<br />
              이메일 링크를 다시 요청해주세요.
            </Text>
            <Button type="link" onClick={() => navigate('/login')}>
              로그인 페이지로 이동
            </Button>
          </div>
        ) : (
          <Form form={form} onFinish={handleSubmit} layout="vertical" size="large">
            <Form.Item
              name="password"
              label="새 비밀번호"
              rules={[
                { required: true, message: '새 비밀번호를 입력해주세요.' },
                { min: 6, message: '비밀번호는 6자 이상이어야 합니다.' },
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="새 비밀번호" />
            </Form.Item>

            <Form.Item
              name="confirm"
              label="비밀번호 확인"
              rules={[{ required: true, message: '비밀번호를 다시 입력해주세요.' }]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="비밀번호 확인" />
            </Form.Item>

            <Form.Item style={{ marginBottom: 8 }}>
              <Button
                type="primary"
                htmlType="submit"
                block
                loading={updateMutation.isPending}
              >
                비밀번호 변경
              </Button>
            </Form.Item>

            <div style={{ textAlign: 'center' }}>
              <Button type="link" onClick={() => navigate('/login')}>
                로그인으로 돌아가기
              </Button>
            </div>
          </Form>
        )}
      </Card>
    </div>
  )
}
