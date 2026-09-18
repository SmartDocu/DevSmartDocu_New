import { useNavigate } from 'react-router-dom'
import { Spin } from 'antd'
import { AppstoreOutlined } from '@ant-design/icons'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useApps } from '@/hooks/useApps'
import { useMenuCodes } from '@/hooks/useMenus'
import FreeServiceGate from '@/components/Launcher/FreeServiceGate'

function canSeeApp(app, user, subscribedServicecds) {
  const { rolecd, servicecd } = app
  if (!user) return false
  // 1. servicecd가 있으면 구독 여부로 판단
  if (servicecd) return subscribedServicecds.includes(servicecd)
  // 2. 시스템 관리자 전용
  if (rolecd === 'S') return user.roleid === 7
  // 3. rolecd 없음 → PM, TM, AM 중 하나라도 Y
  if (!rolecd) {
    return user.projectmanager === 'Y' || user.tenantmanager === 'Y' || user.accountmanager === 'Y'
  }
  return false
}

export default function AppLauncher() {
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const tenantid = useAuthStore((s) => s.user?.tenantid)
  const languageCd = useLangStore((s) => s.languageCd)
  const { data = {}, isLoading } = useApps({ tenantid, languagecd: languageCd })
  const { apps = [], subscribed_servicecds = [] } = data
  const { data: accountStatusCodes = [] } = useMenuCodes('accountstatus')

  useLangStore((s) => s.translations)

  const isAccountInactive = !!user?.accountstatus && user.accountstatus !== 'Active'
  const accountStatusMsg = isAccountInactive
    ? (() => {
        const code = accountStatusCodes.find((c) => c.codevalue === user.accountstatus)
        return code ? (t(code.term_key) || code.default_name) : t('msg.account.status.inactive')
      })()
    : ''
  const visibleApps = isAccountInactive
    ? []
    : apps.filter((app) => canSeeApp(app, user, subscribed_servicecds))

  // 개인(시스템 테넌트) 계정이 구독 서비스가 하나도 없으면 런처 그리드 대신
  // "체험할 서비스 선택" 게이트를 보여준다 — /launcher는 로그인 직후와 테넌트 전환
  // 직후 모두 거치는 공통 종착점이라, 여기 한 곳에만 조건을 걸면 두 경로 다 커버된다.
  const showFreeServiceGate = !isLoading && !isAccountInactive && !!user?.issystemtenant && subscribed_servicecds.length === 0

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', padding: '40px 0' }}>
      <h2 style={{ textAlign: 'center', marginBottom: 48, color: '#163E64', fontSize: 24, fontWeight: 700 }}>
        {user?.tenantnm}
      </h2>

      {isAccountInactive ? (
        <div style={{ textAlign: 'center', color: '#999', padding: 80 }}>
          {accountStatusMsg}
        </div>
      ) : isLoading ? (
        <div style={{ textAlign: 'center', padding: 80 }}>
          <Spin size="large" />
        </div>
      ) : showFreeServiceGate ? (
        <FreeServiceGate />
      ) : visibleApps.length === 0 ? (
        <div style={{ textAlign: 'center', color: '#999', padding: 80 }}>
          {t('msg.no.apps')}
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 20,
          }}
        >
          {visibleApps.map((app) => (
            <div
              key={app.appcd}
              onClick={() => navigate(`/app/${app.appcd}`)}
              style={{
                background: '#fff',
                borderRadius: 12,
                padding: '36px 20px 28px',
                textAlign: 'center',
                cursor: 'pointer',
                boxShadow: '0 2px 8px rgba(0,0,0,0.07)',
                transition: 'all 0.18s',
                border: '2px solid transparent',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = '#163E64'
                e.currentTarget.style.boxShadow = '0 6px 20px rgba(22,62,100,0.14)'
                e.currentTarget.style.transform = 'translateY(-2px)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'transparent'
                e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.07)'
                e.currentTarget.style.transform = 'translateY(0)'
              }}
            >
              {app.iconurl ? (
                <img
                  src={app.iconurl}
                  alt={app.appnm}
                  style={{ width: 52, height: 52, marginBottom: 16, objectFit: 'contain' }}
                />
              ) : (
                <AppstoreOutlined
                  style={{ fontSize: 44, color: '#163E64', marginBottom: 16, display: 'block' }}
                />
              )}
              <div style={{ fontSize: 15, fontWeight: 600, color: '#163E64' }}>
                {app.appnm}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
