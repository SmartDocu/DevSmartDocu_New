import React from "react";

export default function PageContainer({ children }) {
  return (
    <div style={{ padding: 24, backgroundColor: "#fff", minHeight: "calc(100vh - 60px)" }}>
      {children}
    </div>
  );
}