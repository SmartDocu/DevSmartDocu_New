import { create } from 'zustand'

export const useTabStore = create((set) => ({
  tabs: [],       // [{ key: menucd, label: default_text, path: route_path }]
  activeKey: null,
  siderCollapsed: true,
  setSiderCollapsed: (v) => set({ siderCollapsed: v }),

  openTab: (tab) =>
    set((state) => {
      if (state.tabs.find((t) => t.key === tab.key)) {
        return { activeKey: tab.key }
      }
      return { tabs: [...state.tabs, tab], activeKey: tab.key }
    }),

  closeTab: (key) =>
    set((state) => {
      const newTabs = state.tabs.filter((t) => t.key !== key)
      let newActive = state.activeKey
      if (state.activeKey === key) {
        const idx = state.tabs.findIndex((t) => t.key === key)
        newActive = newTabs[Math.min(idx, newTabs.length - 1)]?.key ?? null
      }
      return { tabs: newTabs, activeKey: newActive }
    }),

  setActiveKey: (key) => set({ activeKey: key }),
}))
