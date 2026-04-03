import React from "react";
import { Spin } from "antd";

export default function Spinner({ size = "large" }) {
  return (
    <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100%" }}>
      <Spin size={size} />
    </div>
  );
}