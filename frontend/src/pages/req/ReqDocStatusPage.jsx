import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Button, Card, Col, Row, Space, Table, Tag, Typography,
} from 'antd'
import { ArrowLeftOutlined, ArrowRightOutlined } from '@ant-design/icons'
import { useGendocStatus } from '@/hooks/useGendocs'

const { Title, Text } = Typography

export default function ReqDocStatusPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const gendocuid = searchParams.get('gendocs')

  const { data = {}, isLoading } = useGendocStatus(gendocuid)
  const [selectedRow, setSelectedRow] = useState(null)

  const { status: rows = [], gendocnm = '', createfiledts = '' } = data

  const columns = [
    {
      title: '챕터명',
      dataIndex: 'chapternm',
      key: 'chapternm',
      width: '20%',
    },
    {
      title: '작성자',
      dataIndex: 'createuser',
      key: 'createuser',
      width: '8%',
      align: 'center',
    },
    {
      title: '작성일시',
      dataIndex: 'createfiledts',
      key: 'createfiledts',
      width: '11%',
      align: 'center',
      render: (v) => v || '-',
    },
    {
      title: '수정자',
      dataIndex: 'updateuser',
      key: 'updateuser',
      width: '8%',
      align: 'center',
    },
    {
      title: '업로드일시',
      dataIndex: 'updatefiledts',
      key: 'updatefiledts',
      width: '11%',
      align: 'center',
      render: (v) => v || '-',
    },
    {
      title: '미반영 챕터',
      dataIndex: 'new_chapteryn',
      key: 'new_chapteryn',
      width: '9%',
      align: 'center',
      render: (v) => (v ? <Tag color="orange">√</Tag> : ''),
    },
    {
      title: '항목수',
      dataIndex: 'object_cnt',
      key: 'object_cnt',
      width: '8%',
      align: 'center',
      render: (v) => v ?? 0,
    },
    {
      title: '미반영 항목수',
      dataIndex: 'new_object_cnt',
      key: 'new_object_cnt',
      width: '10%',
      align: 'center',
      render: (v) =>
        v > 0 ? <Tag color="red">{v}</Tag> : (v ?? 0),
    },
  ]

  return (
    <div>
      {/* 헤더 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/req/list')}>
            목록
          </Button>
          <Title level={4} style={{ margin: 0 }}>
            문서 작성 상태 조회
            {gendocnm && (
              <Text type="secondary" style={{ fontSize: 14 }}> — {gendocnm}</Text>
            )}
          </Title>
        </div>
      </div>

      {/* 상세 정보 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={24}>
          <Col>
            <Text type="secondary">문서 작성 일시: </Text>
            <Text>{createfiledts || '-'}</Text>
          </Col>
        </Row>
      </Card>

      {/* 챕터 상태 테이블 */}
      <Card size="small" title="챕터 상태">
        <Table
          columns={columns}
          dataSource={rows}
          rowKey={(row) => row.genchapteruid || row.chapternm}
          loading={isLoading}
          size="small"
          pagination={false}
          rowClassName={(row) =>
            row.genchapteruid === selectedRow?.genchapteruid ? 'ant-table-row-selected' : ''
          }
          onRow={(row) => ({
            onClick: () => setSelectedRow(row),
            style: { cursor: 'pointer' },
          })}
        />
      </Card>

      {/* 하단 이동 버튼 */}
      <div style={{ marginTop: 16, display: 'flex', justifyContent: 'center', gap: 16 }}>
        <Button
          type="link"
          icon={<ArrowRightOutlined />}
          onClick={() => navigate(`/req/chapters-read?gendocs=${gendocuid}`)}
        >
          챕터
        </Button>
        <Button
          type="link"
          icon={<ArrowRightOutlined />}
          disabled={!selectedRow}
          onClick={() =>
            selectedRow &&
            navigate(`/req/chapter-objects?genchapteruid=${selectedRow.genchapteruid}`)
          }
        >
          챕터 항목
        </Button>
      </div>
    </div>
  )
}
