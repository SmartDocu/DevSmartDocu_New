import React, { useState } from "react";
import { Select, Button, Modal, Input } from "antd";
import { useI18n } from "../../contexts/I18nContext";
import { useAuth } from "../../contexts/AuthContext";

const { Option } = Select;

export default function HeaderBar() {
  const { lang, setLang, t } = useI18n();
  const { user, signIn, signOut } = useAuth();

  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const handleLogin = async () => {
    try {
      await signIn(email, password);
      setOpen(false);
    } catch (err) {
      alert("로그인 실패");
    }
  };

  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "0 20px", background: "#fff", alignItems: "center" }}>
      <b>SmartDocu</b>

      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Select value={lang} style={{ width: 100 }} onChange={(value) => setLang(value)}>
          <Option value="ko">한국어</Option>
          <Option value="en">English</Option>
        </Select>

        {/* 🔥 로그인 상태 분기 */}
        {user ? (
          <>
            <span>{user.email}</span>
            <Button onClick={signOut}>
              {t("btn.logout") || "로그아웃"}
            </Button>
          </>
        ) : (
          <Button onClick={() => setOpen(true)}>
            {t("btn.login") || "로그인"}
          </Button>
        )}
      </div>

      {/* 로그인 모달 */}
      <Modal
        title="Login"
        open={open}
        onOk={handleLogin}
        onCancel={() => setOpen(false)}
      >
        <Input
          placeholder="Email"
          onChange={(e) => setEmail(e.target.value)}
        />
        <Input.Password
          placeholder="Password"
          onChange={(e) => setPassword(e.target.value)}
          style={{ marginTop: 10 }}
        />
      </Modal>
    </div>
  );
}