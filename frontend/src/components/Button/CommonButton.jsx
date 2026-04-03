import React from "react";
import { Button } from "antd";

export default function CommonButton({
  children,
  onClick,
  type = "primary",
  size = "middle",
  disabled = false,
  loading = false,
}) {
  return (
    <Button
      type={type}
      size={size}
      onClick={onClick}
      disabled={disabled}
      loading={loading}
    >
      {children}
    </Button>
  );
}