import { Outlet, useNavigate, useLocation, useParams } from 'react-router-dom'
import { Layout, Typography, Space, theme, Tabs, Select, Badge, Dropdown, App, Modal, Popover, Input, Spin } from 'antd'
import { useQueryClient } from '@tanstack/react-query'
import QRCode from 'qrcode'
import apiClient from '@/api/client'
import { useMfaEnroll, useMfaEnrollVerify } from '@/hooks/useMfa'
import { GlobalOutlined, BellOutlined, UserOutlined, HomeOutlined, InfoCircleOutlined, ReadOutlined, LeftOutlined, RightOutlined, QuestionCircleOutlined, FolderOutlined, AppstoreOutlined } from '@ant-design/icons'
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
import { useHelpSearch } from '@/hooks/useAdmin'
import { useDatasProjects, useUpdateMyProject } from '@/hooks/useDatas'
import { useApps } from '@/hooks/useApps'
import { useNotifications, navigateToNotificationTarget } from '@/hooks/useNotifications'

function canSeeApp(app, user, subscribedServicecds) {
  const { rolecd, servicecd } = app
  if (!user) return false
  if (servicecd) return subscribedServicecds.includes(servicecd)
  if (rolecd === 'S') return user.roleid === 7
  if (!rolecd) return user.projectmanager === 'Y' || user.tenantmanager === 'Y' || user.accountmanager === 'Y'
  return false
}

const { Header, Content, Sider } = Layout
const { Text } = Typography

export default function AppLayout() {
  const navigate = useNavigate()
  const { appcd } = useParams()
  const { token: cssToken } = theme.useToken()
  const { user, clearAuth, updateUser, switchTenant, updateTokens } = useAuthStore()
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()

  const location = useLocation()
  const [docModalOpen, setDocModalOpen] = useState(false)
  const [registerModalOpen, setRegisterModalOpen] = useState(false)
  const [loginModalOpen, setLoginModalOpen] = useState(false)
  const [helpModalOpen, setHelpModalOpen] = useState(false)
  const [mfaChallenge, setMfaChallenge] = useState(null) // { tenantid, tenant, factor_id, code }
  const [tenantSwitching, setTenantSwitching] = useState(false)
  const [mfaSetupModal, setMfaSetupModal] = useState(null) // { tenantid, tenant }
  const [mfaSetupData, setMfaSetupData] = useState(null) // { factor_id, totp_uri, secret }
  const [mfaSetupQr, setMfaSetupQr] = useState('')
  const [mfaSetupCode, setMfaSetupCode] = useState('')
  const mfaSetupEnroll = useMfaEnroll()
  const mfaSetupVerify = useMfaEnrollVerify()
  const { tabs, activeKey, closeTab, setActiveKey, siderCollapsed, setSiderCollapsed, colorTheme, setColorTheme, openTab, clearTabs, closeOtherTabs, closeLeftTabs, closeRightTabs } = useTabStore()
  const isDark = !!user && colorTheme === 'dark'
  const headerBg = isDark ? '#081A2B' : '#163E64'
  const siderBg = isDark ? '#0E2740' : '#fff'

  const { languageCd, setLanguageCd, setTranslations, resetLang } = useLangStore()
  const { data: languages = [] } = useLanguages()
  const { data: configs } = useConfigs()
  const { data: translationsData } = useTranslations(languageCd)
  const setLanguageMutation = useSetLanguage()
  const { data: allMenus = [] } = useMenus(appcd)
  const { data: helpData } = useHelpSearch(location.pathname, languageCd || 'en')
  const helpItem = helpData?.help ?? null
  const { data: { apps = [], subscribed_servicecds = [] } = {} } = useApps({ enabled: !!user, tenantid: user?.tenantid })
  const currentServicecd = apps.find((a) => a.appcd === appcd)?.servicecd
  const { data: projectsData } = useDatasProjects({ enabled: !!user, servicecd: currentServicecd })
  const projectList = projectsData?.projects || []
  const updateMyProject = useUpdateMyProject()
  const [selectedProjectId, setSelectedProjectId] = useState(null)
  const [appLauncherOpen, setAppLauncherOpen] = useState(false)
  const [notificationOpen, setNotificationOpen] = useState(false)
  const { data: notificationsData } = useNotifications()
  const notifications = notificationsData?.notifications || []
  const unreadCount = notificationsData?.unread_count || 0

  useEffect(() => {
    if (!currentServicecd || projectList.length === 0) return
    const saved = projectsData?.myprojectid
    const found = saved && projectList.find(p => String(p.projectid) === String(saved))
    const resolved = found ? found.projectid : projectList[0].projectid
    setSelectedProjectId(resolved)
	updateUser({ myprojectid: String(resolved) })
    if (String(resolved) !== String(saved ?? '')) {
      updateMyProject.mutate({ myprojectid: String(resolved), servicecd: currentServicecd })
    }
  }, [projectList, projectsData?.myprojectid, currentServicecd])


  // re-render 트리거용 구독
  useLangStore((s) => s.translations)

  const isLoggedIn = !!user
  const showSidebar = isLoggedIn && location.pathname !== '/launcher'

  const openMyInfoInTab = () => {
    const effectiveAppcd = appcd || apps[0]?.appcd
    const tabPath = effectiveAppcd ? `app/${effectiveAppcd}/myinfo` : 'myinfo'
    const navPath = effectiveAppcd ? `/app/${effectiveAppcd}/myinfo` : '/myinfo'
    const menu = allMenus.find((m) => m.route_path === 'myinfo')
    if (menu) {
      openTab({ key: menu.menucd, label: t(`mnu.${menu.menucd}`, menu.default_text || 'My Info'), labelKey: `mnu.${menu.menucd}`, path: tabPath })
    } else {
      openTab({ key: 'myinfo', label: t('ttl.myinfo.personal', 'My Info') || 'My Info', labelKey: 'ttl.myinfo.personal', path: tabPath })
    }
    navigate(navPath)
  }

  // launcher 화면(appcd 없음)에서도 알림 클릭이 동작해야 하므로 openMyInfoInTab과 동일하게
  // effectiveAppcd(현재 appcd 없으면 첫 번째 앱)로 폴백해서 이동한다 — useOpenInTab은 appcd가
  // 없으면 /app/:appcd 하위에만 등록된 라우트로 못 감(그냥 launcher로 리다이렉트됨).
  const openAppRouteInTab = (routePath, query = '', fallbackLabel = '') => {
    const effectiveAppcd = appcd || apps[0]?.appcd
    const tabPath = effectiveAppcd ? `app/${effectiveAppcd}/${routePath}${query}` : `${routePath}${query}`
    const navPath = effectiveAppcd ? `/app/${effectiveAppcd}/${routePath}${query}` : `/${routePath}${query}`
    const menu = allMenus.find((m) => m.route_path === routePath)
    if (menu) {
      openTab({ key: menu.menucd, label: t(`mnu.${menu.menucd}`, menu.default_text || fallbackLabel), labelKey: `mnu.${menu.menucd}`, path: tabPath })
    } else {
      openTab({ key: routePath, label: fallbackLabel, path: tabPath })
    }
    navigate(navPath)
  }

  const handleNotificationClick = (n) => {
    setNotificationOpen(false)
    navigateToNotificationTarget(n, openAppRouteInTab)
  }

  const handleNotificationListClick = () => {
    setNotificationOpen(false)
    openAppRouteInTab('notifications', '', t('ttl.notifications'))
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

  const _finishTenantSwitch = (tenantid, tenant, data) => {
    switchTenant(tenantid)
    updateUser({
      tenantnm: data.tenantnm ?? tenant?.tenantnm,
      disptenantnm: data.disptenantnm ?? data.tenantnm ?? tenant?.tenantnm,
      tenanticonurl: data.tenanticonurl ?? tenant?.tenanticonurl,
      accountuid: data.accountuid ?? null,
      tenantmanager: data.tenantmanager ?? 'N',
      accountmanager: data.accountmanager ?? 'N',
    })
    queryClient.invalidateQueries()
    clearTabs()
    navigate('/launcher')
  }

  const _attemptSwitchTenant = async (tenantid, tenant) => {
    setTenantSwitching(true)
    try {
      const res = await apiClient.post('/auth/switch-tenant', {
        tenantid,
        refresh_token: useAuthStore.getState().refreshToken,
      })

      if (res.data.mfa_setup_required) {
        setMfaSetupModal({ tenantid, tenant })
        return
      }
      if (res.data.mfa_required) {
        setMfaChallenge({ tenantid, tenant, factor_id: res.data.factor_id, code: '' })
        return
      }

      _finishTenantSwitch(tenantid, tenant, res.data)
    } catch (e) {
      const detail = e.response?.data?.detail
      message.error(detail ? t(detail) : t('msg.tenant.switch.error'))
    } finally {
      setTenantSwitching(false)
    }
  }

  const handleTenantChange = (tenantid) => {
    const tenant = user?.tenants?.find((t) => String(t.tenantid) === String(tenantid))
    modal.confirm({
      title: t('msg.tenant.switch.confirm'),
      content: t('msg.tenant.switch.desc'),
      okText: t('btn.confirm'),
      cancelText: t('btn.cancel'),
      onOk: () => _attemptSwitchTenant(tenantid, tenant),
    })
  }

  const handleMfaChallengeVerify = async () => {
    if (!mfaChallenge || mfaChallenge.code.length !== 6) return
    const { accessToken, refreshToken } = useAuthStore.getState()
    setTenantSwitching(true)
    try {
      const res = await apiClient.post('/auth/mfa-verify', {
        factor_id: mfaChallenge.factor_id,
        code: mfaChallenge.code,
        access_token: accessToken,
        refresh_token: refreshToken,
        tenantid: mfaChallenge.tenantid,
      })
      updateTokens({ accessToken: res.data.access_token, refreshToken: res.data.refresh_token })
      const { tenantid, tenant } = mfaChallenge
      setMfaChallenge(null)
      _finishTenantSwitch(tenantid, tenant, res.data.user || {})
    } catch (e) {
      message.error(t('msg.mfa.code_invalid'))
      setMfaChallenge((c) => (c ? { ...c, code: '' } : c))
    } finally {
      setTenantSwitching(false)
    }
  }

  // 강제 MFA 설정 모달 진입 시 자동으로 enroll 시작 (라우팅/탭 전환에 기대지 않고 모달 안에서 바로 처리)
  useEffect(() => {
    if (!mfaSetupModal) { setMfaSetupData(null); setMfaSetupQr(''); setMfaSetupCode(''); return }
    mfaSetupEnroll.mutate(undefined, { onSuccess: (data) => setMfaSetupData(data) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mfaSetupModal])

  useEffect(() => {
    if (!mfaSetupData?.totp_uri) { setMfaSetupQr(''); return }
    QRCode.toDataURL(mfaSetupData.totp_uri, { width: 160, margin: 2 })
      .then(setMfaSetupQr)
      .catch(() => setMfaSetupQr(''))
  }, [mfaSetupData])

  const handleMfaSetupVerify = () => {
    if (!mfaSetupData || mfaSetupCode.length !== 6) return
    mfaSetupVerify.mutate(
      { factor_id: mfaSetupData.factor_id, code: mfaSetupCode },
      {
        onSuccess: (data) => {
          if (data.access_token) {
            updateTokens({ accessToken: data.access_token, refreshToken: data.refresh_token || useAuthStore.getState().refreshToken })
          }
          const { tenantid, tenant } = mfaSetupModal
          setMfaSetupModal(null)
          _attemptSwitchTenant(tenantid, tenant)
        },
        onError: () => setMfaSetupCode(''),
      },
    )
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {/* 좌측 Sidebar */}
      {showSidebar && <Sider
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
            onClick={() => navigate(isLoggedIn ? '/launcher' : '/')}
            style={{ borderBottom: isDark ? '1px solid #1a5080' : '1px solid #e8e8e8' }}
          >
            {user?.tenanticonurl && (
              <img
                src={user.tenanticonurl}
                alt=""
                style={{ height: 28, width: 'auto', flexShrink: 0 }}
              />
            )}
            {!siderCollapsed && (
              <Text
                strong
                style={{
                  color: isDark ? '#fff' : '#163E64', fontSize: 16, whiteSpace: 'nowrap',
                  overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0, flex: '1 1 0',
                }}
                title={user?.disptenantnm || user?.tenantnm || 'D2Doc'}
              >
                {user?.disptenantnm || user?.tenantnm || 'D2Doc'}
              </Text>
            )}
          </div>

          {/* 메뉴 영역 (스크롤 가능) */}
          <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
            <AppSidebar collapsed={siderCollapsed} isDark={isDark} appcd={appcd} />
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
              ? <span title="© D2Doc 2025"></span>
              : '© D2Doc 2025. All rights reserved.'
            }
          </div>
        </div>
      </Sider>}

      {/* 오른쪽 메인 영역 */}
      <Layout style={{ marginLeft: showSidebar ? (siderCollapsed ? 50 : 300) : 0, transition: 'margin-left 0.2s' }}>
        <Header
          style={{
            position: 'fixed',
            top: 0,
            left: showSidebar ? (siderCollapsed ? 50 : 300) : 0,
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
            onClick={() => { clearTabs(); navigate(isLoggedIn ? '/launcher' : '/') }}
            style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}
          >
            <img src="/D2Doc.svg" alt="" style={{ height: 32, width: 'auto' }} />
            <Text strong style={{ color: '#fff', fontSize: 18 }}>D2Doc</Text>
          </div>

          {/* 공개 메뉴 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {[
                { path: 'service', label: t('mnu.service'), icon: <HomeOutlined /> },
                { path: 'about',   label: t('mnu.about'),   icon: <InfoCircleOutlined /> },
                { path: 'usage',   label: t('mnu.usage'),   icon: <ReadOutlined /> },
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

          {/* 사용자 영역 */}
          <div style={{ display: 'flex', alignItems: 'center', whiteSpace: 'nowrap' }}>
            {/* 테넌트 선택 (멀티테넌트 사용자만) */}
            {isLoggedIn && user?.tenants?.length >= 2 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 2, marginRight: 8 }}>
                <Select
                  value={user?.tenantid || undefined}
                  onChange={handleTenantChange}
                  size="small"
                  variant="borderless"
                  style={{ minWidth: 120, color: '#fff' }}
                  popupMatchSelectWidth={false}
                  options={user.tenants.map((t) => ({ value: t.tenantid, label: t.tenantnm }))}
                  className="lang-select"
                />
              </div>
            )}

            {/* 프로젝트 선택 */}
            {isLoggedIn && projectList.length > 0 && (appcd === 'D2CHAT' || appcd === 'D2INSIGHT') && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <Select
                  value={selectedProjectId || undefined}
                  onChange={(val) => {
                    setSelectedProjectId(val)
					updateUser({ myprojectid: String(val) })
                    updateMyProject.mutate({ myprojectid: String(val), servicecd: currentServicecd })
                  }}
                  size="small"
                  variant="borderless"
                  style={{ minWidth: 120, color: '#fff' }}
                  popupMatchSelectWidth={false}
                  options={projectList.map(p => ({ value: p.projectid, label: p.projectnm }))}
                  className="lang-select"
                />
              </div>
            )}

            {/* 문서 선택 */}
            {isLoggedIn && appcd === 'D2DOC' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 20 }}>
                <img
                  src="/doc-select.svg"
                  alt={t('ttl.doc.select')}
                  title={t('ttl.doc.select')}
                  onClick={() => setDocModalOpen(true)}
                  style={{ width: 20, height: 20, cursor: 'pointer', filter: 'invert(100%) brightness(250%) contrast(150%)' }}
                />
                {user?.docnm && (
                  <span style={{ color: '#fff', fontSize: 14, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {user.docnm}
                  </span>
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
                {/* 앱 런처 */}
                <Popover
                  open={appLauncherOpen}
                  onOpenChange={setAppLauncherOpen}
                  trigger="click"
                  placement="bottomRight"
                  content={
                    <div style={{ width: 340, padding: 4 }}>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
                        {apps.filter((a) => canSeeApp(a, user, subscribed_servicecds)).map((app) => (
                          <div
                            key={app.appcd}
                            onClick={() => {
                              setAppLauncherOpen(false)
                              clearTabs()
                              navigate(`/app/${app.appcd}`)
                            }}
                            style={{
                              textAlign: 'center',
                              padding: '14px 8px 10px',
                              borderRadius: 8,
                              cursor: 'pointer',
                              border: `2px solid ${app.appcd === appcd ? '#163E64' : 'transparent'}`,
                              background: app.appcd === appcd ? '#f0f4f8' : 'transparent',
                              transition: 'all 0.15s',
                            }}
                            onMouseEnter={(e) => {
                              if (app.appcd !== appcd) {
                                e.currentTarget.style.background = '#f5f5f5'
                                e.currentTarget.style.borderColor = '#d0d0d0'
                              }
                            }}
                            onMouseLeave={(e) => {
                              if (app.appcd !== appcd) {
                                e.currentTarget.style.background = 'transparent'
                                e.currentTarget.style.borderColor = 'transparent'
                              }
                            }}
                          >
                            {app.iconurl ? (
                              <img src={app.iconurl} alt={app.appnm} style={{ width: 32, height: 32, marginBottom: 6, objectFit: 'contain' }} />
                            ) : (
                              <AppstoreOutlined style={{ fontSize: 28, color: '#163E64', marginBottom: 6, display: 'block' }} />
                            )}
                            <div style={{ fontSize: 12, fontWeight: 600, color: '#163E64', lineHeight: 1.3 }}>{app.appnm}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  }
                >
                  <AppstoreOutlined style={{ color: '#fff', fontSize: 20, cursor: 'pointer', marginLeft: 20 }} />
                </Popover>

                {/* 알람 */}
                <Popover
                  open={notificationOpen}
                  onOpenChange={setNotificationOpen}
                  trigger="click"
                  placement="bottomRight"
                  content={
                    <div style={{ width: 320 }}>
                      <div style={{ maxHeight: 360, overflowY: 'auto', background: '#fff' }}>
                        {notifications.length === 0 ? (
                          <div style={{ padding: '24px 8px', textAlign: 'center', color: '#999' }}>
                            {t('msg.notification.empty')}
                          </div>
                        ) : (
                          notifications.map((n) => (
                            <div
                              key={n.notificationuid}
                              onClick={() => handleNotificationClick(n)}
                              style={{
                                padding: '16px 8px',
                                marginBottom: 6,
                                borderRadius: 6,
                                cursor: 'pointer',
                                background: n.is_read ? 'transparent' : '#f0f6ff',
                              }}
                            >
                              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                {!n.is_read && <span style={{ width: 6, height: 6, borderRadius: '50%', background: n.notificationstatus === 'error' ? '#dc3545' : '#245F97', flexShrink: 0 }} />}
                                <span style={{ fontWeight: n.is_read ? 400 : 600, fontSize: 13 }}>{n.title}</span>
                              </div>
                              <div style={{ fontSize: 12, color: '#666', marginTop: 6 }}>{n.message}</div>
                              <div style={{ fontSize: 11, color: '#aaa', marginTop: 6 }}>{n.createdts}</div>
                            </div>
                          ))
                        )}
                      </div>
                      <div
                        onClick={handleNotificationListClick}
                        style={{
                          padding: '10px 8px',
                          textAlign: 'center',
                          fontSize: 13,
                          color: '#245F97',
                          fontWeight: 600,
                          cursor: 'pointer',
                          borderTop: '1px solid #f0f0f0',
                        }}
                      >
                        {t('btn.notification.list')}
                      </div>
                    </div>
                  }
                >
                  <div style={{ marginLeft: 20 }}>
                    <Badge count={unreadCount} size="small">
                      <BellOutlined style={{ color: '#fff', fontSize: 18, cursor: 'pointer' }} />
                    </Badge>
                  </div>
                </Popover>
                {/* 사람 아이콘 */}
                <Dropdown
                  menu={{
                    items: [
                      {
                        key: 'myinfo',
                        label: user?.email,
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
                  {t('btn.register_btn')}
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
                  {t('btn.login_btn')}
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
              left: showSidebar ? (siderCollapsed ? 50 : 300) : 0,
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
                    else navigate(isLoggedIn ? '/launcher' : '/')
                  }
                }
              }}
              items={tabs.map((tab, idx) => {
                const isFirst = idx === 0
                const isLast = idx === tabs.length - 1
                const isSingle = tabs.length === 1
                const contextMenu = {
                  items: [
                    {
                      key: 'close-this',
                      label: t('btn.tab.close.this', 'Close Tab'),
                      disabled: isSingle,
                      onClick: () => {
                        const nextTab = tabs[idx + 1] ?? tabs[idx - 1] ?? null
                        closeTab(tab.key)
                        if (activeKey === tab.key) {
                          if (nextTab) navigate('/' + nextTab.path)
                          else navigate(isLoggedIn ? '/launcher' : '/')
                        }
                      },
                    },
                    {
                      key: 'close-others',
                      label: t('btn.tab.close.others', 'Close Other Tabs'),
                      disabled: isSingle,
                      onClick: () => {
                        closeOtherTabs(tab.key)
                        if (activeKey !== tab.key) navigate('/' + tab.path)
                      },
                    },
                    {
                      key: 'close-left',
                      label: t('btn.tab.close.left', 'Close Tabs to Left'),
                      disabled: isFirst,
                      onClick: () => {
                        const wasActiveRemoved = !tabs.slice(idx).find((t) => t.key === activeKey)
                        closeLeftTabs(tab.key)
                        if (wasActiveRemoved) navigate('/' + tab.path)
                      },
                    },
                    {
                      key: 'close-right',
                      label: t('btn.tab.close.right', 'Close Tabs to Right'),
                      disabled: isLast,
                      onClick: () => {
                        const wasActiveRemoved = !tabs.slice(0, idx + 1).find((t) => t.key === activeKey)
                        closeRightTabs(tab.key)
                        if (wasActiveRemoved) navigate('/' + tab.path)
                      },
                    },
                  ],
                }
                return {
                  key: tab.key,
                  label: (
                    <Dropdown trigger={['contextMenu']} menu={contextMenu}>
                      <span>{tab.labelKey ? t(tab.labelKey, tab.label) : t(`mnu.${tab.key}`, tab.label)}</span>
                    </Dropdown>
                  ),
                  closable: true,
                }
              })}
              style={{ marginBottom: 0 }}
              className={isDark ? 'tabs-dark' : 'tabs-light'}
            />
          </div>
        )}

        <Content style={{ marginTop: tabs.length > 0 ? 104 : 60, padding: '0 24px 24px', minHeight: tabs.length > 0 ? 'calc(95vh - 104px)' : 'calc(95vh - 60px)', display: 'flex', flexDirection: 'column' }}>
          <div style={{ background: cssToken.colorBgContainer, borderRadius: cssToken.borderRadius, padding: '12px 24px 24px', flex: 1, position: 'relative' }}>
            {helpItem && (
              <div style={{ position: 'absolute', top: 21, right: 2, zIndex: 1 }}>
                <QuestionCircleOutlined
                  style={{ fontSize: 20, cursor: 'pointer', color: '#8c8c8c' }}
                  onClick={() => setHelpModalOpen(true)}
                  title={t('ttl.help')}
                />
              </div>
            )}
            <Outlet />
          </div>
        </Content>
      </Layout>

      <DocSelectModal open={docModalOpen} onClose={() => setDocModalOpen(false)} />
      <RegisterModal open={registerModalOpen} onClose={() => setRegisterModalOpen(false)} />
      <LoginModal open={loginModalOpen} onClose={() => setLoginModalOpen(false)} />

      {/* 테넌트 전환 진행 중 오버레이 — MFA 모달이 닫힌 뒤 실제 전환까지의 공백 구간 안내 */}
      {tenantSwitching && (
        <div style={{
          position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
          background: 'rgba(0,0,0,0.5)',
          display: 'flex', justifyContent: 'center', alignItems: 'center',
          zIndex: 10000,
        }}>
          <div style={{
            background: '#fafae5', padding: '20px 30px', borderRadius: 8,
            fontSize: 16, fontWeight: 'bold', color: '#6c757d',
            boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
            display: 'flex', alignItems: 'center', gap: 12,
          }}>
            <Spin />
            <span>{t('msg.tenant.switching')}</span>
          </div>
        </div>
      )}

      <Modal
        title={t('ttl.mfa.verify')}
        open={!!mfaChallenge}
        onCancel={() => setMfaChallenge(null)}
        footer={null}
        width={320}
      >
        <div style={{ textAlign: 'center', padding: '12px 0' }}>
          <Input
            value={mfaChallenge?.code || ''}
            onChange={(e) => setMfaChallenge((c) => (c ? { ...c, code: e.target.value.replace(/\D/g, '').slice(0, 6) } : c))}
            onPressEnter={handleMfaChallengeVerify}
            maxLength={6}
            style={{ width: 160, textAlign: 'center', letterSpacing: 8, fontFamily: 'monospace', fontSize: 20, margin: '0 auto 16px', display: 'block' }}
            placeholder="000000"
          />
          <button
            className="btn btn-primary"
            type="button"
            onClick={handleMfaChallengeVerify}
            disabled={(mfaChallenge?.code || '').length !== 6}
          >
            {t('ttl.mfa.verify')}
          </button>
        </div>
      </Modal>

      <Modal
        title={t('ttl.mfa.setup')}
        open={!!mfaSetupModal}
        onCancel={() => setMfaSetupModal(null)}
        footer={null}
        width={360}
      >
        <div style={{ textAlign: 'center', padding: '8px 0' }}>
          <div style={{ fontSize: 13, color: '#888', marginBottom: 16, textAlign: 'left' }}>
            {t('msg.mfa.setup_required')}
          </div>
          {mfaSetupQr && (
            <img
              src={mfaSetupQr}
              alt="QR Code"
              style={{ width: 160, height: 160, border: '1px solid #f0f0f0', borderRadius: 8, marginBottom: 12 }}
            />
          )}
          {mfaSetupData?.secret && (
            <div style={{ fontFamily: 'monospace', fontSize: 12, color: '#666', marginBottom: 16, wordBreak: 'break-all' }}>
              {mfaSetupData.secret}
            </div>
          )}
          <Input
            value={mfaSetupCode}
            onChange={(e) => setMfaSetupCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            onPressEnter={handleMfaSetupVerify}
            maxLength={6}
            style={{ width: 160, textAlign: 'center', letterSpacing: 8, fontFamily: 'monospace', fontSize: 20, margin: '0 auto 16px', display: 'block' }}
            placeholder="000000"
          />
          <button
            className="btn btn-primary"
            type="button"
            onClick={handleMfaSetupVerify}
            disabled={mfaSetupCode.length !== 6 || !mfaSetupData}
          >
            {t('btn.mfa.activate')}
          </button>
        </div>
      </Modal>

      <Modal
        title={<div style={{ textAlign: 'center' }}>{helpItem?.help}</div>}
        open={helpModalOpen}
        onCancel={() => setHelpModalOpen(false)}
        footer={null}
        width={640}
      >
        <div
          style={{ padding: '8px 0', lineHeight: 1.7 }}
          dangerouslySetInnerHTML={{ __html: helpItem?.desc || '' }}
        />
      </Modal>
    </Layout>
  )
}
