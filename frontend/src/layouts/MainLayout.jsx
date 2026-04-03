import React, { Suspense } from "react";
import { Layout, Tabs } from "antd";
import Sidebar from "../components/Layout/Sidebar";
import HeaderBar from "../components/Layout/Header";
import { useI18n } from "../contexts/I18nContext";

const { Content, Sider } = Layout;

export default function MainLayout({ 
  menuStructure, 
  tabs, 
  setTabs, 
  activeKey, 
  setActiveKey, 
  openKeys, 
  setOpenKeys 
}) {
  const { t } = useI18n();

  const findLabel = (key) => {
    const allMenus = menuStructure.flatMap(g => g.children ?? [g]);
    return allMenus.find(m => m.key === key)?.label || key;
  };

  const removeTab = (targetKey) => {
    const filteredTabs = tabs.filter((tab) => tab.key !== targetKey);
    setTabs(filteredTabs);
    if (activeKey === targetKey && filteredTabs.length) {
      setActiveKey(filteredTabs[filteredTabs.length - 1].key);
    }
  };

  return (
    <Layout style={{ minHeight: "120vh" }}>
      <Sider collapsible>
        <Sidebar
          menuStructure={menuStructure}
          activeKey={activeKey}
          setActiveKey={setActiveKey}
          tabs={tabs}
          setTabs={setTabs}
          openKeys={openKeys}
          setOpenKeys={setOpenKeys}
        />
      </Sider>

      <Layout>
        <HeaderBar />

        <Content style={{ margin: "16px" }}>
          <Tabs
            type="editable-card"
            hideAdd
            activeKey={activeKey}
            onChange={setActiveKey}
            onEdit={(key, action) => action === "remove" && removeTab(key)}
            items={tabs.map((tab) => ({
              key: tab.key,
              label: t(findLabel(tab.key)),
              // 🔹 여기가 핵심
              children: tab.component ? (
                <Suspense fallback={<div>Loading page...</div>}>
                  <tab.component />
                </Suspense>
              ) : null,
            }))}
          />
        </Content>
      </Layout>
    </Layout>
  );
}