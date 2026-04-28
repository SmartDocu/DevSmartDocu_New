import { Outlet, useNavigate } from 'react-router-dom'
import { Layout, Typography, Space, theme, Tabs, Select, Badge, Dropdown, App } from 'antd'
import { GlobalOutlined, BellOutlined, UserOutlined, HomeOutlined, InfoCircleOutlined, ReadOutlined, LeftOutlined, RightOutlined } from '@ant-design/icons'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useLanguages, useTranslations, useSetLanguage } from '@/hooks/useI18n'
import { useConfigs } from '@/hooks/useConfigs'
import { useMenus } from '@/hooks/useMenus'
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
  const { message } = App.useApp()

  const [docModalOpen, setDocModalOpen] = useState(false)
  const [registerModalOpen, setRegisterModalOpen] = useState(false)
  const [loginModalOpen, setLoginModalOpen] = useState(false)
  const { tabs, activeKey, closeTab, setActiveKey, siderCollapsed, setSiderCollapsed, colorTheme, setColorTheme, openTab, clearTabs } = useTabStore()
  const isDark = !!user && colorTheme === 'dark'
  const headerBg = isDark ? '#081A2B' : '#163E64'
  const siderBg = isDark ? '#0E2740' : '#fff'

  const { languageCd, setLanguageCd, setTranslations, resetLang } = useLangStore()
  const { data: languages = [] } = useLanguages()
  const { data: configs } = useConfigs()
  const { data: translationsData } = useTranslations(languageCd)
  const setLanguageMutation = useSetLanguage()
  const { data: allMenus = [] } = useMenus()

  // re-render 트리거용 구독
  useLangStore((s) => s.translations)

  const isLoggedIn = !!user

  const openMyInfoInTab = () => {
    const menu = allMenus.find((m) => m.route_path === 'myinfo')
    if (menu) {
      openTab({ key: menu.menucd, label: t(`mnu.${menu.menucd}`, menu.default_text), path: 'myinfo' })
    } else {
      openTab({ key: 'myinfo', label: '내 계정', path: 'myinfo' })
    }
    navigate('/myinfo')
  }

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
    clearTabs()
    resetLang()
    clearAuth()
    navigate('/')
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {/* 좌측 Sidebar */}
      {isLoggedIn && <Sider
        collapsible
        trigger={null}
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
          background: siderBg,
          borderRight: isDark ? '1px solid #1a5080' : '1px solid #e8e8e8',
          overflow: 'hidden',
        }}
        theme={isDark ? 'dark' : 'light'}
      >
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          {/* 로고 */}
          <div
            className="sidebar-logo"
            onClick={() => navigate('/')}
            style={{ borderBottom: isDark ? '1px solid #1a5080' : '1px solid #e8e8e8' }}
          >
            {user?.tenanticonurl && (
              <img
                src={user.tenanticonurl}
                alt="로고"
                style={{ height: 28, width: 'auto', flexShrink: 0 }}
              />
            )}
            {!siderCollapsed && (
              <Text strong style={{ color: isDark ? '#fff' : '#163E64', fontSize: 16, whiteSpace: 'nowrap' }}>
                SmartDocu
              </Text>
            )}
          </div>

          {/* 메뉴 영역 (스크롤 가능) */}
          <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
            <AppSidebar collapsed={siderCollapsed} isDark={isDark} />
          </div>

          {/* Collapse 버튼 */}
          <div
            onClick={() => setSiderCollapsed(!siderCollapsed)}
            style={{
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              height: 40,
              cursor: 'pointer',
              borderTop: isDark ? '1px solid #1a5080' : '1px solid #e8e8e8',
              color: isDark ? '#aaa' : '#888',
              fontSize: 12,
              userSelect: 'none',
            }}
          >
            {siderCollapsed ? <RightOutlined /> : <LeftOutlined />}
          </div>

          {/* Copyright — Footer 대체 */}
          <div
            className="sidebar-copyright"
            style={{ color: isDark ? '#aaa' : undefined, borderTop: isDark ? '1px solid #1a5080' : undefined }}
          >
            {siderCollapsed
              ? <span title="© SmartDocu 2025"></span>
              : '© SmartDocu 2025. All rights reserved.'
            }
          </div>
        </div>
      </Sider>}

      {/* 오른쪽 메인 영역 */}
      <Layout style={{ marginLeft: isLoggedIn ? (siderCollapsed ? 50 : 300) : 0, transition: 'margin-left 0.2s' }}>
        <Header
          style={{
            position: 'fixed',
            top: 0,
            left: isLoggedIn ? (siderCollapsed ? 50 : 300) : 0,
            right: 0,
            zIndex: 10,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 24px',
            background: headerBg,
            height: 60,
            transition: 'left 0.2s',
          }}
        >
          {/* 로고 + 이름 */}
          <div
            onClick={() => navigate('/')}
            style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}
          >
            <img src="/SmartDocu.svg" alt="로고" style={{ height: 32, width: 'auto' }} />
            <Text strong style={{ color: '#fff', fontSize: 18 }}>SmartDocu</Text>
          </div>

          {/* 비로그인 공개 메뉴 */}
          {!isLoggedIn && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {[
                { path: 'service', label: '서비스 소개', icon: <HomeOutlined /> },
                { path: 'about',   label: '기능 소개',   icon: <InfoCircleOutlined /> },
                { path: 'usage',   label: '서비스 이용', icon: <ReadOutlined /> },
              ].map(({ path, label, icon }) => (
                <button
                  key={path}
                  onClick={() => navigate('/' + path)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: '#fff',
                    fontSize: 14,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '6px 14px',
                    borderRadius: 4,
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.12)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
                >
                  {icon}{label}
                </button>
              ))}
            </div>
          )}

          {/* 사용자 영역 */}
          <div style={{ display: 'flex', alignItems: 'center', whiteSpace: 'nowrap' }}>
            {/* 문서 선택 */}
            {isLoggedIn && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
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
              </div>
            )}

            {/* 언어 선택기 — 지구본 + Select 붙이기 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 2, marginLeft: isLoggedIn ? 30 : 0 }}>
              <GlobalOutlined style={{ color: '#fff', fontSize: 16 }} />
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
            </div>

            {isLoggedIn ? (
              <>
                {/* 알람 */}
                <div style={{ marginLeft: 20 }}>
                  <Badge count={3} size="small">
                    <BellOutlined
                      style={{ color: '#fff', fontSize: 18, cursor: 'pointer' }}
                      onClick={() => message.info('알림 기능은 추후 제공될 예정입니다.')}
                    />
                  </Badge>
                </div>
                {/* 사람 아이콘 */}
                <Dropdown
                  menu={{
                    items: [
                      {
                        key: 'myinfo',
                        label: user?.email ?? '사용자',
                        onClick: openMyInfoInTab,
                      },
                      { type: 'divider' },
                      {
                        key: 'theme',
                        label: (
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span style={{ marginRight: 4 }}>{t('lbl.theme')}</span>
                            <span
                              onClick={(e) => { e.stopPropagation(); setColorTheme('light') }}
                              style={{
                                cursor: 'pointer',
                                padding: '2px 10px',
                                borderRadius: 4,
                                fontSize: 12,
                                fontWeight: !isDark ? 600 : 400,
                                backgroundColor: !isDark ? '#245F97' : 'transparent',
                                color: !isDark ? '#fff' : '#888',
                                border: !isDark ? '1px solid #245F97' : '1px solid #d9d9d9',
                              }}
                            >Light</span>
                            <span
                              onClick={(e) => { e.stopPropagation(); setColorTheme('dark') }}
                              style={{
                                cursor: 'pointer',
                                padding: '2px 10px',
                                borderRadius: 4,
                                fontSize: 12,
                                fontWeight: isDark ? 600 : 400,
                                backgroundColor: isDark ? '#245F97' : 'transparent',
                                color: isDark ? '#fff' : '#888',
                                border: isDark ? '1px solid #245F97' : '1px solid #d9d9d9',
                              }}
                            >Dark</span>
                          </div>
                        ),
                      },
                      { type: 'divider' },
                      { key: 'logout', label: t('btn.logout'), onClick: handleLogout },
                    ],
                  }}
                  trigger={['click']}
                  placement="bottomRight"
                >
                  <UserOutlined style={{ color: '#fff', fontSize: 20, cursor: 'pointer', marginLeft: 20 }} />
                </Dropdown>
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
                    marginLeft: 12,
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
                    marginLeft: 8,
                  }}
                >
                  {t('btn.login')}
                </button>
              </>
            )}
          </div>
        </Header>

        {/* 탭 바 */}
        {tabs.length > 0 && (
          <div
            style={{
              position: 'fixed',
              top: 60,
              left: isLoggedIn ? (siderCollapsed ? 50 : 300) : 0,
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
              items={tabs.map((tab) => ({ key: tab.key, label: t(`mnu.${tab.key}`, tab.label), closable: true }))}
              style={{ marginBottom: 0 }}
              className={isDark ? 'tabs-dark' : 'tabs-light'}
            />
          </div>
        )}

        <Content style={{ marginTop: tabs.length > 0 ? 104 : 60, padding: '0 24px 24px', minHeight: 'calc(100vh - 60px)', display: 'flex', flexDirection: 'column' }}>
          <div style={{ background: cssToken.colorBgContainer, borderRadius: cssToken.borderRadius, padding: '12px 24px 24px', flex: 1 }}>
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
