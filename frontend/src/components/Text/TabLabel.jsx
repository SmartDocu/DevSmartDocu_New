import React from "react";

export default function TabLabel({ children }) {
  return (
    <span style={{ fontSize: 16, fontWeight: 500, color: "#333", padding: "4px 8px" }}>
      {children}
    </span>
  );
}