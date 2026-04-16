import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert, Button, Card, Col, Form, Input, Modal, Row, Select, Space,
  Spin, Table, Typography,
} from 'antd'
import { ArrowLeftOutlined, SaveOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useDataparams, useCreateGendoc } from '@/hooks/useGendocs'
import apiClient from '@/api/client'

const { Title, Text } = Typography

export default function ReqDocSettingPage() {
  const navigate = useNavigate()
  const { data: paramData = {}, isLoading } = useDataparams()
  const createGendoc = useCreateGendoc()

  const [form] = Form.useForm()
  const [checkAlert, setCheckAlert] = useState(null)   // { type, msg }
  const [pendingValues, setPendingValues] = useState(null)
  const [saving, setSaving] = useState(false)

  const dataparams = paramData.dataparams || []
  const paramsValue = paramData.params_value || []
  const docid = dataparams[0]?.docid ?? null

  const getOptions = (dp) => {
    const pv = paramsValue.find((p) => p.datauid === dp.datauid)
    if (!pv || !pv.value.length) return []
    return pv.value.map((row) => ({
      value: String(row[dp.keycolnm] ?? ''),
      label: String(row[dp.nmcolnm || dp.keycolnm] ?? row[dp.keycolnm] ?? ''),
    }))
  }

  const doCreate = (values) => {
    setSaving(true)
    const docnm = values.docnm || ''
    const params = dataparams.map((dp) => ({
      paramuid: dp.paramuid,
      paramnm: dp.paramnm,
      orderno: dp.orderno,
      paramvalue: values[`param_${dp.paramuid}`] ?? '',
    }))
    createGendoc.mutate(
      { docid, docnm, params },
      {
        onSuccess: (data) => {
          setSaving(false)
          navigate(`/req/write?gendocs=${data.gendocuid}`)
        },
        onError: () => setSaving(false),
      },
    )
  }

  const handleSave = async () => {
    let values
    try {
      values = await form.validateFields()
    } catch (_) {
      return
    }

    setCheckAlert(null)
    setPendingValues(null)

    const params = dataparams.map((dp) => ({
      paramuid: dp.paramuid,
      paramnm: dp.paramnm,
      orderno: dp.orderno,
      paramvalue: values[`param_${dp.paramuid}`] ?? '',
    }))

    // 1. 항목 미설정 확인
    try {
      const objChk = await apiClient.post('/gendocs/check-objects', { docid })
      if (objChk.data.unset_objects?.length > 0) {
        const msgs = objChk.data.unset_objects.map((o) => o.text).join('\n')
        setCheckAlert({ type: 'warning', msg: `미설정 항목이 있습니다:\n${msgs}` })
      }
    } catch (_) { /* continue */ }

    // 2. 동일 파라미터 중복 확인
    try {
      const chk = await apiClient.post('/gendocs/params/check', { docid, params })
      if (chk.data.exists) {
        setPendingValues(values)
        Modal.confirm({
          title: '중복 확인',
          content: '동일한 파라미터 조합의 문서가 이미 존재합니다. 계속 생성하시겠습니까?',
          okText: '계속 생성',
          cancelText: '취소',
          onOk: () => doCreate(values),
        })
        return
      }
    } catch (_) { /* continue */ }

    doCreate(values)
  }

  const columns = [
    {
      title: '매개변수명',
      dataIndex: 'paramnm',
      key: 'paramnm',
      width: '30%',
    },
    {
      title: '예시값',
      dataIndex: 'samplevalue',
      key: 'samplevalue',
      width: '35%',
      render: (v) => <Text type="secondary">{v || '-'}</Text>,
    },
    {
      title: '입력값',
      key: 'input',
      width: '35%',
      render: (_, dp) => (
        <Form.Item name={`param_${dp.paramuid}`} style={{ margin: 0 }}>
          {dp.datauid ? (
            <Select
              options={getOptions(dp)}
              placeholder="선택"
              showSearch
              optionFilterProp="label"
              size="small"
              style={{ width: '100%' }}
            />
          ) : (
            <Input size="small" placeholder={dp.paramnm} />
          )}
        </Form.Item>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16, gap: 12 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/req/list')}>
          목록
        </Button>
        <Title level={4} style={{ margin: 0 }}>문서 작성</Title>
      </div>

      {checkAlert && (
        <Alert
          type={checkAlert.type}
          message={<pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{checkAlert.msg}</pre>}
          closable
          onClose={() => setCheckAlert(null)}
          style={{ marginBottom: 16 }}
        />
      )}

      <Spin spinning={isLoading}>
        <Form form={form} layout="vertical" size="small">
          <Row gutter={24} style={{ minHeight: '70vh' }}>
            {/* 좌측: 문서 구성 */}
            <Col
              span={8}
              style={{ borderRight: '1px solid #f0f0f0', paddingRight: 24 }}
            >
              <Card size="small" title="문서 구성" bordered={false} style={{ padding: 0 }}>
                <Form.Item
                  name="docnm"
                  label="작성 문서명"
                  rules={[{ required: true, message: '문서명을 입력해주세요.' }]}
                >
                  <Input placeholder="작성문서명을 입력하시오." />
                </Form.Item>

                {!docid && !isLoading && (
                  <Text type="secondary">
                    등록된 문서 양식이 없습니다.
                  </Text>
                )}
              </Card>
            </Col>

            {/* 우측: 매개변수 입력 */}
            <Col span={16}>
              <Card
                size="small"
                title="매개변수 입력"
                bordered={false}
                extra={
                  <Space>
                    <Button
                      icon={<ThunderboltOutlined />}
                      disabled
                      title="문서 일괄 작성(준비 중)"
                    >
                      일괄 작성
                    </Button>
                    <Button
                      type="primary"
                      icon={<SaveOutlined />}
                      loading={saving || createGendoc.isPending}
                      onClick={handleSave}
                      disabled={!docid}
                    >
                      구성 저장
                    </Button>
                  </Space>
                }
              >
                <Table
                  columns={columns}
                  dataSource={dataparams}
                  rowKey="paramuid"
                  size="small"
                  pagination={false}
                  locale={{ emptyText: '매개변수가 없습니다.' }}
                />
              </Card>
            </Col>
          </Row>
        </Form>
      </Spin>
    </div>
  )
}
