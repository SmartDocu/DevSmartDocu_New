import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, Button, Card, Form, Input, Typography } from 'antd'
import { LockOutlined } from '@ant-design/icons'
import { useMutation } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { useLangStore, t } from '@/stores/langStore'
import { useLanguages, useTranslations } from '@/hooks/useI18n'
import { useConfigs } from '@/hooks/useConfigs'

const { Title, Text } = Typography

export default function PasswordResetPage() {
  useLangStore((s) => s.translations)
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [tokenHash, setTokenHash] = useState('')
  const [tokenError, setTokenError] = useState(false)
  const processedRef = useRef(false)

  // 이 페이지는 AppLayout 밖(비로그인 전용 라우트)에서 렌더되므로, AppLayout이 하는
  // 언어 초기화/번역 로드를 직접 해줘야 한다 — 안 하면 langStore.translations가 계속
  // 빈 값이라 t()가 항상 key 원문을 그대로 반환한다.
  const { languageCd, setLanguageCd, setTranslations } = useLangStore()
  const { data: languages = [] } = useLanguages()
  const { data: configs } = useConfigs()
  const { data: translationsData } = useTranslations(languageCd)

  useEffect(() => {
    if (languageCd) return
    const resolved = configs?.default_lang || (languages.length > 0 ? languages[0].languagecd : '')
    if (resolved) setLanguageCd(resolved)
  }, [configs, languages, languageCd, setLanguageCd])

  useEffect(() => {
    if (translationsData) {
      setTranslations(translationsData.translations ?? {}, translationsData.defaults ?? {})
    }
  }, [translationsData, setTranslations])

  // 이메일 링크: /password-reset?token_hash=xxx&type=recovery
  // token_hash는 여기서 바로 서버에 검증 요청하지 않는다 — 메일 보안 스캐너가
  // 링크를 미리 방문해 1회용 토큰을 소진시키는 문제를 피하기 위해, 검증은
  // 사용자가 "비밀번호 변경" 버튼을 눌러 폼을 제출하는 시점까지 미룬다.
  useEffect(() => {
    // StrictMode(개발 모드)가 effect를 두 번 실행해도 URL 처리(replaceState)는 1회만 되도록 가드
    if (processedRef.current) return
    processedRef.current = true

    const params = new URLSearchParams(window.location.search)
    const hash = params.get('token_hash')
    const type = params.get('type')

    if (!hash || type !== 'recovery') {
      setTokenError(true)
      return
    }
    setTokenHash(hash)
    // 브라우저 URL에서 쿼리스트링 제거 (보안)
    window.history.replaceState(null, '', window.location.pathname)
  }, [])

  const updateMutation = useMutation({
    mutationFn: ({ newPassword }) =>
      apiClient.post('/auth/update-password', {
        token_hash: tokenHash,
        new_password: newPassword,
      }).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.password.changed'))
      setTimeout(() => navigate('/', { replace: true }), 1500)
    },
    onError: (err) => {
      const detail = t(err.response?.data?.detail) || t('msg.password.change.failed')
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
          <Title level={3} style={{ margin: 0 }}>D2Doc</Title>
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
