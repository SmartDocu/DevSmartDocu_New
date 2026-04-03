import React, { useEffect, useState } from "react";
import { Menu, Input, message } from "antd";
import { useI18n } from "../../contexts/I18nContext";
import { useAuth } from "../../contexts/AuthContext";

export default function Sidebar({
  menuStructure,
  activeKey,
  setActiveKey,
  tabs,
  setTabs,
  openKeys,
  setOpenKeys,
}) {
  const [search, setSearch] = useState("");
  const [maxTabs, setMaxTabs] = useState(5);
  const { t } = useI18n();
  const { user } = useAuth();
  const isLoggedIn = !!user;

  const BASE_URL = process.env.REACT_APP_API_URL;

  useEffect(() => {
    fetch(`${BASE_URL}/settings/max-tabs`)
      .then((res) => res.json())
      .then((data) => data?.maxTabs && setMaxTabs(data.maxTabs))
      .catch(() => console.warn("maxTabs 불러오기 실패 → 기본값 5 사용"));
  }, []);

  const findMenu = (menus, key) => {
    for (const m of menus) {
      if (m.key.toLowerCase() === key.toLowerCase()) return m;
      if (m.children) {
        const found = findMenu(m.children, key);
        if (found) return found;
      }
    }
    return null;
  };

  const handleMenuClick = (key) => {
    const found = findMenu(menuStructure, key);
    if (!found || !found.component) return;

    const parentMap = {};
    menuStructure.forEach((g) =>
      g.children?.forEach((c) => (parentMap[c.key] = g.key))
    );
    const parentKey = parentMap[key];
    if (parentKey) setOpenKeys([parentKey]);

    if (!tabs.find((t) => t.key === key)) {
      if (tabs.length >= maxTabs) {
        message.warning(`탭은 최대 ${maxTabs}개까지 열 수 있습니다.`);
        return;
      }
      setTabs([...tabs, { key: found.key, component: found.component }]);
    }

    setActiveKey(key);
  };

  // 🔹 로그인 + 검색 필터
  const filterMenu = (menuList) =>
    menuList
      .map((item) => {
        if (item.requiresAuth && !isLoggedIn) return null;

        let children = item.children ? filterMenu(item.children) : null;

        const include =
          (!children && (!item.requiresAuth || isLoggedIn)) ||
          (children && children.length > 0) ||
          t(item.label).toLowerCase().includes(search.toLowerCase());

        if (!include) return null;

        return { ...item, children };
      })
      .filter(Boolean);

  const filteredMenu = filterMenu(menuStructure);

  useEffect(() => {
    if (search) setOpenKeys(filteredMenu.map((g) => g.key));
  }, [search]);

  // 🔹 메뉴 항목 생성 (children 포함 번역)
  const buildMenuItems = (menus) =>
    menus.map((item) => ({
      key: item.key,
      icon: item.icon,
      label: t(item.label),
      children: item.children ? buildMenuItems(item.children) : undefined,
    }));

  const menuItems = buildMenuItems(filteredMenu);

  return (
    <div>
      <div style={{ color: "white", padding: 16, textAlign: "center" }}>
        SmartDocu
      </div>

      <div style={{ padding: 12 }}>
        <Input
          placeholder={t("menu.search") || "메뉴 검색"}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          allowClear
        />
      </div>

      <Menu
        theme="dark"
        mode="inline"
        openKeys={openKeys}
        selectedKeys={[activeKey]}
        onOpenChange={(keys) =>
          setOpenKeys(keys.length ? [keys[keys.length - 1]] : [])
        }
        onClick={(e) => handleMenuClick(e.key)}
        items={menuItems}
      />

      {filteredMenu.length === 0 && (
        <div style={{ color: "#999", padding: 12 }}>
          {t("menu.no_result") || "검색 결과 없음"}
        </div>
      )}
    </div>
  );
}