import { App } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useMenuCodes } from '@/hooks/useMenus'
import { useBillingRecoveryAccounts, useRetryBillingRecovery } from '@/hooks/useAdmin'

export default function AdminBillingRecoveryPage() {
  const { message } = App.useApp()
  useLangStore((s) => s.translations)

  const { data = {}, isLoading } = useBillingRecoveryAccounts()
  const accounts = data.accounts || []
  const retryMutation = useRetryBillingRecovery()

  const { data: statusCodes = [] } = useMenuCodes('servicestatus')
  const statusLabel = (cd) => {
    const found = statusCodes.find((c) => c.codevalue === cd)
    return found ? (t(found.term_key) || found.default_name) : cd
  }

  const handleRetry = (accountuid) => {
    retryMutation.mutate(accountuid, {
      onError: (err) => { message.error(err.response?.data?.detail || t('msg.billing.retry.error')) },
    })
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('mnu.system.billing_recovery')}</div>
        </div>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <div className="spinner" />
        </div>
      ) : (
        <div style={{ height: 'calc(100vh - 330px)', overflowY: 'auto' }}>
          <table style={{ width: '100%' }}>
            <thead>
              <tr>
                <th>{t('lbl.tenantnm')}</th>
                <th>{t('thd.billing_status')}</th>
                <th>{t('thd.failure_count')}</th>
                <th>{t('thd.grace_until_dt')}</th>
                <th>{t('thd.next_billing_dt')}</th>
                <th style={{ width: '12%' }} />
              </tr>
            </thead>
            <tbody>
              {accounts.length === 0 ? (
                <tr><td colSpan={6} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
              ) : accounts.map((row) => (
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
                      {t('btn.retry_billing')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
