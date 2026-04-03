import React from "react";
import { Card, List } from "antd";

export default function DocCardList({ docs, selectedDoc, onSelect }) {
  return (
    <List
      dataSource={docs}
      renderItem={(doc) => (
        <List.Item onClick={() => onSelect(doc)} style={{ cursor: "pointer" }}>
          <Card
            size="small"
            bordered={doc.docid === selectedDoc?.docid} // 선택 강조
            style={{
              backgroundColor: doc.docid === selectedDoc?.docid ? "#e6f7ff" : "#fff",
              marginBottom: 4, // 카드 간 간격만
            }}
          >
            <h4 style={{ margin: 0 }}>{doc.docnm}</h4>
            <p style={{ margin: "2px 0", color: "#888", fontSize: 12 }}>
              {doc.info || "간단한 문서 정보"}
            </p>
          </Card>
        </List.Item>
      )}
    />
  );
}