import React from "react";
import { InputNumber } from "antd";

export default function NumberInput({ value, onChange, min = 0, max, disabled = false }) {
  return <InputNumber value={value} onChange={onChange} min={min} max={max} disabled={disabled} />;
}