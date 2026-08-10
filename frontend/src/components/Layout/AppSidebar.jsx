import { useState, useMemo, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Input, Menu, Spin, Divider, Typography, App } from 'antd'
import { StarOutlined, StarFilled, SearchOutlined } from '@ant-design/icons'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useMenus, useFavorites, useToggleFavorite } from '@/hooks/useMenus'
import { useConfigs } from '@/hooks/useConfigs'
import { useTenantManageOtherSubscriptions } from '@/hooks/useSettings'
import { useTabStore } from '@/stores/tabStore'

const { Text } = Typography

/* ── 기타 구독(Feature) 상품 구독 여부에 따라서만 노출되는 메뉴 ── */
const FEATURE_GATED_MENUS = {
  'tenant_mgr.manage.whitelists': 'whitelist',
}

function hasFeatureAccess(menucd, ownedProductcds) {
  const requiredProductcd = FEATURE_GATED_MENUS[menucd]
  if (!requiredProductcd) return true
  return ownedProductcds.has(requiredProductcd)
}

/* ── 시스템(개인) 테넌트에서는 '조직' 개념이 없어 의미 없는 기업 관리 메뉴 ──
   org.llm/org.project_llm(AM, 개인 LLM 키 등록용)은 제외.
   proj_mgr.project_users는 시스템 테넌트에서 개인이 자기 프로젝트의 projectmanager='Y'로
   자동 지정되어 노출되는 것을 막기 위해 포함 — 기업 테넌트의 실제 PM에게는 계속 보인다
   (tenant_mgr.org.project_users가 같은 화면을 TM 전용으로 별도 제공, 2026-08-10) */
const SYSTEM_TENANT_HIDDEN_MENUS = new Set([
  'tenant_mgr.manage',
  'tenant_mgr.manage.overview',
  'tenant_mgr.manage.whitelists',
  'tenant_mgr.org.users',
  'tenant_mgr.org.projects',
  'tenant_mgr.db.db_data',
  'tenant_mgr.db.api_data',
  'tenant_mgr.db.connectors',
  'tenant_mgr.db.data_groups',
  'tenant_mgr.db.servers',
  'proj_mgr.project_users',
])

function hiddenOnSystemTenant(menucd, isSystemTenant) {
  return isSystemTenant && SYSTEM_TENANT_HIDDEN_MENUS.has(menucd)
}

/* ── Ant Design 아이콘 동적 렌더링 ──
   menus.iconnm은 자유 텍스트(DB 저장값)라 어떤 아이콘 이름이 올지 미리 알 수 없다.
   전체 아이콘(800개+)을 정적으로 import(* as Icons)하면 메인 번들에 다 실리므로,
   패키지 전체를 하나의 지연 청크로 동적 import해서 메인 번들에서만 빼고 이름으로 골라 쓴다.
   (node_modules 경로에 대한 아이콘별 변수 동적 import는 Vite가 프로덕션 빌드에서
   청크로 쪼개주지 않아 런타임에 깨지므로 사용하지 않는다.) */
let _iconsPromise = null
function loadIconLibrary() {
  if (!_iconsPromise) _iconsPromise = import('@ant-design/icons')
  return _iconsPromise
}

function DynIcon({ name }) {
  const [Icon, setIcon] = useState(null)

  useEffect(() => {
    if (!name) { setIcon(null); return }
    let cancelled = false
    loadIconLibrary().then((mod) => {
      if (!cancelled) setIcon(() => mod[name] || null)
    })
    return () => { cancelled = true }
  }, [name])

  if (!Icon) return null
  return <Icon />
}

/* ── rolecd 권한 체크 ── */
function canSee(rolecd, user, isAuthenticated) {
  if (rolecd === 'P') return true
  if (!isAuthenticated()) return false
  if (rolecd === 'U') return true
  if (rolecd === 'PM') return user?.projectmanager === 'Y'
  if (rolecd === 'TM') return user?.tenantmanager === 'Y'
  if (rolecd === 'AM') return user?.accountmanager === 'Y'
  if (rolecd === 'S') return user?.roleid === 7
  return false
}

/* ── 플랫 목록 → 계층 트리 변환 ── */
function buildTree(menus) {
  const map = {}
  menus.forEach((m) => { map[m.menucd] = { ...m, children: [] } })

  const roots = []
  menus.forEach((m) => {
    const parts = m.menucd.split('.')
    if (parts.length === 1) {
      roots.push(map[m.menucd])
    } else {
      const parentCd = parts.slice(0, -1).join('.')
      if (map[parentCd]) {
        map[parentCd].children.push(map[m.menucd])
      }
    }
  })
  return roots
}

/* ── 메뉴 표시명: 현재 언어 번역 → menus.default_text 순으로 참조 (ui_terms defaults 건너뜀) ── */
function menuLabel(menucd, defaultText) {
  const { translations } = useLangStore.getState()
  return translations[`mnu.${menucd}`] ?? defaultText ?? `mnu.${menucd}`
}

/* ── 트리 → Ant Design Menu items 변환 ── */
function toAntItems(nodes, favoriteSet, onStarClick, searchKeyword, collapsed = false) {
  const filtered = searchKeyword
    ? filterByKeyword(nodes, searchKeyword)
    : nodes

  return filtered.map((node) => {
    const hasChildren = node.children && node.children.length > 0
    const isFav = favoriteSet.has(node.menucd)
    const nm = menuLabel(node.menucd, node.default_text)

    if (hasChildren) {
      return {
        key: node.menucd,
        icon: <DynIcon name={node.iconnm} />,
        label: nm,
        title: nm,
        children: toAntItems(node.children, favoriteSet, onStarClick, null, collapsed),
      }
    }

    return {
      key: node.menucd,
      icon: <DynIcon name={node.iconnm} />,
      title: nm,
      label: collapsed ? nm : (
        <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', color: !node.route_path ? '#bbb' : undefined }}>
            {nm}
          </span>
          <span
            className="sidebar-star"
            onClick={(e) => { e.stopPropagation(); onStarClick(node.menucd) }}
            style={{ marginLeft: 4, color: isFav ? '#faad14' : '#ccc', flexShrink: 0 }}
          >
            {isFav ? <StarFilled /> : <StarOutlined />}
          </span>
        </span>
      ),
    }
  })
}

/* ── 검색어로 트리 필터링 (부모 포함) ── */
function filterByKeyword(nodes, keyword) {
  const kw = keyword.toLowerCase()
  return nodes
    .map((node) => {
      const match = t(`mnu.${node.menucd}`, node.default_text).toLowerCase().includes(kw)
      const filteredChildren = node.children ? filterByKeyword(node.children, keyword) : []
      if (match || filteredChildren.length > 0) {
        return { ...node, children: filteredChildren }
      }
      return null
    })
    .filter(Boolean)
}

/* ── 현재 경로에 해당하는 menucd 찾기 ── */
function findSelectedKey(menus, pathname) {
  for (const m of menus) {
    if (m.route_path && pathname.includes(m.route_path)) {
      return m.menucd
    }
  }
  return null
}

export default function AppSidebar({ collapsed = false, isDark = false, appcd = null }) {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, isAuthenticated } = useAuthStore()
  const { message } = App.useApp()
  const { data: configs } = useConfigs()
  const { tabs, openTab } = useTabStore()
  // 언어 변경 시 re-render 트리거 — Header 버튼과 동일한 방식
  useLangStore((s) => s.translations)
  const translationVersion = useLangStore((s) => s.translationVersion)

  const [search, setSearch] = useState('')

  const { data: allMenus = [], isLoading: menusLoading } = useMenus(appcd)
  const { data: favoritesData = [] } = useFavorites()
  const toggleFavorite = useToggleFavorite()
  const { data: otherSubData } = useTenantManageOtherSubscriptions({ enabled: isAuthenticated() })
  const ownedFeatureProductcds = useMemo(
    () => new Set((otherSubData?.owned || []).map((o) => o.productcd)),
    [otherSubData],
  )

  /* ── 권한 필터링된 메뉴 목록 (자식이 보이면 부모도 자동 포함) ── */
  const visibleMenus = useMemo(() => {
    const visibleCds = new Set(
      allMenus
        .filter((m) => canSee(m.rolecd, user, isAuthenticated)
          && hasFeatureAccess(m.menucd, ownedFeatureProductcds)
          && !hiddenOnSystemTenant(m.menucd, user?.issystemtenant))
        .map((m) => m.menucd)
    )
    // 보이는 메뉴의 모든 조상 menucd 추가
    visibleCds.forEach((cd) => {
      const parts = cd.split('.')
      for (let i = 1; i < parts.length; i++) {
        visibleCds.add(parts.slice(0, i).join('.'))
      }
    })
    return allMenus.filter((m) => visibleCds.has(m.menucd))
  }, [allMenus, user, isAuthenticated, ownedFeatureProductcds])

  /* ── 즐겨찾기 Set (menucd) ── */
  const favoriteSet = useMemo(
    () => new Set((favoritesData || []).map((f) => f.menucd)),
    [favoritesData],
  )

  /* ── 즐겨찾기 메뉴 항목 목록 (favorites.orderno 순) ── */
  const favoriteMenus = useMemo(() => {
    const orderMap = Object.fromEntries(
      (favoritesData || []).map((f) => [f.menucd, f.orderno])
    )
    return visibleMenus
      .filter((m) => favoriteSet.has(m.menucd))
      .sort((a, b) => (orderMap[a.menucd] ?? 999) - (orderMap[b.menucd] ?? 999))
  }, [visibleMenus, favoriteSet, favoritesData])

  /* ── 트리 빌드 ── */
  const menuTree = useMemo(() => buildTree(visibleMenus), [visibleMenus])

  /* ── Ant Design Menu items — useMemo 미사용: 언어 변경 시 항상 최신 번역으로 재계산 ── */
  const menuItems = toAntItems(menuTree, favoriteSet, (cd) => toggleFavorite.mutate(cd), search || null, collapsed)

  /* ── 선택된 키 ── */
  const selectedKey = useMemo(
    () => findSelectedKey(visibleMenus, location.pathname),
    [visibleMenus, location.pathname],
  )

  /* ── 열린 부모 키 목록 (현재 경로 기준) ── */
  const defaultOpenKeys = useMemo(() => {
    if (!selectedKey) return []
    const parts = selectedKey.split('.')
    const opens = []
    for (let i = 1; i < parts.length; i++) {
      opens.push(parts.slice(0, i).join('.'))
    }
    return opens
  }, [selectedKey])

  const handleMenuClick = ({ key }) => {
    const menu = visibleMenus.find((m) => m.menucd === key)
    if (!menu) return
    if (!menu.route_path) {
      const isLeaf = !visibleMenus.some((m) => m.menucd.startsWith(key + '.'))
      if (isLeaf) message.info(t('msg.coming.soon'))
      return
    }
    if (menu.route_path.startsWith('http')) {
      window.open(menu.route_path, '_blank')
      return
    }
    const maxTabs = configs?.maxtabs ?? 10
    const alreadyOpen = tabs.some((t) => t.key === key)
    if (!alreadyOpen && tabs.length >= maxTabs) {
      message.warning(t('msg.tab.maxcount').replace('{n}', maxTabs))
      return
    }
    const tabPath = appcd ? `app/${appcd}/${menu.route_path}` : menu.route_path
    const navPath = appcd ? `/app/${appcd}/${menu.route_path}` : `/${menu.route_path}`
    openTab({ key: menu.menucd, label: t(`mnu.${menu.menucd}`, menu.default_text), path: tabPath })
    navigate(navPath)
  }

  const handleFavClick = (menu) => {
    if (!menu.route_path) return
    if (menu.route_path.startsWith('http')) {
      window.open(menu.route_path, '_blank')
      return
    }
    const maxTabs = configs?.maxtabs ?? 10
    const alreadyOpen = tabs.some((t) => t.key === menu.menucd)
    if (!alreadyOpen && tabs.length >= maxTabs) {
      message.warning(t('msg.tab.maxcount').replace('{n}', maxTabs))
      return
    }
    const tabPath = appcd ? `app/${appcd}/${menu.route_path}` : menu.route_path
    const navPath = appcd ? `/app/${appcd}/${menu.route_path}` : `/${menu.route_path}`
    openTab({ key: menu.menucd, label: t(`mnu.${menu.menucd}`, menu.default_text), path: tabPath })
    navigate(navPath)
  }

  if (menusLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}>
        <Spin size="small" />
      </div>
    )
  }

  return (
    <div className="app-sidebar">
      {/* 검색 — 펼쳤을 때만 */}
      {!collapsed && (
        <div className="sidebar-search">
          <Input
            prefix={<SearchOutlined style={{ color: '#aaa' }} />}
            placeholder={t('msg.sidebar.search')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            allowClear
            size="small"
            className={isDark ? 'sidebar-search-dark' : undefined}
            style={isDark ? { background: '#1a3a5c', color: '#fff', borderColor: '#1a5080' } : undefined}
          />
        </div>
      )}

      {/* 즐겨찾기 — 펼쳤을 때만 */}
      {!collapsed && isAuthenticated() && favoriteMenus.length > 0 && !search && (
        <>
          <div className="sidebar-section-title" style={{ color: isDark ? '#aaa' : undefined }}>
            <StarFilled style={{ color: '#faad14', marginRight: 4 }} />
            {t('msg.sidebar.favorites')}
          </div>
          <ul className="sidebar-fav-list">
            {favoriteMenus.map((m) => (
              <li
                key={m.menucd}
                className={`sidebar-fav-item${location.pathname.includes(m.route_path || '__none__') ? ' active' : ''}`}
                style={{ color: isDark ? '#ccc' : '#333' }}
              >
                <span className="sidebar-fav-label" onClick={() => handleFavClick(m)}>
                  <DynIcon name={m.iconnm} />
                  <span style={{ marginLeft: 6 }}>{t(`mnu.${m.menucd}`, m.default_text)}</span>
                </span>
                <span
                  className="sidebar-star"
                  onClick={() => toggleFavorite.mutate(m.menucd)}
                  style={{ color: '#faad14' }}
                >
                  <StarFilled />
                </span>
              </li>
            ))}
          </ul>
          <Divider style={{ margin: '4px 0' }} />
        </>
      )}

      {/* 메뉴 트리 — 접혔을 때는 아이콘만 표시 */}
      <Menu
        key={translationVersion}
        mode="inline"
        theme={isDark ? 'dark' : 'light'}
        inlineCollapsed={collapsed}
        items={menuItems}
        selectedKeys={selectedKey ? [selectedKey] : []}
        defaultOpenKeys={collapsed ? [] : defaultOpenKeys}
        onClick={handleMenuClick}
        style={{ border: 'none', background: 'transparent' }}
      />
    </div>
  )
}
