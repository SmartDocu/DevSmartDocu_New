import { useState } from 'react'
import { App, Modal, Tabs, Form, Input, Upload, Button, Alert } from 'antd'
import { InboxOutlined } from '@ant-design/icons'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'

const { Dragger } = Upload

// 로컬 파일 업로드 또는 외부 API 연결로 세션에 데이터셋을 등록하는 모달.
// 등록되면 해당 세션은 이후 DB 대신 이 데이터(들)을 대상으로 질의하는 모드로 전환된다.
export default function DatasetUploadModal({ open, sessionId, onClose, onSuccess }) {
  const { message } = App.useApp()
  const user = useAuthStore((s) => s.user)

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
      message.error('업로드할 파일을 선택해주세요.')
      return
    }
    setSubmitting(true)
    try {
      const fd = new FormData()
      fileList.forEach((f) => fd.append('files', f.originFileObj || f))
      if (sessionId) fd.append('session_id', sessionId)
      if (user?.projectid != null) fd.append('project_id', user.projectid)
      if (user?.accountuid) fd.append('account_uid', user.accountuid)

      const { data } = await apiClient.post('/d2chat/upload-dataset', fd)
      message.success(`${data.datasets.length}개 데이터셋이 등록되었습니다.`)
      onSuccess?.(data)
      resetAndClose()
    } catch (e) {
      message.error(e.response?.data?.detail || '파일 업로드 중 오류가 발생했습니다.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleApiSubmit = async () => {
    try {
      const values = await apiForm.validateFields()
      setSubmitting(true)
      const { data } = await apiClient.post('/d2chat/upload-dataset-url', {
        url: values.url,
        session_id: sessionId || null,
        project_id: user?.projectid ?? null,
        account_uid: user?.accountuid ?? null,
        dataset_name: values.dataset_name || null,
        header_name: values.header_name || null,
        header_value: values.header_value || null,
      })
      message.success(`${data.datasets.length}개 데이터셋이 등록되었습니다.`)
      onSuccess?.(data)
      resetAndClose()
    } catch (e) {
      if (e?.errorFields) return // antd form validation error, 조용히 무시
      message.error(e.response?.data?.detail || 'API 연결 중 오류가 발생했습니다.')
    } finally {
      setSubmitting(false)
    }
  }

  const items = [
    {
      key: 'file',
      label: '파일 업로드',
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
            <p className="ant-upload-text">클릭하거나 파일을 드래그하여 업로드</p>
            <p className="ant-upload-hint">CSV, XLSX, XLS 파일 지원 (여러 개 선택 가능, 전체 500MB 이하)</p>
          </Dragger>
          <div style={{ marginTop: 16, textAlign: 'right' }}>
            <Button type="primary" onClick={handleFileSubmit} loading={submitting}>업로드</Button>
          </div>
        </div>
      ),
    },
    {
      key: 'api',
      label: 'API 연결',
      children: (
        <Form form={apiForm} layout="vertical">
          <Form.Item
            name="url"
            label="API URL"
            rules={[{ required: true, message: 'URL을 입력해주세요.' }]}
          >
            <Input placeholder="https://api.example.com/data" />
          </Form.Item>
          <Form.Item name="dataset_name" label="데이터셋 이름 (선택)">
            <Input placeholder="지정하지 않으면 호스트명을 사용합니다" />
          </Form.Item>
          <Form.Item name="header_name" label="인증 헤더 이름 (선택)">
            <Input placeholder="예: Authorization" />
          </Form.Item>
          <Form.Item name="header_value" label="인증 헤더 값 (선택)">
            <Input.Password placeholder="예: Bearer xxxxx" />
          </Form.Item>
          <Alert
            type="info"
            showIcon
            message="JSON 응답을 반환하는 공개 API만 지원합니다. 사설/내부망 주소는 사용할 수 없습니다."
            style={{ marginBottom: 16 }}
          />
          <div style={{ textAlign: 'right' }}>
            <Button type="primary" onClick={handleApiSubmit} loading={submitting}>연결</Button>
          </div>
        </Form>
      ),
    },
  ]

  return (
    <Modal
      title="데이터셋 추가"
      open={open}
      onCancel={resetAndClose}
      footer={null}
      destroyOnClose
      width={560}
    >
      <Alert
        type="warning"
        showIcon
        message="데이터셋을 등록하면 이 대화는 이후 등록된 데이터만을 대상으로 답변합니다 (기존 DB 조회는 사용되지 않습니다)."
        style={{ marginBottom: 16 }}
      />
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={items} />
    </Modal>
  )
}
