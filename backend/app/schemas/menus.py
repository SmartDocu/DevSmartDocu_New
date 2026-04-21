from typing import Optional
from pydantic import BaseModel


class MenuItem(BaseModel):
    menucd: str
    default_text: Optional[str] = None
    description: Optional[str] = None
    iconnm: Optional[str] = None
    orderno: Optional[int] = None
    useyn: Optional[bool] = True
    rolecd: Optional[str] = None
    route_path: Optional[str] = None


class MenusListResponse(BaseModel):
    menus: list[MenuItem]


class MenuSaveRequest(BaseModel):
    menucd: str
    default_text: Optional[str] = None
    description: Optional[str] = None
    iconnm: Optional[str] = None
    orderno: Optional[int] = None
    useyn: Optional[bool] = True
    rolecd: Optional[str] = None
    route_path: Optional[str] = None


class MenuSaveResponse(BaseModel):
    result: str
    menucd: str


class TranslationItem(BaseModel):
    menucd: str
    languagecd: str
    translated_text: Optional[str] = None


class TranslationsListResponse(BaseModel):
    translations: list[TranslationItem]


class TranslationSaveRequest(BaseModel):
    languagecd: str
    translated_text: Optional[str] = None


class LanguageItem(BaseModel):
    languagecd: str
    languagenm: str
    useyn: Optional[bool] = True
    orderno: Optional[int] = None


class LanguagesListResponse(BaseModel):
    languages: list[LanguageItem]


class CodeItem(BaseModel):
    codevalue: str
    term_key: str
    default_name: Optional[str] = None


class CodesListResponse(BaseModel):
    codes: list[CodeItem]
