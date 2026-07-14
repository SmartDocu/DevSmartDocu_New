import { useState } from 'react'
import { App, Modal, Tabs, Form, Input, Upload, Button, Alert } from 'antd'
import { InboxOutlined } from '@ant-design/icons'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'

const { Dragger } = Upload

// 로컬 파일 업로드 또는 외부 API 연결로 세션에 데이터셋을 등록하는 모달.
// 등록되면 해당 세션은 이후 DB 대신 이 데이터(들)을 대상으로 질의하는 모드로 전환된다.
// apiBase: '/d2chat' | '/d2insight' — 둘 다 토큰 인증, d2insight는 user_id를 body에 추가로 포함
export default function DatasetUploadModal({ open, sessionId, onClose, onSuccess, apiBase = '/d2chat' }) {
  useLangStore((s) => s.translations)
  const { message } = App.useApp()
  const user = useAuthStore((s) => s.user)
  const isInsight = apiBase === '/d2insight'

  const [activeTab, setActiveTab] = useState('file')
  const [fileList, setFileList] = useState([])
  const [submitting, setSubmitting] = useState(false)
  const [apiForm] = Form.useForm()

  const resetAndClose = () => {
    setFileList([])
    apiForm.resetFields()
    setSubmitting(false)
    onClose()
  }

  const handleFileSubmit = async () => {
    if (fileList.length === 0) {
      message.error(t('msg.d2insight.select_file_required'))
      return
    }
    setSubmitting(true)
    try {
      const fd = new FormData()
      fileList.forEach((f) => fd.append('files', f.originFileObj || f))
      if (sessionId) fd.append('session_id', sessionId)
      if (user?.projectid != null) fd.append('project_id', user.projectid)
      if (user?.accountuid) fd.append('account_uid', user.accountuid)
      if (isInsight && user?.id) fd.append('user_id', user.id)

      const { data } = await apiClient.post(`${apiBase}/upload-dataset`, fd)
      message.success(t('msg.d2insight.datasets_registered').replace('{n}', data.datasets.length))
      onSuccess?.(data)
      resetAndClose()
    } catch (e) {
      message.error(e.response?.data?.detail || t('msg.d2insight.upload_error'))
    } finally {
      setSubmitting(false)
    }
  }

  const handleApiSubmit = async () => {
    try {
      const values = await apiForm.validateFields()
      setSubmitting(true)
      const { data } = await apiClient.post(`${apiBase}/upload-dataset-url`, {
        url: values.url,
        session_id: sessionId || null,
        project_id: user?.projectid ?? null,
        account_uid: user?.accountuid ?? null,
        dataset_name: values.dataset_name || null,
        header_name: values.header_name || null,
        header_value: values.header_value || null,
        ...(isInsight ? { user_id: user?.id ?? null } : {}),
      })
      message.success(t('msg.d2insight.datasets_registered').replace('{n}', data.datasets.length))
      onSuccess?.(data)
      resetAndClose()
    } catch (e) {
      if (e?.errorFields) return // antd form validation error, 조용히 무시
      message.error(e.response?.data?.detail || t('msg.d2insight.api_connect_error'))
    } finally {
      setSubmitting(false)
    }
  }

  const items = [
    {
      key: 'file',
      label: t('lbl.d2insight.file_upload'),
      children: (
        <div>
          <Dragger
            multiple
            accept=".csv,.xlsx,.xls"
            fileList={fileList}
            beforeUpload={() => false}
            onChange={({ fileList: fl }) => setFileList(fl)}
          >
            <p className="ant-upload-drag-icon"><InboxOutlined /></p>
            <p className="ant-upload-text">{t('inf.d2insight.upload_drag_text')}</p>
            <p className="ant-upload-hint">{t('inf.d2insight.upload_hint')}</p>
          </Dragger>
          <div style={{ marginTop: 16, textAlign: 'right' }}>
            <Button type="primary" onClick={handleFileSubmit} loading={submitting}>{t('btn.d2insight.upload')}</Button>
          </div>
        </div>
      ),
    },
    {
      key: 'api',
      label: t('lbl.d2insight.api_connect'),
      children: (
        <Form form={apiForm} layout="vertical">
          <Form.Item
            name="url"
            label="API URL"
            rules={[{ required: true, message: t('msg.d2insight.url_required') }]}
          >
            <Input placeholder="https://api.example.com/data" />
          </Form.Item>
          <Form.Item name="dataset_name" label={t('lbl.d2insight.dataset_name')}>
            <Input placeholder={t('inf.d2insight.dataset_name_placeholder')} />
          </Form.Item>
          <Form.Item name="header_name" label={t('lbl.d2insight.auth_header_name')}>
            <Input placeholder={t('inf.d2insight.auth_header_name_placeholder')} />
          </Form.Item>
          <Form.Item name="header_value" label={t('lbl.d2insight.auth_header_value')}>
            <Input.Password placeholder={t('inf.d2insight.auth_header_value_placeholder')} />
          </Form.Item>
          <Alert
            type="info"
            showIcon
            message={t('msg.d2insight.api_public_only')}
            style={{ marginBottom: 16 }}
          />
          <div style={{ textAlign: 'right' }}>
            <Button type="primary" onClick={handleApiSubmit} loading={submitting}>{t('btn.d2insight.connect')}</Button>
          </div>
        </Form>
      ),
    },
  ]

  return (
    <Modal
      title={t('ttl.d2insight.add_dataset')}
      open={open}
      onCancel={resetAndClose}
      footer={null}
      destroyOnClose
      width={560}
    >
      <Alert
        type="warning"
        showIcon
        message={t('msg.d2insight.dataset_scope_warning')}
        style={{ marginBottom: 16 }}
      />
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={items} />
    </Modal>
  )
}
