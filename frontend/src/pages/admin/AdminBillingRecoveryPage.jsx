import { useEffect, useState } from 'react'
import { Pagination } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { useLangStore, t } from '@/stores/langStore'
import { useMenuCodes } from '@/hooks/useMenus'
import { useBillingRecoveryAccounts, useRetryBillingRecovery } from '@/hooks/useAdmin'

const PAGE_SIZE = 10

export default function AdminBillingRecoveryPage() {
  useLangStore((s) => s.translations)

  const { data = {}, isLoading } = useBillingRecoveryAccounts()
  const accounts = data.accounts || []
  const retryMutation = useRetryBillingRecovery()

  const [page, setPage] = useState(1)
  useEffect(() => { setPage(1) }, [accounts.length])
  const pagedAccounts = accounts.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const { data: statusCodes = [] } = useMenuCodes('servicestatus')
  const statusLabel = (cd) => {
    const found = statusCodes.find((c) => c.codevalue === cd)
    return found ? (t(found.term_key) || found.default_name) : cd
  }

  const handleRetry = (accountuid) => {
    retryMutation.mutate(accountuid)
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('mnu.system.billing_recovery')}</div>
        </div>
      </div>

      <div className="panel-section" style={{ height: 'calc(100vh - 224px)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', height: 60, flexShrink: 0,
          margin: '-16px -18px 16px', padding: '16px 18px 12px',
          borderBottom: '1px solid var(--border-color, #e3e6eb)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <h3 style={{ margin: 0, lineHeight: 1 }}>{t('ttl.list')}</h3>
            <span style={{
              display: 'inline-flex', alignItems: 'center', lineHeight: 1,
              font: '500 11px monospace', color: '#8d9199', background: '#f2efe9',
              borderRadius: 6, padding: '5px 8px 4px',
            }}>
              {t('lbl.count.docs').replace('{n}', accounts.length)}
            </span>
          </div>
          <div />
        </div>

        {isLoading ? (
          <div style={{ textAlign: 'center', padding: 48 }}>
            <div className="spinner" />
          </div>
        ) : (
          <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th>{t('lbl.tenantnm')}</th>
                  <th>{t('thd.billing_status')}</th>
                  <th>{t('thd.failure_count')}</th>
                  <th>{t('thd.grace_until_dt')}</th>
                  <th>{t('thd.next_billing_dt')}</th>
                  <th style={{ width: '14%' }} />
                </tr>
              </thead>
              <tbody>
                {pagedAccounts.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : pagedAccounts.map((row) => (
                  <tr key={row.accountuid}>
                    <td>{row.tenantnm || '-'}</td>
                    <td style={{ color: row.billing_status === 'Suspended' ? '#cf1322' : '#d46b08' }}>
                      {statusLabel(row.billing_status)}
                    </td>
                    <td style={{ textAlign: 'center' }}>{row.failure_count ?? 0}</td>
                    <td>{row.grace_until_dt || '-'}</td>
                    <td>{row.next_billing_dt || '-'}</td>
                    <td style={{ textAlign: 'center' }}>
                      <button
                        type="button"
                        className="btn btn-primary"
                        disabled={retryMutation.isPending}
                        onClick={() => handleRetry(row.accountuid)}
                      >
                        <ReloadOutlined style={{ marginRight: 6 }} />{t('btn.retry_billing')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {accounts.length > PAGE_SIZE && (
          <div style={{ marginTop: 'auto', paddingTop: 12, display: 'flex', justifyContent: 'center' }}>
            <Pagination
              current={page}
              pageSize={PAGE_SIZE}
              total={accounts.length}
              showSizeChanger={false}
              onChange={setPage}
            />
          </div>
        )}
      </div>
    </div>
  )
}
