import React from "react";
import CommonButton from "./CommonButton";

export default function DangerButton(props) {
  return (
    <CommonButton
      {...props}
      type="primary"
      style={{ backgroundColor: "#ff4d4f", borderColor: "#ff4d4f" }}
    />
  );
}