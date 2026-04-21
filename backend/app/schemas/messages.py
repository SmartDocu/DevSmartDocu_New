from typing import Optional
from pydantic import BaseModel


class MessageItem(BaseModel):
    messagekey: str
    messagetypecd: Optional[str] = None
    default_message: Optional[str] = None
    description: Optional[str] = None
    useyn: Optional[bool] = True


class MessagesListResponse(BaseModel):
    messages: list[MessageItem]


class MessageSaveRequest(BaseModel):
    messagekey: str
    messagetypecd: Optional[str] = None
    default_message: Optional[str] = None
    description: Optional[str] = None
    useyn: Optional[bool] = True


class MessageSaveResponse(BaseModel):
    result: str
    messagekey: str


class MessageTranslationItem(BaseModel):
    messagekey: str
    languagecd: str
    translated_text: Optional[str] = None


class MessageTranslationsListResponse(BaseModel):
    translations: list[MessageTranslationItem]


class MessageTranslationSaveRequest(BaseModel):
    languagecd: str
    translated_text: Optional[str] = None
