import React from "react";
import { Table, Space } from "antd";
import CommonButton from "../Button/CommonButton";
import DangerButton from "../Button/DangerButton";

export default function DataTable({ columns, data }) {
  const enhancedColumns = [
    ...columns,
    {
      title: "액션",
      key: "action",
      render: (_, record) => (
        <Space>
          <CommonButton size="small">수정</CommonButton>
          <DangerButton size="small">삭제</DangerButton>
        </Space>
      ),
    },
  ];

  return <Table columns={enhancedColumns} dataSource={data} />;
}