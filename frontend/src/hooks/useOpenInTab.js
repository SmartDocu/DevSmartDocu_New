import { useNavigate, useLocation } from 'react-router-dom'
import { App } from 'antd'
import { useTabStore } from '@/stores/tabStore'
import { useMenus } from '@/hooks/useMenus'
import { useConfigs } from '@/hooks/useConfigs'
import { t } from '@/stores/langStore'

export function useOpenInTab() {
  const navigate = useNavigate()
  const location = useLocation()
  const { message } = App.useApp()
  const { openTab, tabs, activeKey } = useTabStore()
  const { data: allMenus = [] } = useMenus()
  const { data: configs } = useConfigs()

  const openInTab = (routePath, query = '', fallbackLabel = '') => {
    // 현재 탭의 저장 path를 실제 URL로 동기화 (탭 내 navigate로 이동한 경우 대비)
    const currentTab = tabs.find((tab) => tab.key === activeKey)
    if (currentTab) {
      const currentPath = (location.pathname + location.search).replace(/^\//, '')
      if (currentTab.path !== currentPath) {
        openTab({ key: currentTab.key, label: currentTab.label, path: currentPath })
      }
    }

    const menu = allMenus.find((m) => m.route_path === routePath)
    const key = menu?.menucd || routePath
    const maxTabs = configs?.maxtabs ?? 10
    const alreadyOpen = tabs.some((tab) => tab.key === key)
    if (!alreadyOpen && tabs.length >= maxTabs) {
      message.warning(t('msg.tab.maxcount').replace('{n}', maxTabs))
      return
    }
    const label = menu ? t(`mnu.${menu.menucd}`, menu.default_text) : fallbackLabel
    openTab({ key, label, path: `${routePath}${query}` })
    navigate(`/${routePath}${query}`)
  }

  return openInTab
}
