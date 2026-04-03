import React, { useEffect, useState } from "react";
import { useI18n } from "../contexts/I18nContext";

import CommonButton from "../components/Button/CommonButton";
import CustomTabs from "../components/Tabs/CustomTabs";
import PageContainer from "../components/Layout/PageContainer";
import PageTitle from "../components/Text/PageTitle";
import Subtitle from "../components/Text/SubTitle";
import InfoText from "../components/Text/InfoText";
import SuccessText from "../components/Text/SussceeText";
import ErrorText from "../components/Text/ErrorText";
import DocCardList from "../components/Card/DocCardList";
import Spinner from "../components/Utils/Spinner";

import api from "../lib/api";

export default function Master_Docs() {
  const { t } = useI18n();
  const [docs, setDocs] = useState([]);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [activeTab, setActiveTab] = useState("tab1");
  const [messageKey, setMessageKey] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    api
      .get("/master_docs")
      .then((res) => setDocs(res.data.docs))
      .catch((err) => console.log(err))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    if (!selectedDoc) return;
    setLoading(true);
    try {
      const res = await api.post("/master_docs/save", { docId: selectedDoc.docid });
      setMessageKey(res.data.message_key);
    } catch (err) {
      console.log(err);
      setMessageKey("msg.error");
    } finally {
      setLoading(false);
    }
  };

  const tabs = [
    {
      key: "tab1",
      label: t("tab1.label") || "Tab 1",
      content: selectedDoc ? (
        <>
          <Subtitle>{selectedDoc.docnm} 상세 정보 수정</Subtitle>
          <CommonButton onClick={handleSave}>{t("btn.save")}</CommonButton>
          {messageKey && (
            messageKey === "msg.success" ? (
              <SuccessText>{t(messageKey)}</SuccessText>
            ) : (
              <ErrorText>{t(messageKey)}</ErrorText>
            )
          )}
          <InfoText>여기서 문서 상세 정보를 수정할 수 있습니다.</InfoText>
        </>
      ) : (
        <InfoText>좌측에서 문서를 선택해주세요.</InfoText>
      ),
    },
    {
      key: "tab2",
      label: t("tab2.label") || "Tab 2",
      content: selectedDoc ? (
        <>
          <Subtitle>{selectedDoc.docnm} 챕터 목록</Subtitle>
          <InfoText>여기서 문서의 챕터를 작성/관리할 수 있습니다.</InfoText>
        </>
      ) : (
        <InfoText>좌측에서 문서를 선택해주세요.</InfoText>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageTitle>{t("menu.master_data.master_docs")}</PageTitle>
      <InfoText>{t("msg.page2.subtitle")}</InfoText>

      {loading && <Spinner />}

      <div style={{ display: "flex", gap: 20, marginTop: 20 }}>
        {/* 좌측 카드 목록 */}
        <div style={{ flex: 1, border: "1px solid #f0f0f0", padding: 10 }}>
          <Subtitle>문서 목록</Subtitle>
          <DocCardList docs={docs} selectedDoc={selectedDoc} onSelect={setSelectedDoc} />
        </div>

        {/* 우측 탭 */}
        <div style={{ flex: 3, border: "1px solid #f0f0f0", padding: 10 }}>
          <CustomTabs activeKey={activeTab} onChange={setActiveTab} tabs={tabs} />
        </div>
      </div>
    </PageContainer>
  );
}