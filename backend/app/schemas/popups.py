from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator, model_validator


class PopupAdminItem(BaseModel):
    popupid: int
    title: str
    content_type: str = "page"
    pageurl: Optional[str] = None
    body: Optional[str] = None
    button_text: Optional[str] = None
    button_url: Optional[str] = None
    startdts: Optional[str] = None
    enddts: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    lefts: Optional[int] = None
    top: Optional[int] = None
    useyn: Optional[bool] = True
    deactivateday: Optional[int] = None
    mainlogin: Optional[str] = None


class PopupsAdminListResponse(BaseModel):
    popups: list[PopupAdminItem]


class PopupSaveRequest(BaseModel):
    title: str
    content_type: str = "page"
    pageurl: Optional[str] = None
    body: Optional[str] = None
    button_text: Optional[str] = None
    button_url: Optional[str] = None
    startdts: str
    enddts: str
    width: Optional[int] = 480
    height: Optional[int] = 300
    lefts: Optional[int] = 120
    top: Optional[int] = 120
    useyn: Optional[bool] = True
    deactivateday: Optional[int] = 7
    mainlogin: Optional[str] = "M"

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("제목은 필수입니다.")
        return v

    @field_validator("content_type")
    @classmethod
    def _content_type_valid(cls, v: str) -> str:
        if v not in ("page", "inline"):
            raise ValueError("content_type은 'page' 또는 'inline'이어야 합니다.")
        return v

    @field_validator("startdts", "enddts")
    @classmethod
    def _dts_parseable(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            raise ValueError("날짜/시간 형식이 올바르지 않습니다. 예: 2026-01-01T00:00:00+00:00")
        return v

    @model_validator(mode="after")
    def _check_period_and_pageurl(self) -> "PopupSaveRequest":
        start = datetime.fromisoformat(self.startdts.replace("Z", "+00:00"))
        end = datetime.fromisoformat(self.enddts.replace("Z", "+00:00"))
        if end <= start:
            raise ValueError("종료일시는 시작일시보다 이후여야 합니다.")
        if self.content_type == "page" and not (self.pageurl or "").strip():
            raise ValueError("content_type이 'page'이면 pageurl은 필수입니다.")
        return self


class PopupSaveResponse(BaseModel):
    result: str
    popupid: int


class PopupTranslationItem(BaseModel):
    popupid: int
    languagecd: str
    title: Optional[str] = None
    body: Optional[str] = None
    button_text: Optional[str] = None


class PopupTranslationsListResponse(BaseModel):
    translations: list[PopupTranslationItem]


class PopupTranslationSaveRequest(BaseModel):
    languagecd: str
    title: Optional[str] = None
    body: Optional[str] = None
    button_text: Optional[str] = None
