import React from "react";

export default function PageTitle({ children }) {
  return <h1 style={{ fontSize: 24, fontWeight: "bold", marginBottom: 8 }}>{children}</h1>;
}