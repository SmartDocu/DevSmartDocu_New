import React from "react";
import CommonButton from "./CommonButton";

export default function NavButton(props) {
  return <CommonButton {...props} type="default">{props.children || "이동"}</CommonButton>;
}