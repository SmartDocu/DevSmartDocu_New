from typing import Optional
from pydantic import BaseModel


class ObjectTypeItem(BaseModel):
    objecttypecd: str
    objecttypenm: Optional[str] = None
    orderno: Optional[int] = None


class ObjectTypesResponse(BaseModel):
    objecttypes: list[ObjectTypeItem]


class ObjectItem(BaseModel):
    objectuid: Optional[str] = None
    chapteruid: Optional[str] = None
    objectnm: Optional[str] = None
    objectdesc: Optional[str] = None
    objecttypecd: Optional[str] = None
    objecttypenm: Optional[str] = None
    gentypecd: Optional[str] = None
    useyn: Optional[bool] = True
    orderno: Optional[int] = None
    objectsettingyn: Optional[bool] = False
    createdts: Optional[str] = None
    objecttypenm_full: Optional[str] = None
    creatornm: Optional[str] = None


class ObjectsListResponse(BaseModel):
    objects: list[ObjectItem]


class ObjectSaveRequest(BaseModel):
    chapteruid: str
    objectuid: Optional[str] = None
    objectdesc: Optional[str] = None
    objecttypecd_orig: Optional[str] = None
    objecttypecd: Optional[str] = None
    useyn: bool = True
    orderno: Optional[int] = None
