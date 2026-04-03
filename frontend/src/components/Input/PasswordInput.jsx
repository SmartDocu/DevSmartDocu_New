import React from "react";
import { Input } from "antd";

export default function PasswordInput({ value, onChange, placeholder = "", disabled = false }) {
  return <Input.Password value={value} onChange={onChange} placeholder={placeholder} disabled={disabled} />;
}