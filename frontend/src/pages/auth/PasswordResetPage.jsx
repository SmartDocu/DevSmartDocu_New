import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, Button, Card, Form, Input, Typography } from 'antd'
import { LockOutlined } from '@ant-design/icons'
import { useMutation } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { useLangStore, t } from '@/stores/langStore'

const { Title, Text } = Typography

export default function PasswordResetPage() {
  useLangStore((s) => s.translations)
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
      message.success(t('msg.password.changed'))
      setTimeout(() => navigate('/', { replace: true }), 1500)
    },
    onError: (err) => {
      const detail = err.response?.data?.detail || t('msg.password.change.failed')
      message.error(detail)
    },
  })

  const handleSubmit = (values) => {
    if (values.password !== values.confirm) {
      message.error(t('msg.password.mismatch'))
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
          <Text type="secondary">{t('ttl.password.reset')}</Text>
        </div>

        {tokenError ? (
          <div style={{ textAlign: 'center' }}>
            <Text type="danger" style={{ display: 'block', marginBottom: 16 }}>
              {t('msg.password.reset.invalid')}
            </Text>
            <Button type="link" onClick={() => navigate('/')}>
              {t('btn.go.login')}
            </Button>
          </div>
        ) : (
          <Form form={form} onFinish={handleSubmit} layout="vertical" size="large">
            <Form.Item
              name="password"
              label={t('lbl.new.password')}
              rules={[
                { required: true, message: t('msg.new.password.required') },
                { min: 6, message: t('msg.password.min6') },
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder={t('lbl.new.password')} />
            </Form.Item>

            <Form.Item
              name="confirm"
              label={t('lbl.password.confirm')}
              rules={[{ required: true, message: t('msg.password.confirm.required') }]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder={t('lbl.password.confirm')} />
            </Form.Item>

            <Form.Item style={{ marginBottom: 8 }}>
              <Button
                type="primary"
                htmlType="submit"
                block
                loading={updateMutation.isPending}
              >
                {t('btn.password.change')}
              </Button>
            </Form.Item>

            <div style={{ textAlign: 'center' }}>
              <Button type="link" onClick={() => navigate('/')}>
                {t('btn.back.to.login')}
              </Button>
            </div>
          </Form>
        )}
      </Card>
    </div>
  )
}
