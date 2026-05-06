import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export const useTabStore = create(
  persist(
    (set) => ({
      tabs: [],
      activeKey: null,
      siderCollapsed: true,
      setSiderCollapsed: (v) => set({ siderCollapsed: v }),
      colorTheme: 'light',
      setColorTheme: (theme) => set({ colorTheme: theme }),

      openTab: (tab) =>
        set((state) => {
          if (state.tabs.find((t) => t.key === tab.key)) {
            return { tabs: state.tabs.map((t) => t.key === tab.key ? { ...t, path: tab.path } : t), activeKey: tab.key }
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

      closeOtherTabs: (key) =>
        set((state) => ({
          tabs: state.tabs.filter((t) => t.key === key),
          activeKey: key,
        })),

      closeLeftTabs: (key) =>
        set((state) => {
          const idx = state.tabs.findIndex((t) => t.key === key)
          const newTabs = state.tabs.slice(idx)
          const activeKey = newTabs.find((t) => t.key === state.activeKey) ? state.activeKey : key
          return { tabs: newTabs, activeKey }
        }),

      closeRightTabs: (key) =>
        set((state) => {
          const idx = state.tabs.findIndex((t) => t.key === key)
          const newTabs = state.tabs.slice(0, idx + 1)
          const activeKey = newTabs.find((t) => t.key === state.activeKey) ? state.activeKey : key
          return { tabs: newTabs, activeKey }
        }),

      setActiveKey: (key) => set({ activeKey: key }),

      clearTabs: () => set({ tabs: [], activeKey: null }),
    }),
    {
      name: 'tab-store',
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        tabs: state.tabs,
        activeKey: state.activeKey,
        siderCollapsed: state.siderCollapsed,
        colorTheme: state.colorTheme,
      }),
    }
  )
)
