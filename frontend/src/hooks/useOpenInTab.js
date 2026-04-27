import { useNavigate } from 'react-router-dom'
import { App } from 'antd'
import { useTabStore } from '@/stores/tabStore'
import { useMenus } from '@/hooks/useMenus'
import { useConfigs } from '@/hooks/useConfigs'
import { t } from '@/stores/langStore'

export function useOpenInTab() {
  const navigate = useNavigate()
  const { message } = App.useApp()
  const { openTab, tabs } = useTabStore()
  const { data: allMenus = [] } = useMenus()
  const { data: configs } = useConfigs()

  const openInTab = (routePath, query = '', fallbackLabel = '') => {
    const menu = allMenus.find((m) => m.route_path === routePath)
    const key = menu?.menucd || routePath
    const maxTabs = configs?.maxtabs ?? 10
    const alreadyOpen = tabs.some((tab) => tab.key === key)
    if (!alreadyOpen && tabs.length >= maxTabs) {
      message.warning(t('msg.tab.maxcount').replace('{n}', maxTabs))
      return
    }
    const label = menu ? t(`mnu.${menu.menucd}`, menu.default_text) : fallbackLabel
    if (menu) openTab({ key, label, path: `${routePath}${query}` })
    navigate(`/${routePath}${query}`)
  }

  return openInTab
}
