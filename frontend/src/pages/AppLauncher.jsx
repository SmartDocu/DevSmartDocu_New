import { useNavigate } from 'react-router-dom'
import { Spin } from 'antd'
import { AppstoreOutlined } from '@ant-design/icons'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useApps } from '@/hooks/useApps'

function canSeeApp(rolecd, user) {
  if (!rolecd || rolecd === 'P') return true
  if (!user) return false
  if (rolecd === 'U') return true
  if (rolecd === 'PM') return user.projectmanager === 'Y'
  if (rolecd === 'TM') return user.tenantmanager === 'Y'
  if (rolecd === 'S') return user.roleid === 7
  return false
}

export default function AppLauncher() {
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const { data: apps = [], isLoading } = useApps()

  useLangStore((s) => s.translations)

  const visibleApps = apps.filter((app) => canSeeApp(app.rolecd, user))

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', padding: '40px 0' }}>
      <h2 style={{ textAlign: 'center', marginBottom: 48, color: '#163E64', fontSize: 24, fontWeight: 700 }}>
        D2Doc
      </h2>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 80 }}>
          <Spin size="large" />
        </div>
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
