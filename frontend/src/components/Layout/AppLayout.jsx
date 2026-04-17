import { Outlet, useNavigate } from 'react-router-dom'
import { Layout, Typography, Space, theme, Tabs, Select } from 'antd'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useLanguages, useTranslations, useSetLanguage } from '@/hooks/useI18n'
import { useConfigs } from '@/hooks/useConfigs'
import DocSelectModal from '@/components/DocSelectModal/DocSelectModal'
import RegisterModal from '@/components/RegisterModal/RegisterModal'
import LoginModal from '@/components/LoginModal/LoginModal'
import AppSidebar from '@/components/Layout/AppSidebar'
import { useState, useEffect } from 'react'
import { useTabStore } from '@/stores/tabStore'

const { Header, Content, Sider } = Layout
const { Text } = Typography

export default function AppLayout() {
  const navigate = useNavigate()
  const { token: cssToken } = theme.useToken()
  const { user, clearAuth, updateUser } = useAuthStore()

  const [docModalOpen, setDocModalOpen] = useState(false)
  const [registerModalOpen, setRegisterModalOpen] = useState(false)
  const [loginModalOpen, setLoginModalOpen] = useState(false)
  const { tabs, activeKey, closeTab, setActiveKey, siderCollapsed, setSiderCollapsed } = useTabStore()

  const { languageCd, setLanguageCd, setTranslations, resetLang } = useLangStore()
  const { data: languages = [] } = useLanguages()
  const { data: configs } = useConfigs()
  const { data: translationsData } = useTranslations(languageCd)
  const setLanguageMutation = useSetLanguage()

  // re-render 트리거용 구독
  useLangStore((s) => s.translations)

  const isLoggedIn = !!user

  // 언어 초기화
  // - 로그인 사용자: user.languagecd 항상 우선 적용 (로그인 시점에 덮어씌움)
  // - 비로그인: 한 번 설정되면 유지, 미설정 시 configs.default_lang → languages[0]
  useEffect(() => {
    if (user?.languagecd) {
      if (languageCd !== user.languagecd) setLanguageCd(user.languagecd)
      return
    }
    if (languageCd) return
    const resolved =
      configs?.default_lang ||
      (languages.length > 0 ? languages[0].languagecd : '')
    if (resolved) setLanguageCd(resolved)
  }, [user, configs, languages, languageCd, setLanguageCd])

  // 번역 dict 로드 — { translations, defaults } 구조
  useEffect(() => {
    if (translationsData) {
      setTranslations(translationsData.translations ?? {}, translationsData.defaults ?? {})
    }
  }, [translationsData, setTranslations])

  const handleLanguageChange = (cd) => {
    setLanguageCd(cd)
    if (user) updateUser({ languagecd: cd })  // effect 재실행 시 덮어씌움 방지
    setLanguageMutation.mutate(cd)
  }

  const handleLogout = () => {
    resetLang()
    clearAuth()
    navigate('/')
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {/* 좌측 Sidebar */}
      <Sider
        collapsible
        collapsed={siderCollapsed}
        onCollapse={setSiderCollapsed}
        width={300}
        collapsedWidth={50}
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          bottom: 0,
          zIndex: 100,
          background: '#fff',
          borderRight: '1px solid #e8e8e8',
          overflow: 'hidden',
        }}
        theme="light"
      >
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          {/* 로고 */}
          <div className="sidebar-logo" onClick={() => navigate('/')}>
            <img
              src={user?.tenanticonurl || '/SmartDocu.svg'}
              alt="로고"
              style={{ height: 28, width: 'auto', flexShrink: 0 }}
            />
            {!siderCollapsed && (
              <Text strong style={{ color: '#163E64', fontSize: 16, whiteSpace: 'nowrap' }}>
                SmartDocu
              </Text>
            )}
          </div>

          {/* 메뉴 영역 (스크롤 가능) */}
          <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
            <AppSidebar collapsed={siderCollapsed} />
          </div>

          {/* Copyright — Footer 대체 */}
          <div className="sidebar-copyright">
            {siderCollapsed
              ? <span title="© SmartDocu 2025">©</span>
              : '© SmartDocu 2025. All rights reserved.'
            }
          </div>
        </div>
      </Sider>

      {/* 오른쪽 메인 영역 */}
      <Layout style={{ marginLeft: siderCollapsed ? 50 : 300, transition: 'margin-left 0.2s' }}>
        <Header
          style={{
            position: 'fixed',
            top: 0,
            left: siderCollapsed ? 50 : 300,
            right: 0,
            zIndex: 10,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 24px',
            background: '#163E64',
            height: 60,
            transition: 'left 0.2s',
          }}
        >
          {/* 로고 + 이름 */}
          <div
            onClick={() => navigate('/')}
            style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}
          >
            <img
              src={user?.tenanticonurl || '/SmartDocu.svg'}
              alt="로고"
              style={{ height: 32, width: 'auto' }}
            />
            <Text strong style={{ color: '#fff', fontSize: 18 }}>SmartDocu</Text>
          </div>

          {/* 사용자 영역 */}
          <Space style={{ whiteSpace: 'nowrap' }} size={8}>
            {/* 언어 선택기 — 로그인/비로그인 공통 */}
            {languages.length > 0 && (
              <Select
                value={languageCd || undefined}
                onChange={handleLanguageChange}
                size="small"
                variant="borderless"
                style={{ minWidth: 80, color: '#fff' }}
                popupMatchSelectWidth={false}
                options={languages.map((l) => ({ value: l.languagecd, label: l.languagenm }))}
                className="lang-select"
              />
            )}

            {isLoggedIn ? (
              <>
                <img
                  src="/doc-select.svg"
                  alt="문서 선택"
                  title="문서 선택"
                  onClick={() => setDocModalOpen(true)}
                  style={{ width: 20, height: 20, cursor: 'pointer', filter: 'invert(100%) brightness(250%) contrast(150%)' }}
                />
                {user?.docnm && (
                  <Text style={{ color: '#fff' }}>{user.docnm}</Text>
                )}
                <Text style={{ color: '#aaa' }}>|</Text>
                <Text
                  style={{ color: '#fff', cursor: 'pointer' }}
                  onClick={() => navigate('/myinfo')}
                >
                  {user?.email ?? '사용자'}
                </Text>
                <button
                  className="btn btn-danger"
                  onClick={handleLogout}
                  style={{ color: 'var(--border-color)', textDecoration: 'none' }}
                >
                  {t('btn.logout')}
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => setRegisterModalOpen(true)}
                  style={{
                    backgroundColor: 'var(--primary-500, #245F97)',
                    color: '#fff',
                    padding: '6px 12px',
                    borderRadius: 4,
                    border: 'none',
                    fontSize: 14,
                    cursor: 'pointer',
                  }}
                >
                  {t('btn.register')}
                </button>
                <button
                  onClick={() => setLoginModalOpen(true)}
                  style={{
                    backgroundColor: '#17a2b8',
                    color: '#fff',
                    padding: '6px 12px',
                    borderRadius: 4,
                    border: 'none',
                    fontSize: 14,
                    cursor: 'pointer',
                  }}
                >
                  {t('btn.login')}
                </button>
              </>
            )}
          </Space>
        </Header>

        {/* 탭 바 */}
        {tabs.length > 0 && (
          <div
            style={{
              position: 'fixed',
              top: 60,
              left: siderCollapsed ? 50 : 300,
              right: 0,
              zIndex: 9,
              background: '#fafafa',
              borderBottom: '1px solid #e8e8e8',
              padding: '4px 16px 0',
              transition: 'left 0.2s',
            }}
          >
            <Tabs
              type="editable-card"
              hideAdd
              size="small"
              activeKey={activeKey}
              onChange={(key) => {
                const tab = tabs.find((t) => t.key === key)
                if (tab) { setActiveKey(key); navigate('/' + tab.path) }
              }}
              onEdit={(key, action) => {
                if (action === 'remove') {
                  const idx = tabs.findIndex((t) => t.key === key)
                  const nextTab = tabs[idx + 1] ?? tabs[idx - 1] ?? null
                  closeTab(key)
                  if (activeKey === key) {
                    if (nextTab) navigate('/' + nextTab.path)
                    else navigate('/')
                  }
                }
              }}
              items={tabs.map((t) => ({ key: t.key, label: t.label, closable: true }))}
              style={{ marginBottom: 0 }}
            />
          </div>
        )}

        <Content style={{ marginTop: tabs.length > 0 ? 104 : 60, padding: '0 24px 24px', minHeight: 'calc(100vh - 60px)' }}>
          <div style={{ background: cssToken.colorBgContainer, borderRadius: cssToken.borderRadius, padding: '12px 24px 24px' }}>
            <Outlet />
          </div>
        </Content>
      </Layout>

      <DocSelectModal open={docModalOpen} onClose={() => setDocModalOpen(false)} />
      <RegisterModal open={registerModalOpen} onClose={() => setRegisterModalOpen(false)} />
      <LoginModal open={loginModalOpen} onClose={() => setLoginModalOpen(false)} />
    </Layout>
  )
}
