import React from "react";
import { Tabs } from "antd";

export default function CustomTabs({ tabs, activeKey, onChange }) {
  const tabBarStyle = {
    backgroundColor: "#f0f2f5",
    borderRadius: 6,
    padding: "4px 8px",
  };

  const tabStyle = {
    backgroundColor: "#747474",
    color: "white",
    borderRadius: "4px 4px 0 0",
    marginRight: 4,
  };

  const activeTabStyle = {
    backgroundColor: "#40a9ff",
    color: "white",
  };

  // items 배열로 변환
  const items = tabs.map((tab) => ({
    key: tab.key,
    label: tab.label,
    children: tab.content,
    style: tab.key === activeKey ? { ...tabStyle, ...activeTabStyle } : tabStyle,
  }));

  return (
    <Tabs
      activeKey={activeKey}
      onChange={onChange}
      type="line"
      tabBarStyle={tabBarStyle}
      items={items}
    />
  );
}