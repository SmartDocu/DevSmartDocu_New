import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Typography, Space, Button, theme } from 'antd'
import { useAuthStore } from '@/stores/authStore'
import DocSelectModal from '@/components/DocSelectModal/DocSelectModal'
import RegisterModal from '@/components/RegisterModal/RegisterModal'
import LoginModal from '@/components/LoginModal/LoginModal'
import { useState } from 'react'

const { Header, Content, Footer } = Layout
const { Text } = Typography

/* ── 서브메뉴 설명 렌더링 헬퍼 ── */
function PanelDesc({ lines }) {
  return (
    <div className="app-menu-desc">
      {lines.map((line, i) => (
        <span key={i}>
          {line === '' ? <br /> : line}
          {line !== '' && <br />}
        </span>
      ))}
    </div>
  )
}

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { token: cssToken } = theme.useToken()
  const { user, clearAuth } = useAuthStore()

  const [docModalOpen, setDocModalOpen] = useState(false)
  const [registerModalOpen, setRegisterModalOpen] = useState(false)
  const [loginModalOpen, setLoginModalOpen] = useState(false)

  const isLoggedIn = !!user
  const sampledocyn = user?.sampledocyn
  const projectmanager = user?.projectmanager
  const tenantmanager = user?.tenantmanager
  const roleid = user?.roleid
  const billingmodelcd = user?.billingmodelcd
  const notFreeOrPro = billingmodelcd !== 'Fr' && billingmodelcd !== 'Pr'

  /* ── 네비게이션 아이템 구성 ── */
  const navItems = []

  navItems.push({ key: '/service', label: '서비스 소개' })
  navItems.push({ key: '/about', label: '기능 소개' })
  navItems.push({ key: '/usage', label: '서비스 이용' })

  if (isLoggedIn) {
    navItems.push({ key: '/req/list', label: '문서' })

    if (sampledocyn === 'Y' || projectmanager === 'Y' || roleid === 7) {
      navItems.push({
        key: 'master',
        label: '기준 정보',
        panelDesc: [
          '문서, 챕터, 항목, 데이터 등 문서를 작성하기 위한 기준 정보를 관리합니다.',
          '',
          '문서 : 문서의 기준 관리',
          '\u00a0└ 챕터 : 챕터 구성 템플릿 관리',
          '\u00a0\u00a0\u00a0└ 항목 : 문장, 표, 차트 구성',
        ],
        children: [
          { key: '/master/docs',     label: '문서 관리',    desc: '작성할 문서명, 매개변수 등을 관리' },
          { key: '/master/chapters', label: '챕터 관리',    desc: '주제별로 분할하고 템플릿을 설정' },
          { key: '/master/object',   label: '항목 관리',    desc: '문장, 표, 차트를 작성하기 위한 설정' },
          { key: '/master/datas/ex', label: 'Excel 데이터', desc: '항목에서 사용할 Excel, CSV 자료를 등록' },
          { key: '/master/datas/ai', label: 'AI 데이터',    desc: 'AI 프롬프트로 DB 또는 Excel 자료를 재가공' },
        ],
      })
    }

    if (roleid === 7 || (notFreeOrPro && (tenantmanager === 'Y' || projectmanager === 'Y'))) {
      const projectChildren = []
      if (tenantmanager === 'Y' || roleid === 7) {
        projectChildren.push({ key: '/org/tenant-users', label: '기업 사용자 관리' })
        if (roleid === 7) {
          projectChildren.push({ key: '/org/tenant-llms', label: '기업 LLM 관리' })
        }
        projectChildren.push({ key: '/org/projects', label: '프로젝트 관리' })
      }
      projectChildren.push({ key: '/org/project-users', label: '프로젝트 사용자 관리' })
      navItems.push({
        key: 'org',
        label: '프로젝트 관리',
        panelDesc: [
          '기업 사용자와 기업 LLM을 포함한 프로젝트 전반의 정보 및',
          '프로젝트별 사용자 구성을 관리합니다.',
        ],
        children: projectChildren,
      })
    }

    if (roleid === 7 || (notFreeOrPro && tenantmanager === 'Y')) {
      navItems.push({
        key: 'db',
        label: 'DB 정보',
        panelDesc: ['문서 작성에 필요한 DB 연결정보와 데이터 정보를 관리합니다.'],
        children: [
          { key: '/settings/servers', label: 'DB 연결정보', desc: 'SQL, PostgreSQL 등 DB 연결정보 관리' },
          { key: '/master/datas/db',  label: 'DB 데이터',   desc: '사용할 Query 정의 및 논리 정보들을 설정' },
        ],
      })
    }

    if (roleid === 7) {
      navItems.push({
        key: 'admin',
        label: '기업관리',
        panelDesc: [
          '관리자용 메뉴 (Admin용)',
          '사용자 관리(기본) 에서 관리자/일반유저 설정 가능',
        ],
        children: [
          { key: '/admin/user-role',       label: '사용자 관리(기본)' },
          { key: '/settings/tenants',      label: '기업 관리' },
          { key: '/admin/sample-prompts',  label: '샘플 프롬프트 관리' },
          { key: '/admin/llms',            label: 'LLM 관리' },
          { key: '/admin/llmapis',         label: 'LLM API 관리' },
          { key: '/admin/tenant-requests', label: '기업 생성 요청 관리' },
          { key: '/admin/helps',           label: '도움말 관리' },
        ],
      })
      navItems.push({
        key: 'dev',
        label: '개발메뉴',
        panelDesc: ['개발자 메뉴', '개발 중 임시 메뉴'],
        children: [
          { key: 'ext-rag', label: 'RAG', external: true },
          { key: 'ext-mcp', label: 'MCP', external: true },
        ],
      })
    }
  }

  const handleNavClick = (key) => {
    if (key === 'ext-rag') { window.open('https://dev-rag-medicine.azurewebsites.net/', '_blank'); return }
    if (key === 'ext-mcp') { window.open('https://dev-mcp-rtims.azurewebsites.net/', '_blank'); return }
    if (key.startsWith('/')) navigate(key)
  }

  const handleLogout = () => {
    clearAuth()
    navigate('/')
  }

  /* ── active 판단 ── */
  const isActive = (item) => {
    if (item.children) {
      return item.children.some(c => c.key.startsWith('/') && location.pathname.startsWith(c.key))
    }
    return location.pathname === item.key
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header
        style={{
          position: 'fixed',
          top: 0, left: 0, right: 0,
          zIndex: 10,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 24px',
          background: '#163E64',
          height: 60,
          overflow: 'visible',
        }}
      >
        {/* 로고 + 메뉴 */}
        <div style={{ display: 'flex', alignItems: 'center', flex: 1, minWidth: 0, overflow: 'visible', height: '100%' }}>
          <div
            onClick={() => navigate('/')}
            style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 24, cursor: 'pointer', whiteSpace: 'nowrap' }}
          >
            <img
              src={user?.tenanticonurl || '/SmartDocu.svg'}
              alt="로고"
              style={{ height: 32, width: 'auto' }}
            />
            <Text strong style={{ color: '#fff', fontSize: 18 }}>SmartDocu</Text>
          </div>

          {/* ── 커스텀 Nav 메뉴 ── */}
          <nav style={{ flex: 1, minWidth: 0, overflow: 'visible', height: '100%', display: 'flex', alignItems: 'center' }}>
            <ul className="app-nav-list">
              {navItems.map((item) => {
                const hasChildren = !!(item.children && item.children.length > 0)
                const active = isActive(item)
                return (
                  <li key={item.key} className="app-nav-item">
                    <button
                      className={`app-nav-link${active ? ' active' : ''}`}
                      onClick={() => !hasChildren && handleNavClick(item.key)}
                    >
                      {item.label}{hasChildren ? ' \u25bf' : ''}
                    </button>

                    {hasChildren && (
                      <div className="app-submenu-panel">
                        {item.panelDesc && <PanelDesc lines={item.panelDesc} />}
                        <div className="app-submenu-list">
                          <ul>
                            {item.children.map((child) => (
                              <li key={child.key}>
                                <button
                                  className="app-submenu-link"
                                  onClick={() => handleNavClick(child.key)}
                                >
                                  {child.label}
                                  {child.desc && (
                                    <>
                                      <br />
                                      <span style={{ paddingLeft: '1.2em' }}>
                                        : <small className="app-submenu-small">{child.desc}</small>
                                      </span>
                                    </>
                                  )}
                                </button>
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          </nav>
        </div>

        {/* 사용자 영역 */}
        {isLoggedIn ? (
          <Space style={{ whiteSpace: 'nowrap', marginLeft: 16 }} size={8}>
            <img
              src="/doc-select.svg"
              alt="문서 선택"
              title="문서 선택"
              onClick={() => setDocModalOpen(true)}
              style={{ width: 20, height: 20, cursor: 'pointer', filter: 'invert(100%) brightness(250%) contrast(150%)' }}
            />
            {user?.docnm && (
              <Text style={{ color: '#fff' }}>
                {user.docnm}
              </Text>
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
              로그아웃
            </button>
          </Space>
        ) : (
          <Space style={{ whiteSpace: 'nowrap', marginLeft: 16 }} size={8}>
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
              회원가입
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
              로그인
            </button>
          </Space>
        )}
      </Header>

      <Content style={{ marginTop: 60, padding: '0 24px 80px', minHeight: 'calc(100vh - 60px - 44px)' }}>
        <div style={{ background: cssToken.colorBgContainer, borderRadius: cssToken.borderRadius, padding: '12px 24px 24px' }}>
          <Outlet />
        </div>
      </Content>

      <Footer
        style={{
          position: 'fixed', bottom: 0, left: 0, right: 0,
          textAlign: 'center',
          background: '#163E64',
          color: '#aaa',
          padding: '12px 24px',
          fontSize: 12,
          zIndex: 10,
        }}
      >
        © SmartDocu 2025. All rights reserved.
      </Footer>

      <DocSelectModal open={docModalOpen} onClose={() => setDocModalOpen(false)} />
      <RegisterModal open={registerModalOpen} onClose={() => setRegisterModalOpen(false)} />
      <LoginModal open={loginModalOpen} onClose={() => setLoginModalOpen(false)} />
    </Layout>
  )
}
