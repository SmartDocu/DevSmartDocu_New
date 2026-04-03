import React from "react";
import CommonButton from "./CommonButton";

export default function CancelButton(props) {
  return <CommonButton {...props} type="default">{props.children || "취소"}</CommonButton>;
}