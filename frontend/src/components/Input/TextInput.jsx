import React from "react";
import { Input } from "antd";

export default function TextInput({ value, onChange, placeholder = "", disabled = false }) {
  return <Input value={value} onChange={onChange} placeholder={placeholder} disabled={disabled} />;
}