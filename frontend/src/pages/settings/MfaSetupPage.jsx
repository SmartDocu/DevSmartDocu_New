import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  Row,
  Space,
  Steps,
  Tag,
  Typography,
} from 'antd'
import {
  CheckCircleOutlined,
  CopyOutlined,
  LockOutlined,
  QrcodeOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import QRCode from 'qrcode'
import { useMfaFactors, useMfaEnroll, useMfaEnrollVerify, useMfaUnenroll } from '@/hooks/useMfa'
import { useLangStore, t } from '@/stores/langStore'

const { Title, Text, Paragraph } = Typography

// ─── QR 코드 캔버스 컴포넌트 ─────────────────────────────────────────────────
function QRCodeCanvas({ uri }) {
  const [dataUrl, setDataUrl] = useState('')

  useEffect(() => {
    if (!uri) return
    QRCode.toDataURL(uri, { width: 180, margin: 2 })
      .then(setDataUrl)
      .catch(() => setDataUrl(''))
  }, [uri])

  if (!dataUrl) return null
  return (
    <img
      src={dataUrl}
      alt="QR Code"
      style={{ width: 180, height: 180, border: '1px solid #f0f0f0', borderRadius: 8 }}
    />
  )
}

// ─── 메인 페이지 ─────────────────────────────────────────────────────────────
export default function MfaSetupPage() {
  useLangStore((s) => s.translations)
  const navigate = useNavigate()
  const [form] = Form.useForm()

  // 현재 단계: 0 = 상태 확인, 1 = QR 스캔, 2 = 코드 입력, 3 = 완료
  const [currentStep, setCurrentStep] = useState(0)
  const [enrollData, setEnrollData] = useState(null)   // { factor_id, totp_uri, secret }
  const [copiedSecret, setCopiedSecret] = useState(false)

  const { data: factorsData, isLoading: factorsLoading } = useMfaFactors()
  const mfaEnroll    = useMfaEnroll()
  const mfaEnrollVerify = useMfaEnrollVerify()
  const mfaUnenroll  = useMfaUnenroll()

  const isMfaEnabled = factorsData?.mfa_enabled ?? false
  const verifiedFactor = factorsData?.factors?.find((f) => f.status === 'verified') ?? null

  // ── 등록 시작 ───────────────────────────────────────────────────────────────
  const handleEnrollStart = () => {
    mfaEnroll.mutate(undefined, {
      onSuccess: (data) => {
        setEnrollData(data)
        setCurrentStep(1)
      },
    })
  }

  // ── 등록 확인 ───────────────────────────────────────────────────────────────
  const handleEnrollVerify = async () => {
    const { code } = await form.validateFields()
    mfaEnrollVerify.mutate(
      { factor_id: enrollData.factor_id, code },
      {
        onSuccess: () => {
          form.resetFields()
          setCurrentStep(3)
        },
      },
    )
  }

  // ── 해제 ────────────────────────────────────────────────────────────────────
  const handleUnenroll = () => {
    if (!verifiedFactor) return
    mfaUnenroll.mutate(
      { factor_id: verifiedFactor.factor_id },
      { onSuccess: () => setCurrentStep(0) },
    )
  }

  // ── 시크릿 복사 ─────────────────────────────────────────────────────────────
  const handleCopySecret = () => {
    navigator.clipboard.writeText(enrollData?.secret || '')
    setCopiedSecret(true)
    setTimeout(() => setCopiedSecret(false), 2000)
  }

  // ─── 현재 MFA 상태 카드 ───────────────────────────────────────────────────
  const StatusCard = () => (
    <Card
      size="small"
      title={
        <Space>
          <SafetyCertificateOutlined />
          {t('ttl.mfa.status')}
        </Space>
      }
      loading={factorsLoading}
      style={{ marginBottom: 16 }}
    >
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label={t('ttl.mfa.status')}>
          {isMfaEnabled ? (
            <Tag color="green" icon={<CheckCircleOutlined />}>{t('lbl.mfa.enable')}</Tag>
          ) : (
            <Tag color="default">{t('btn.mfa.disable')}</Tag>
          )}
        </Descriptions.Item>
        {verifiedFactor && (
          <Descriptions.Item label={t('lbl.mfa.registered_at')}>
            {verifiedFactor.created_at
              ? new Date(verifiedFactor.created_at).toLocaleDateString()
              : '-'}
          </Descriptions.Item>
        )}
      </Descriptions>

      <div style={{ marginTop: 16 }}>
        {isMfaEnabled ? (
          <Button
            danger
            size="small"
            loading={mfaUnenroll.isPending}
            onClick={handleUnenroll}
          >
            {t('btn.mfa.disable')}
          </Button>
        ) : (
          <Button
            type="primary"
            size="small"
            icon={<LockOutlined />}
            loading={mfaEnroll.isPending}
            onClick={handleEnrollStart}
          >
            {t('btn.mfa.enable')}
          </Button>
        )}
      </div>
    </Card>
  )

  // ─── Step 1: QR 코드 스캔 ────────────────────────────────────────────────
  const ScanStep = () => (
    <Card size="small" title={t('ttl.mfa.scan')} style={{ marginBottom: 16 }}>
      <Alert
        type="info"
        showIcon
        message={t('msg.mfa.scan_guide')}
        style={{ marginBottom: 16 }}
      />
      <Row gutter={24} align="middle">
        <Col>
          <QRCodeCanvas uri={enrollData?.totp_uri} />
        </Col>
        <Col flex={1}>
          <Paragraph style={{ marginBottom: 8 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t('lbl.mfa.manual_entry')}
            </Text>
          </Paragraph>
          <Space.Compact style={{ width: '100%' }}>
            <Input
              readOnly
              value={enrollData?.secret || ''}
              style={{ fontFamily: 'monospace', fontSize: 13 }}
            />
            <Button
              icon={<CopyOutlined />}
              onClick={handleCopySecret}
              type={copiedSecret ? 'primary' : 'default'}
            >
              {copiedSecret ? t('btn.mfa.copied') : t('btn.mfa.copy')}
            </Button>
          </Space.Compact>
          <Paragraph style={{ marginTop: 12, marginBottom: 0 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t('msg.mfa.app_guide')}
            </Text>
          </Paragraph>
        </Col>
      </Row>

      <div style={{ marginTop: 20, textAlign: 'right' }}>
        <Space>
          <Button size="small" onClick={() => setCurrentStep(0)}>{t('btn.cancel')}</Button>
          <Button size="small" type="primary" icon={<QrcodeOutlined />} onClick={() => setCurrentStep(2)}>
            {t('btn.mfa.next')}
          </Button>
        </Space>
      </div>
    </Card>
  )

  // ─── Step 2: 코드 입력 ───────────────────────────────────────────────────
  const VerifyStep = () => (
    <Card size="small" title={t('ttl.mfa.verify')} style={{ marginBottom: 16 }}>
      <Alert
        type="warning"
        showIcon
        message={t('msg.mfa.verify_guide')}
        style={{ marginBottom: 16 }}
      />
      {mfaEnrollVerify.isError && (
        <Alert
          type="error"
          showIcon
          message={t('msg.mfa.code_invalid')}
          style={{ marginBottom: 12 }}
        />
      )}
      <Form form={form} layout="vertical" size="small">
        <Form.Item
          name="code"
          label={t('lbl.mfa.code')}
          rules={[
            { required: true, message: t('val.mfa.code_required') },
            { len: 6, message: t('val.mfa.code_length') },
            { pattern: /^\d{6}$/, message: t('val.mfa.code_digits') },
          ]}
        >
          <Input
            maxLength={6}
            style={{ width: 160, letterSpacing: 4, fontFamily: 'monospace', fontSize: 20 }}
            placeholder="000000"
          />
        </Form.Item>
      </Form>

      <div style={{ textAlign: 'right' }}>
        <Space>
          <Button size="small" onClick={() => setCurrentStep(1)}>{t('btn.mfa.prev')}</Button>
          <Button
            size="small"
            type="primary"
            icon={<SafetyCertificateOutlined />}
            loading={mfaEnrollVerify.isPending}
            onClick={handleEnrollVerify}
          >
            {t('btn.mfa.activate')}
          </Button>
        </Space>
      </div>
    </Card>
  )

  // ─── Step 3: 완료 ────────────────────────────────────────────────────────
  const DoneStep = () => (
    <Card size="small" style={{ marginBottom: 16 }}>
      <Alert
        type="success"
        showIcon
        icon={<CheckCircleOutlined />}
        message={t('msg.mfa.activated')}
        // description={t('msg.mfa.activated_desc')}
        style={{ marginBottom: 16 }}
      />
      <div style={{ textAlign: 'right' }}>
        <Button type="primary" size="small" onClick={() => navigate(-1)}>
          {t('btn.back_to_settings')}
        </Button>
      </div>
    </Card>
  )

  // ─── 렌더링 ─────────────────────────────────────────────────────────────
  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>
        {t('ttl.mfa.setup')}
      </Title>

      <Row gutter={16}>
        {/* 좌측: 현재 상태 */}
        <Col span={12}>
          <StatusCard />

          {/* 안내 카드 */}
          <Card size="small" title={t('ttl.mfa.guide')} style={{ marginBottom: 16 }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label={t('lbl.mfa.what')}>
                {t('msg.mfa.what_desc')}
              </Descriptions.Item>
              <Descriptions.Item label={t('lbl.mfa.app')}>
                Google Authenticator, Microsoft Authenticator, Authy
              </Descriptions.Item>
              <Descriptions.Item label={t('lbl.mfa.effect')}>
                {t('msg.mfa.effect_desc')}
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>

        {/* 우측: 등록 진행 */}
        <Col span={12}>
          {currentStep > 0 && currentStep < 3 && (
            <Card size="small" style={{ marginBottom: 16 }}>
              <Steps
                size="small"
                current={currentStep - 1}
                items={[
                  { title: t('ttl.mfa.scan') },
                  { title: t('ttl.mfa.verify') },
                ]}
                style={{ marginBottom: 16 }}
              />
            </Card>
          )}

          {currentStep === 0 && !isMfaEnabled && (
            <Card size="small" style={{ marginBottom: 16 }}>
              <Alert
                type="info"
                showIcon
                message={t('msg.mfa.not_enabled')}
                description={t('msg.mfa.not_enabled_desc')}
              />
            </Card>
          )}

          {currentStep === 1 && <ScanStep />}
          {currentStep === 2 && <VerifyStep />}
          {currentStep === 3 && <DoneStep />}
        </Col>
      </Row>
    </div>
  )
}