import React from "react";
import CommonButton from "./CommonButton";

export default function SaveButton(props) {
  return <CommonButton {...props} type="primary">{props.children || "저장"}</CommonButton>;
}