import { create } from 'zustand'

export const useReqStore = create((set) => ({
  activeGendocuid: null,
  setActiveGendocuid: (uid) => set({ activeGendocuid: uid }),
  activeGenchapteruid: null,
  setActiveGenchapteruid: (uid) => set({ activeGenchapteruid: uid }),
}))
