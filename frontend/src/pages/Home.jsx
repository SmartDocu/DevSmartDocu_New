// src/pages/Home.jsx
import React from "react";
import Home01 from "../assets/images/Home01.png";
import Home02 from "../assets/images/Home02.png";
import Home03 from "../assets/images/Home03.png";

export default function Home() {
  return (
    <div>
      {/* 상단 타이틀 */}
      <div style={{ textAlign: "center", padding: "20px" }}>
        <p style={{ fontSize: "1rem", margin: 0, opacity: 0.8 }}>
          효율적인 문서 자동 작성
        </p>
        <p style={{ fontSize: "5rem", fontWeight: 300, margin: 0 }}>
          SmartDocu
        </p>
      </div>

      {/* 양쪽 정보 박스 */}
      <div style={{ display: "flex", gap: 0, marginTop: "40px" }}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "20px" }}>
          <div
            style={{
              marginLeft: "auto",
              marginRight: "10%",
              backgroundColor: "#e6e6e6",
              padding: "15px 100px 15px 30px",
              borderRadius: "8px",
            }}
          >
            <p style={{ textAlign: "left", color: "black", fontWeight: "normal", margin: 0 }}>
              SmartDocu는 DB와 Excel로부터 <br />
              AI 기능을 이용하여 문서를 작성합니다.
            </p>
          </div>
        </div>

        <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
          <div
            style={{
              marginRight: "auto",
              marginLeft: "10%",
              backgroundColor: "#e6e6e6",
              padding: "15px 100px 15px 30px",
              borderRadius: "8px",
            }}
          >
            <p style={{ textAlign: "left", color: "black", fontWeight: "normal", margin: 0 }}>
              작성에서 검토 및 확정 중심으로 전환,<br />
              One-Click으로 문서를 자동 작성합니다.
            </p>
          </div>
        </div>
      </div>

      {/* What / Why / How 카드 */}
      <div style={{ maxWidth: "700px", margin: "60px auto", display: "flex", flexDirection: "column", gap: "20px" }}>
        {/* What */}
        <div style={{
          display: "flex", alignItems: "center", gap: "20px", padding: "20px 25px",
          borderRadius: "15px", background: "linear-gradient(90deg, #55C7D9, #91E3F3)",
          boxShadow: "0 8px 20px rgba(0,0,0,0.2)", color: "#fff"
        }}>
          <strong style={{ fontSize: "1.2rem" }}>What</strong>
          정기적으로 작성해야 하는 문서
        </div>

        {/* Why */}
        <div style={{
          display: "flex", alignItems: "center", gap: "20px", padding: "20px 25px",
          borderRadius: "15px", background: "linear-gradient(90deg, #FF9A8B, #FF6A88)",
          boxShadow: "0 8px 20px rgba(0,0,0,0.2)", color: "#fff"
        }}>
          <strong style={{ fontSize: "1.2rem" }}>Why</strong>
          반복적인 자료 조회, 비효율적인 작성
        </div>

        {/* How */}
        <div style={{
          display: "flex", alignItems: "center", gap: "20px", padding: "20px 25px",
          borderRadius: "15px", background: "linear-gradient(90deg, #FDCB6E, #FFB347)",
          boxShadow: "0 8px 20px rgba(0,0,0,0.2)", color: "#fff"
        }}>
          <strong style={{ fontSize: "1.2rem" }}>How</strong>
          문서에 사용될 데이터와 서식 설정을 통해
        </div>
      </div>

      {/* 슬라이드 섹션 (이미지만) */}
      <div style={{ maxWidth: "800px", margin: "50px auto", border: "1px solid #ddd", borderRadius: "15px", overflow: "hidden", position: "relative", paddingBottom: "40px" }}>
        {[Home01, Home02, Home03].map((img, idx) => (
          <div key={idx} style={{ display: idx === 0 ? "flex" : "none", padding: "20px", gap: "20px", alignItems: "center" }}>
            <div style={{ flex: 3 }}>
              <h2>{idx === 0 ? "데이터 설정" : idx === 1 ? "문서 설정" : "문서 작성"}</h2>
              <p>
                {idx === 0 ? "ODBC를 지원하는 모든 데이터베이스와 Excel 자료에 대한 연결 정보, 쿼리, 데이터 항목을 정의합니다." :
                 idx === 1 ? "구성할 목차, 템플릿, 템플릿 내 항목을 정의합니다. 개체에 해당하는 문장, 테이블, 차트는 AI와 UI로 정의합니다." :
                 "문서의 노출된 매개변수에 값을 기입하여 해당 매개변수 기준으로 문서를 작성합니다."}
              </p>
            </div>
            <div style={{ flex: 7, textAlign: "right" }}>
              <img src={img} style={{ maxWidth: "100%", borderRadius: "10px" }} alt="" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}