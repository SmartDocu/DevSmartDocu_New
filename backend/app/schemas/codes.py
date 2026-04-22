from typing import Optional
from pydantic import BaseModel


class CodeAdminItem(BaseModel):
    codegroupcd: str
    codevalue: str
    default_name: Optional[str] = None
    orderno: Optional[int] = None
    useyn: Optional[bool] = True


class CodesAdminListResponse(BaseModel):
    codes: list[CodeAdminItem]


class CodeSaveRequest(BaseModel):
    codegroupcd: str
    codevalue: str
    default_name: Optional[str] = None
    orderno: Optional[int] = None
    useyn: Optional[bool] = True


class CodeSaveResponse(BaseModel):
    result: str
    codegroupcd: str
    codevalue: str


class CodeTranslationItem(BaseModel):
    codegroupcd: str
    codevalue: str
    languagecd: str
    translated_text: Optional[str] = None
    translated_desc: Optional[str] = None


class CodeTranslationsListResponse(BaseModel):
    translations: list[CodeTranslationItem]


class CodeTranslationSaveRequest(BaseModel):
    languagecd: str
    translated_text: Optional[str] = None
    translated_desc: Optional[str] = None
