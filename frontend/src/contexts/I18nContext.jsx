import React, { createContext, useContext, useState, useEffect } from "react";
import axios from "axios";

const I18nContext = createContext();
const BASE_URL = process.env.REACT_APP_API_URL;

export const I18nProvider = ({ children, initialLang = "en" }) => {
  const [lang, setLang] = useState(initialLang); // prop 이름 변경
  const [translations, setTranslations] = useState({});

  useEffect(() => {
    async function fetchTranslations() {
      try {
        const res = await axios.get(`${BASE_URL}/i18n/terms?lang=${lang}`);
        setTranslations(res.data);
      } catch (err) {
        console.error("Translation fetch error:", err);
      }
    }
    fetchTranslations();
  }, [lang]);

  const t = (key) => translations[key] || key;

  return <I18nContext.Provider value={{ t, lang, setLang }}>{children}</I18nContext.Provider>;
};

export const useI18n = () => useContext(I18nContext);