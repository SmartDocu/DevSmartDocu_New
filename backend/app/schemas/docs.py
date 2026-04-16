from typing import Optional
from pydantic import BaseModel


class ProjectItem(BaseModel):
    projectid: int
    projectnm: str


class ProjectsResponse(BaseModel):
    projects: list[ProjectItem]


class DocItem(BaseModel):
    docid: int
    docnm: str
    docdesc: Optional[str] = None
    projectid: int
    projectnm: Optional[str] = None
    tenantnm: Optional[str] = None
    basetemplatenm: Optional[str] = None
    basetemplateurl: Optional[str] = None
    sampleyn: Optional[bool] = False
    editbuttonyn: str = "Y"


class DocsListResponse(BaseModel):
    docs: list[DocItem]


class DocSaveResponse(BaseModel):
    result: str
    docid: Optional[int] = None


class DocSelectRequest(BaseModel):
    docid: int
    docnm: str = ""


class DocSelectResponse(BaseModel):
    """문서 선택 후 갱신된 사용자 컨텍스트"""
    docid: int
    docnm: str
    projectid: str
    tenantid: str
    tenantmanager: str
    projectmanager: str
    editbuttonyn: str
    sampledocyn: str


class ChapterItem(BaseModel):
    chapteruid: str
    docid: int
    chapternm: str
    chapterno: int
    useyn: bool = True
    chaptertemplatenm: Optional[str] = None
    chaptertemplateurl: Optional[str] = None


class ChaptersListResponse(BaseModel):
    chapters: list[ChapterItem]


class ChapterSaveResponse(BaseModel):
    result: str
    chapteruid: Optional[str] = None
