import React from "react";
import { Modal } from "antd";

export default function ModalDialog({
  visible,
  title,
  onOk,
  onCancel,
  okText = "확인",
  cancelText = "취소",
  width = 520,
  children,
}) {
  return (
    <Modal
      title={title}
      open={visible}
      onOk={onOk}
      onCancel={onCancel}
      okText={okText}
      cancelText={cancelText}
      width={width}
    >
      {children}
    </Modal>
  );
}