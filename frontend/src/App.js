import React, { useState, useEffect, Suspense } from "react";
import MainLayout from "./layouts/MainLayout";
import { I18nProvider } from "./contexts/I18nContext";
import { AuthProvider, useAuth } from "./contexts/AuthContext";

function AppInner() {
  const { user, loading: authLoading } = useAuth();
  const [tabs, setTabs] = useState([]);
  const [activeKey, setActiveKey] = useState(null);
  const [openKeys, setOpenKeys] = useState([]);
  const [menuStructure, setMenuStructure] = useState([]);
  const [defaultLang, setDefaultLang] = useState(null);
  const [loading, setLoading] = useState(true);

  const BASE_URL = process.env.REACT_APP_API_URL;

  // 🔹 메뉴 구조 받아오면 component 필드 동적 추가
  const attachComponent = (menus) =>
    menus.map((m) => ({
      ...m,
      component: m.menu
        ? React.lazy(() => import(`./pages/${m.menu}`))
        : null,
      children: m.children ? attachComponent(m.children) : undefined,
    }));

  useEffect(() => {
    if (authLoading) return;

    async function fetchSettings() {
      try {
        const userId = user?.id || "";
        const [menuRes, langRes] = await Promise.all([
          fetch(`${BASE_URL}/settings/menu?user_id=${userId}`).then((r) => r.json()),
          fetch(`${BASE_URL}/settings/default-lang?user_id=${userId}`).then((r) => r.json()),
        ]);
        const menuWithComp = attachComponent(menuRes.menu);
        setMenuStructure(menuWithComp);

        // 🔹 기본 홈 탭
        const homeMenu = menuWithComp.find((m) => m.key === "home");
        if (homeMenu?.component) {
          setTabs([{ key: homeMenu.key, component: homeMenu.component }]);
          setActiveKey(homeMenu.key);
        }

        setDefaultLang(langRes.defaultLang);
      } catch (err) {
        console.error("Settings fetch error", err);
        setDefaultLang("en");
      } finally {
        setLoading(false);
      }
    }

    fetchSettings();
  }, [user, authLoading, BASE_URL]);

  if (loading || !defaultLang) return <div>Loading...</div>;

  return (
    <I18nProvider initialLang={defaultLang}>
      <Suspense fallback={<div>Loading page...</div>}>
        <MainLayout
          menuStructure={menuStructure}
          tabs={tabs}
          setTabs={setTabs}
          activeKey={activeKey}
          setActiveKey={setActiveKey}
          openKeys={openKeys}
          setOpenKeys={setOpenKeys}
        />
      </Suspense>
    </I18nProvider>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppInner />
    </AuthProvider>
  );
}