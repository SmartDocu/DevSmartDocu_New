import React from "react";
import { Input } from "antd";

export default function TextArea({ value, onChange, placeholder = "", rows = 4, disabled = false }) {
  return <Input.TextArea value={value} onChange={onChange} placeholder={placeholder} rows={rows} disabled={disabled} />;
}