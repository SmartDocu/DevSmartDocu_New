import { useState } from 'react'
import {
  Button, Card, Checkbox, Col, Form, Input, Popconfirm,
  Row, Table, Typography,
} from 'antd'
import { PlusOutlined, SaveOutlined, DeleteOutlined } from '@ant-design/icons'
import { useSettingsProjects, useSaveProject, useDeleteProject } from '@/hooks/useSettings'

const { Title, Text } = Typography

export default function SettingsProjectsPage() {
  const { data = {}, isLoading } = useSettingsProjects()
  const saveProject = useSaveProject()
  const deleteProject = useDeleteProject()
  const [form] = Form.useForm()
  const [selectedId, setSelectedId] = useState(null)

  const projects = data.projects || []
  const tenantnm = data.tenantnm || ''

  const handleRowSelect = (row) => {
    setSelectedId(row.projectid)
    form.setFieldsValue({
      projectid: row.projectid,
      projectnm: row.projectnm,
      projectdesc: row.projectdesc || '',
      useyn: row.useyn,
    })
  }

  const handleNew = () => {
    setSelectedId(null)
    form.resetFields()
    form.setFieldsValue({ useyn: true })
  }

  const handleSave = async () => {
    const values = await form.validateFields()
    saveProject.mutate(
      {
        projectid: values.projectid || null,
        projectnm: values.projectnm,
        projectdesc: values.projectdesc || null,
        useyn: values.useyn ?? true,
      },
      { onSuccess: handleNew },
    )
  }

  const handleDelete = () => {
    if (!selectedId) return
    deleteProject.mutate(selectedId, { onSuccess: handleNew })
  }

  const columns = [
    { title: '프로젝트명', dataIndex: 'projectnm', key: 'projectnm' },
    {
      title: '설명',
      dataIndex: 'projectdesc',
      key: 'projectdesc',
      render: (v) => <Text type="secondary">{v || ''}</Text>,
    },
    {
      title: '사용',
      dataIndex: 'useyn',
      key: 'useyn',
      width: 60,
      align: 'center',
      render: (v) => v ? '✔' : '',
    },
    { title: '생성일시', dataIndex: 'createdts', key: 'createdts', width: 130 },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>
        프로젝트 관리
        {tenantnm && <Text type="secondary" style={{ fontSize: 14 }}> — {tenantnm}</Text>}
      </Title>
      <Row gutter={24}>
        <Col span={14}>
          <Card size="small" title="프로젝트 목록">
            <Table
              columns={columns}
              dataSource={projects}
              rowKey="projectid"
              loading={isLoading}
              size="small"
              pagination={{ pageSize: 15 }}
              rowClassName={(row) => row.projectid === selectedId ? 'ant-table-row-selected' : ''}
              onRow={(row) => ({ onClick: () => handleRowSelect(row), style: { cursor: 'pointer' } })}
            />
          </Card>
        </Col>

        <Col span={10}>
          <Card
            size="small"
            title="프로젝트 상세"
            extra={<Button size="small" icon={<PlusOutlined />} onClick={handleNew}>신규</Button>}
          >
            <Form form={form} layout="vertical" size="small">
              <Form.Item name="projectid" hidden><Input /></Form.Item>

              <Form.Item name="projectnm" label="프로젝트명" rules={[{ required: true, message: '필수 항목입니다.' }]}>
                <Input />
              </Form.Item>

              <Form.Item name="projectdesc" label="설명">
                <Input.TextArea rows={4} style={{ resize: 'none' }} />
              </Form.Item>

              <Form.Item name="useyn" valuePropName="checked" label="사용">
                <Checkbox />
              </Form.Item>

              <Row gutter={8}>
                <Col>
                  <Button type="primary" icon={<SaveOutlined />} loading={saveProject.isPending} onClick={handleSave}>
                    저장
                  </Button>
                </Col>
                <Col>
                  <Popconfirm title="삭제하시겠습니까?" onConfirm={handleDelete} okText="삭제" cancelText="취소" disabled={!selectedId}>
                    <Button danger icon={<DeleteOutlined />} disabled={!selectedId} loading={deleteProject.isPending}>
                      삭제
                    </Button>
                  </Popconfirm>
                </Col>
              </Row>
            </Form>
          </Card>
        </Col>
      </Row>
    </div>
  )
}
