import { useState } from 'react'
import { DatePicker, Select, Table, Tag } from 'antd'
import dayjs from 'dayjs'
import { useLangStore, t } from '@/stores/langStore'
import { useAuthStore } from '@/stores/authStore'
import { useMyGenFailures } from '@/hooks/useGenFailures'
import { getGenErrorKey } from '@/utils/genError'

const { RangePicker } = DatePicker

export default function ReqGenFailuresPage() {
  useLangStore((s) => s.translations)
  const user = useAuthStore((s) => s.user)

  const [dates, setDates] = useState([dayjs().subtract(29, 'day'), dayjs()])
  const [kind, setKind] = useState('doc')
  const [page, setPage] = useState(1)
  const pageSize = 10

  const params = {
    kind,
    projectid: user?.projectid,   // 현재 선택된 프로젝트 — 소속 여부는 서버가 검증한다
    start_date: dates[0]?.format('YYYY-MM-DD'),
    end_date: dates[1]?.format('YYYY-MM-DD'),
    page,
    page_size: pageSize,
  }
  const { data = {}, isLoading } = useMyGenFailures(params)

  const columns = [
    { title: t('thd.audit.createdts'), dataIndex: 'startdts', key: 'startdts', width: 140 },
    { title: t('thd.audit.user'), key: 'user', width: 200, render: (_, r) => (
      <div>
        <div>{r.usernm || '-'}</div>
        <div style={{ fontSize: 12, color: '#888' }}>{r.email || ''}</div>
      </div>
    ) },
    { title: t('thd.projectnm_thd'), dataIndex: 'projectnm', key: 'projectnm', width: 160 },
    { title: t('thd.gendocnm'), dataIndex: 'docnm', key: 'docnm' },
    { title: t('thd.chapternm'), dataIndex: 'chapternm', key: 'chapternm', render: (v) => v || '-' },
    { title: t('thd.gen.reason'), dataIndex: 'errorcd', key: 'errorcd', render: (v) => (
      <div style={{ wordBreak: 'break-word' }}>
        <Tag color="red">{v}</Tag>
        <span>{t(getGenErrorKey(v))}</span>
      </div>
    ) },
  ]

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('ttl.gen.failures')}</div>
        </div>
      </div>

      <div className="panel-section" style={{ display: 'flex', gap: 20, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        <div className="filter-item">
          <label style={{ fontWeight: 'bold' }}>{t('lbl.period')}</label>
          <RangePicker
            value={dates}
            onChange={(v) => { setDates(v || [dayjs().subtract(29, 'day'), dayjs()]); setPage(1) }}
            allowClear={false}
          />
        </div>
        <div className="filter-item">
          <label style={{ fontWeight: 'bold' }}>{t('thd.audit.genkind')}</label>
          <Select
            style={{ width: 140 }}
            value={kind}
            onChange={(v) => { setKind(v); setPage(1) }}
            options={['doc', 'chapter'].map((v) => ({ value: v, label: t(`lbl.audit.genkind.${v}`) }))}
          />
        </div>
      </div>

      <div className="panel-section">
        <Table
          rowKey="jobuid"
          columns={columns}
          dataSource={data.items || []}
          loading={isLoading}
          pagination={{
            current: page, pageSize, total: data.total || 0, position: ['bottomCenter'],
            onChange: setPage, showSizeChanger: false,
          }}
          size="small"
        />
      </div>
    </div>
  )
}
