from typing import Optional
from pydantic import BaseModel


class TermItem(BaseModel):
    termkey: str
    termgroupcd: Optional[str] = None
    default_text: Optional[str] = None
    description: Optional[str] = None
    useyn: Optional[bool] = True


class TermsListResponse(BaseModel):
    terms: list[TermItem]


class TermSaveRequest(BaseModel):
    termkey: str
    termgroupcd: Optional[str] = None
    default_text: Optional[str] = None
    description: Optional[str] = None
    useyn: Optional[bool] = True


class TermSaveResponse(BaseModel):
    result: str
    termkey: str


class TranslationItem(BaseModel):
    termkey: str
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
