import { useI18n } from "../contexts/I18nContext";

export const useTranslation = (key) => {
  const { translations } = useI18n();
  return translations[key] || key;
};