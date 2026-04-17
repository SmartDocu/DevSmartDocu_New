import { useState, useMemo } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Input, Menu, Spin, Divider, Typography, App } from 'antd'
import { StarOutlined, StarFilled, SearchOutlined } from '@ant-design/icons'
import * as Icons from '@ant-design/icons'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useMenus, useFavorites, useToggleFavorite } from '@/hooks/useMenus'
import { useConfigs } from '@/hooks/useConfigs'
import { useTabStore } from '@/stores/tabStore'

const { Text } = Typography

/* ── Ant Design 아이콘 동적 렌더링 ── */
function DynIcon({ name }) {
  const Icon = name && Icons[name]
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

/* ── 트리 → Ant Design Menu items 변환 ── */
function toAntItems(nodes, favoriteSet, onStarClick, searchKeyword) {
  const filtered = searchKeyword
    ? filterByKeyword(nodes, searchKeyword)
    : nodes

  return filtered.map((node) => {
    const hasChildren = node.children && node.children.length > 0
    const isFav = favoriteSet.has(node.menucd)

    if (hasChildren) {
      return {
        key: node.menucd,
        icon: <DynIcon name={node.iconnm} />,
        label: t(`mnu.${node.menucd}`, node.default_text),
        children: toAntItems(node.children, favoriteSet, onStarClick, null),
      }
    }

    return {
      key: node.menucd,
      icon: <DynIcon name={node.iconnm} />,
      label: (
        <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', color: !node.route_path ? '#bbb' : undefined }}>
            {t(`mnu.${node.menucd}`, node.default_text)}
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

export default function AppSidebar({ collapsed = false }) {
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

  const { data: allMenus = [], isLoading: menusLoading } = useMenus()
  const { data: favoritesData = [] } = useFavorites()
  const toggleFavorite = useToggleFavorite()

  /* ── 권한 필터링된 메뉴 목록 ── */
  const visibleMenus = useMemo(
    () => allMenus.filter((m) => canSee(m.rolecd, user, isAuthenticated)),
    [allMenus, user, isAuthenticated],
  )

  /* ── 즐겨찾기 Set (menucd) ── */
  const favoriteSet = useMemo(
    () => new Set((favoritesData || []).map((f) => f.menucd)),
    [favoritesData],
  )

  /* ── 즐겨찾기 메뉴 항목 목록 ── */
  const favoriteMenus = useMemo(
    () => visibleMenus.filter((m) => favoriteSet.has(m.menucd)),
    [visibleMenus, favoriteSet],
  )

  /* ── 트리 빌드 ── */
  const menuTree = useMemo(() => buildTree(visibleMenus), [visibleMenus])

  /* ── Ant Design Menu items — useMemo 미사용: 언어 변경 시 항상 최신 번역으로 재계산 ── */
  const menuItems = toAntItems(menuTree, favoriteSet, (cd) => toggleFavorite.mutate(cd), search || null)

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
      if (isLeaf) message.info('작업 예정')
      return
    }
    if (menu.route_path.startsWith('http')) {
      window.open(menu.route_path, '_blank')
      return
    }
    const maxTabs = configs?.maxtabs ?? 10
    const alreadyOpen = tabs.some((t) => t.key === key)
    if (!alreadyOpen && tabs.length >= maxTabs) {
      message.warning(`탭은 최대 ${maxTabs}개까지 열 수 있습니다.`)
      return
    }
    openTab({ key: menu.menucd, label: t(`mnu.${menu.menucd}`, menu.default_text), path: menu.route_path })
    navigate('/' + menu.route_path)
  }

  const handleFavClick = (menu) => {
    if (!menu.route_path) return
    if (menu.route_path.startsWith('http')) {
      window.open(menu.route_path, '_blank')
    } else {
      navigate('/' + menu.route_path)
    }
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
            placeholder={t('sidebar.search')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            allowClear
            size="small"
          />
        </div>
      )}

      {/* 즐겨찾기 — 펼쳤을 때만 */}
      {!collapsed && isAuthenticated() && favoriteMenus.length > 0 && !search && (
        <>
          <div className="sidebar-section-title">
            <StarFilled style={{ color: '#faad14', marginRight: 4 }} />
            {t('sidebar.favorites')}
          </div>
          <ul className="sidebar-fav-list">
            {favoriteMenus.map((m) => (
              <li
                key={m.menucd}
                className={`sidebar-fav-item${location.pathname.includes(m.route_path || '__none__') ? ' active' : ''}`}
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
