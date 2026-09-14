import { useState } from 'react'
import { DatePicker, Input, Select, Table, Tabs, Tag } from 'antd'
import dayjs from 'dayjs'
import { useLangStore, t } from '@/stores/langStore'
import {
  usePrivacyConsentLogs,
  useAdminActionLogs,
  useWorkLogs,
  useLoginLogs,
} from '@/hooks/useAuditLogs'

const { RangePicker } = DatePicker

const CONSENT_TYPE_OPTIONS = [
  { value: 'userinfo', label: 'lbl.audit.consenttype.userinfo' },
  { value: 'termsofuse', label: 'lbl.audit.consenttype.termsofuse' },
  { value: 'electronicfinancialterms', label: 'lbl.audit.consenttype.electronicfinancialterms' },
]
const ADMIN_ACTION_OPTIONS = [
  'view_user', 'update', 'delete', 'permission_change', 'config_change',
].map((v) => ({ value: v, label: `lbl.audit.actioncd.${v}` }))
const WORK_SERVICE_OPTIONS = [
  { value: 'Do', label: 'lbl.audit.servicecd.do' },
  { value: 'Ch', label: 'lbl.audit.servicecd.ch' },
  { value: 'In', label: 'lbl.audit.servicecd.in' },
  { value: 'Tenant', label: 'lbl.audit.servicecd.tenant' },
]
const WORK_ACTION_OPTIONS = ['create', 'update', 'delete', 'create_requested'].map((v) => ({ value: v, label: `lbl.audit.actioncd.${v}` }))
const EVENT_TYPE_OPTIONS = [
  { value: 'login', label: 'lbl.audit.eventtype.login' },
  { value: 'logout', label: 'lbl.audit.eventtype.logout' },
]

function JsonCell({ value }) {
  if (!value) return <span style={{ color: '#bbb' }}>-</span>
  return (
    <pre style={{ margin: 0, maxWidth: 360, maxHeight: 160, overflow: 'auto', fontSize: 12, background: '#f7f7f7', padding: 6, borderRadius: 4 }}>
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

function useFilterState() {
  const [dates, setDates] = useState([dayjs().subtract(29, 'day'), dayjs()])
  const [email, setEmail] = useState('')
  const [emailInput, setEmailInput] = useState('')
  const [page, setPage] = useState(1)
  const pageSize = 10
  const commitEmailSearch = () => { setEmail(emailInput); setPage(1) }
  return { dates, setDates, email, emailInput, setEmailInput, commitEmailSearch, page, setPage, pageSize }
}

function FilterBar({ dates, setDates, emailInput, setEmailInput, commitEmailSearch, extra }) {
  return (
    <div className="panel-section" style={{ display: 'flex', gap: 20, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
      <div className="filter-item">
        <label style={{ fontWeight: 'bold' }}>{t('lbl.period')}</label>
        <RangePicker
          value={dates}
          onChange={(v) => setDates(v || [dayjs().subtract(29, 'day'), dayjs()])}
          allowClear={false}
        />
      </div>
      <div className="filter-item">
        <label style={{ fontWeight: 'bold' }}>{t('lbl.email')}</label>
        <Input.Search
          placeholder={t('lbl.audit.search.email')}
          style={{ width: 240 }}
          value={emailInput}
          onChange={(e) => setEmailInput(e.target.value)}
          onSearch={commitEmailSearch}
          allowClear
        />
      </div>
      {extra}
    </div>
  )
}

function UserCell({ record }) {
  return (
    <div>
      <div>{record.usernm || '-'}</div>
      <div style={{ fontSize: 12, color: '#888' }}>{record.email || record.useruid}</div>
    </div>
  )
}

// ─── 1. 개인정보 동의 로그 ───────────────────────────────────────────────────

function PrivacyConsentTab() {
  const f = useFilterState()
  const [consenttypecd, setConsenttypecd] = useState(undefined)
  const params = {
    start_date: f.dates[0]?.format('YYYY-MM-DD'),
    end_date: f.dates[1]?.format('YYYY-MM-DD'),
    email: f.email || undefined,
    consenttypecd,
    page: f.page,
    page_size: f.pageSize,
  }
  const { data = {}, isLoading } = usePrivacyConsentLogs(params)

  const columns = [
    { title: t('thd.audit.user'), key: 'user', render: (_, r) => <UserCell record={r} /> },
    { title: t('thd.audit.consenttype'), dataIndex: 'consenttypecd', key: 'consenttypecd', render: (v) => t(`lbl.audit.consenttype.${v}`) },
    { title: t('thd.audit.consentyn'), dataIndex: 'consentyn', key: 'consentyn', render: (v) => (v ? <Tag color="green">Y</Tag> : <Tag color="red">N</Tag>) },
    { title: t('thd.audit.termsversion'), dataIndex: 'termsversion', key: 'termsversion' },
    { title: t('thd.audit.ip'), dataIndex: 'ip', key: 'ip' },
    { title: t('thd.audit.createdts'), dataIndex: 'createdts', key: 'createdts' },
  ]

  return (
    <div>
      <FilterBar
        {...f}
        extra={
          <div className="filter-item">
            <label style={{ fontWeight: 'bold' }}>{t('thd.audit.consenttype')}</label>
            <Select
              allowClear
              style={{ width: 220 }}
              value={consenttypecd}
              onChange={(v) => { setConsenttypecd(v); f.setPage(1) }}
              options={CONSENT_TYPE_OPTIONS.map((o) => ({ value: o.value, label: t(o.label) }))}
            />
          </div>
        }
      />
      <div className="panel-section">
        <Table
          rowKey="consentloguid"
          columns={columns}
          dataSource={data.items || []}
          loading={isLoading}
          pagination={{
            current: f.page, pageSize: f.pageSize, total: data.total || 0, position: ['bottomCenter'],
            onChange: f.setPage, showSizeChanger: false,
          }}
          size="small"
        />
      </div>
    </div>
  )
}

// ─── 2. 보안/관리자 로그 ─────────────────────────────────────────────────────

function AdminActionsTab() {
  const f = useFilterState()
  const [actioncd, setActioncd] = useState(undefined)
  const params = {
    start_date: f.dates[0]?.format('YYYY-MM-DD'),
    end_date: f.dates[1]?.format('YYYY-MM-DD'),
    email: f.email || undefined,
    actioncd,
    page: f.page,
    page_size: f.pageSize,
  }
  const { data = {}, isLoading } = useAdminActionLogs(params)

  const columns = [
    { title: t('thd.audit.user'), key: 'user', render: (_, r) => <UserCell record={r} /> },
    { title: t('thd.audit.actioncd'), dataIndex: 'actioncd', key: 'actioncd', render: (v) => <Tag>{t(`lbl.audit.actioncd.${v}`)}</Tag> },
    { title: t('thd.audit.target'), key: 'target', render: (_, r) => (
      <div>
        <div>{r.targettype || '-'}</div>
        <div style={{ fontSize: 12, color: '#888' }}>{r.targetid || ''}</div>
      </div>
    ) },
    { title: t('thd.audit.before'), dataIndex: 'before_json', key: 'before_json', render: (v) => <JsonCell value={v} /> },
    { title: t('thd.audit.after'), dataIndex: 'after_json', key: 'after_json', render: (v) => <JsonCell value={v} /> },
    { title: t('thd.audit.ip'), dataIndex: 'ip', key: 'ip' },
    { title: t('thd.audit.createdts'), dataIndex: 'createdts', key: 'createdts' },
  ]

  return (
    <div>
      <FilterBar
        {...f}
        extra={
          <div className="filter-item">
            <label style={{ fontWeight: 'bold' }}>{t('thd.audit.actioncd')}</label>
            <Select
              allowClear
              style={{ width: 220 }}
              value={actioncd}
              onChange={(v) => { setActioncd(v); f.setPage(1) }}
              options={ADMIN_ACTION_OPTIONS.map((o) => ({ value: o.value, label: t(o.label) }))}
            />
          </div>
        }
      />
      <div className="panel-section" style={{ overflowX: 'auto' }}>
        <Table
          rowKey="adminloguid"
          columns={columns}
          dataSource={data.items || []}
          loading={isLoading}
          scroll={{ x: 'max-content' }}
          pagination={{
            current: f.page, pageSize: f.pageSize, total: data.total || 0, position: ['bottomCenter'],
            onChange: f.setPage, showSizeChanger: false,
          }}
          size="small"
        />
      </div>
    </div>
  )
}

// ─── 3-1. 접속/작업 로그 (work_logs) ─────────────────────────────────────────

function WorkLogsTab() {
  const f = useFilterState()
  const [servicecd, setServicecd] = useState(undefined)
  const [actioncd, setActioncd] = useState(undefined)
  const params = {
    start_date: f.dates[0]?.format('YYYY-MM-DD'),
    end_date: f.dates[1]?.format('YYYY-MM-DD'),
    email: f.email || undefined,
    servicecd,
    actioncd,
    page: f.page,
    page_size: f.pageSize,
  }
  const { data = {}, isLoading } = useWorkLogs(params)

  const columns = [
    { title: t('thd.audit.user'), key: 'user', render: (_, r) => <UserCell record={r} /> },
    { title: t('thd.audit.servicecd'), dataIndex: 'servicecd', key: 'servicecd', render: (v) => <Tag>{v}</Tag> },
    { title: t('thd.audit.actioncd'), dataIndex: 'actioncd', key: 'actioncd', render: (v) => <Tag>{t(`lbl.audit.actioncd.${v}`)}</Tag> },
    { title: t('thd.audit.target'), key: 'target', render: (_, r) => (
      <div>
        <div>{r.targettype || '-'}</div>
        <div style={{ fontSize: 12, color: '#888' }}>{r.targetid || ''}</div>
      </div>
    ) },
    { title: t('thd.audit.before'), dataIndex: 'before_json', key: 'before_json', render: (v) => <JsonCell value={v} /> },
    { title: t('thd.audit.after'), dataIndex: 'after_json', key: 'after_json', render: (v) => <JsonCell value={v} /> },
    { title: t('thd.audit.request'), key: 'request', render: (_, r) => (
      <div style={{ fontSize: 12 }}>
        <div><Tag>{r.detail?.method}</Tag> {r.detail?.path}</div>
        {r.detail?.query && <div style={{ color: '#888' }}>?{r.detail.query}</div>}
      </div>
    ) },
    { title: t('thd.audit.ip'), dataIndex: 'ip', key: 'ip' },
    { title: t('thd.audit.createdts'), dataIndex: 'createdts', key: 'createdts' },
  ]

  return (
    <div>
      <FilterBar
        {...f}
        extra={
          <>
            <div className="filter-item">
              <label style={{ fontWeight: 'bold' }}>{t('thd.audit.servicecd')}</label>
              <Select
                allowClear
                style={{ width: 160 }}
                value={servicecd}
                onChange={(v) => { setServicecd(v); f.setPage(1) }}
                options={WORK_SERVICE_OPTIONS.map((o) => ({ value: o.value, label: t(o.label) }))}
              />
            </div>
            <div className="filter-item">
              <label style={{ fontWeight: 'bold' }}>{t('thd.audit.actioncd')}</label>
              <Select
                allowClear
                style={{ width: 160 }}
                value={actioncd}
                onChange={(v) => { setActioncd(v); f.setPage(1) }}
                options={WORK_ACTION_OPTIONS.map((o) => ({ value: o.value, label: t(o.label) }))}
              />
            </div>
          </>
        }
      />
      <div className="panel-section" style={{ overflowX: 'auto' }}>
        <Table
          rowKey="workloguid"
          columns={columns}
          dataSource={data.items || []}
          loading={isLoading}
          scroll={{ x: 'max-content' }}
          pagination={{
            current: f.page, pageSize: f.pageSize, total: data.total || 0, position: ['bottomCenter'],
            onChange: f.setPage, showSizeChanger: false,
          }}
          size="small"
        />
      </div>
    </div>
  )
}

// ─── 3-2. 접속/작업 로그 (login_logs) ────────────────────────────────────────

function LoginLogsTab() {
  const f = useFilterState()
  const [eventtypecd, setEventtypecd] = useState(undefined)
  const params = {
    start_date: f.dates[0]?.format('YYYY-MM-DD'),
    end_date: f.dates[1]?.format('YYYY-MM-DD'),
    email: f.email || undefined,
    eventtypecd,
    page: f.page,
    page_size: f.pageSize,
  }
  const { data = {}, isLoading } = useLoginLogs(params)

  const columns = [
    { title: t('thd.audit.user'), key: 'user', render: (_, r) => <UserCell record={r} /> },
    { title: t('thd.audit.eventtype'), dataIndex: 'eventtypecd', key: 'eventtypecd', render: (v) => <Tag color={v === 'logout' ? 'default' : 'blue'}>{v}</Tag> },
    { title: t('thd.audit.roleid'), dataIndex: 'roleid', key: 'roleid', render: (v) => {
      if (v === 7) return <Tag color="volcano">{t('lbl.audit.admin_role')}</Tag>
      if (v === 1) return <Tag>{t('lbl.audit.general_role')}</Tag>
      return v ?? '-'
    } },
    { title: t('thd.audit.success'), dataIndex: 'is_success', key: 'is_success', render: (v) => (v ? <Tag color="green">OK</Tag> : <Tag color="red">FAIL</Tag>) },
    { title: t('thd.audit.mfa'), dataIndex: 'is_mfaused', key: 'is_mfaused', render: (v) => (v ? 'Y' : 'N') },
    { title: t('thd.audit.ip'), dataIndex: 'ip', key: 'ip' },
    { title: t('thd.audit.browser'), key: 'browser', render: (_, r) => `${r.browser || ''} ${r.browser_version || ''} / ${r.os || ''}` },
    { title: t('thd.audit.createdts'), dataIndex: 'logindts', key: 'logindts' },
  ]

  return (
    <div>
      <FilterBar
        {...f}
        extra={
          <div className="filter-item">
            <label style={{ fontWeight: 'bold' }}>{t('thd.audit.eventtype')}</label>
            <Select
              allowClear
              style={{ width: 160 }}
              value={eventtypecd}
              onChange={(v) => { setEventtypecd(v); f.setPage(1) }}
              options={EVENT_TYPE_OPTIONS.map((o) => ({ value: o.value, label: t(o.label) }))}
            />
          </div>
        }
      />
      <div className="panel-section">
        <Table
          rowKey="login_logui"
          columns={columns}
          dataSource={data.items || []}
          loading={isLoading}
          pagination={{
            current: f.page, pageSize: f.pageSize, total: data.total || 0, position: ['bottomCenter'],
            onChange: f.setPage, showSizeChanger: false,
          }}
          size="small"
        />
      </div>
    </div>
  )
}

// ─── 페이지 루트 ─────────────────────────────────────────────────────────────

export default function AdminAuditLogsPage() {
  useLangStore((s) => s.translations)

  const items = [
    { key: 'consent', label: t('ttl.audit.consent'), children: <PrivacyConsentTab /> },
    { key: 'admin', label: t('ttl.audit.admin_log'), children: <AdminActionsTab /> },
    { key: 'work', label: t('ttl.audit.work'), children: <WorkLogsTab /> },
    { key: 'login', label: t('ttl.audit.login'), children: <LoginLogsTab /> },
  ]

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('mnu.system.audit_logs')}</div>
        </div>
      </div>
      <Tabs items={items} defaultActiveKey="consent" />
    </div>
  )
}
