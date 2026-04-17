import { create } from 'zustand'

export const useLangStore = create((set) => ({
  languageCd: '',
  translations: {},       // ui_term_translations[lang_cd] 만
  defaults: {},           // ui_terms.default_text (언어 무관 기본값)
  translationVersion: 0,  // 번역 로드될 때마다 증가 → Menu key로 강제 재마운트
  setLanguageCd: (cd) => set({ languageCd: cd }),
  setTranslations: (translations, defaults) =>
    set((state) => ({ translations, defaults, translationVersion: state.translationVersion + 1 })),
  resetLang: () => set({ languageCd: '', translations: {}, defaults: {}, translationVersion: 0 }),
}))

/**
 * 번역 헬퍼 — 컴포넌트 외부에서도 사용 가능.
 * 우선순위: translations[key] → defaults[key] → key 그대로
 */
export function t(key, menuFallback) {
  const { translations, defaults } = useLangStore.getState()
  return translations[key] ?? defaults[key] ?? menuFallback ?? key
}
