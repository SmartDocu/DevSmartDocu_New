import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { CheckCircleOutlined } from '@ant-design/icons'
import { useLangStore, t } from '@/stores/langStore'

const fill = (s, vars) => Object.entries(vars).reduce((acc, [k, v]) => acc.split(`{${k}}`).join(v ?? ''), s)

// 탈퇴 완료 화면 — 탈퇴 직후 로그아웃된 상태에서 보이므로 인증이 필요 없는 공개 라우트다.
// 결과 데이터는 탈퇴 페이지가 router state로 넘겨준다(새로고침/직접 접근 시에는 홈으로).
export default function WithdrawDonePage() {
  useLangStore((s) => s.translations)
  const navigate = useNavigate()
  const result = useLocation().state?.result
  if (!result) return <Navigate to="/" replace />

  const proServices = (result.personal_services || []).filter((s) => s.is_pro)
  const lines = [
    t('inf.withdraw.done.personal'),
    ...proServices.map((s) => fill(t('inf.withdraw.done.billing_stop'), { name: s.productnm })),
    ...(result.orgs || []).map((o) => {
      let text = t('inf.withdraw.res.masked')
      if (o.kind === 'soloOrg') text = o.end_mode === 'delete' ? t('inf.withdraw.res.end_delete') : t('inf.withdraw.res.end_keep')
      return `${o.tenantnm}: ${text}`
    }),
    ...(result.email ? [fill(t('inf.withdraw.done.mail'), { email: result.email })] : []),
  ]

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('btn.account.withdraw')}</div>
        </div>
        <div />
      </div>

      <div className="panel-section" style={{ maxWidth: 640 }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10, minHeight: 32,
          margin: '-16px -18px 16px', padding: '16px 18px 12px',
          borderBottom: '1px solid var(--border-color, #e3e6eb)',
        }}>
          <CheckCircleOutlined style={{ fontSize: 20, color: '#52c41a' }} />
          <h3 style={{ margin: 0, lineHeight: 1 }}>{t('ttl.withdraw.done')}</h3>
        </div>
        <ul style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 8, lineHeight: 1.65 }}>
          {lines.map((l) => <li key={l}>{l}</li>)}
        </ul>
        <p style={{ margin: '20px 0 0', color: '#555' }}>{t('inf.withdraw.done.thanks')}</p>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 20 }}>
          <button className="btn btn-primary" type="button" onClick={() => navigate('/', { replace: true })}>
            {t('btn.withdraw.home')}
          </button>
        </div>
      </div>
    </div>
  )
}
