from typing import Optional
from pydantic import BaseModel


class DbConnectorItem(BaseModel):
    connectid: int
    connectnm: str


class DbConnectorsResponse(BaseModel):
    connectors: list[DbConnectorItem]


class DataItem(BaseModel):
    datauid: Optional[str] = None
    projectid: Optional[int] = None
    projectnm: Optional[str] = None
    datanm: Optional[str] = None
    datasourcecd: Optional[str] = None
    connectid: Optional[str] = None
    connectnm: Optional[str] = None
    query: Optional[str] = None
    excelurl: Optional[str] = None
    excelnm: Optional[str] = None
    sourcedatauid: Optional[str] = None
    gensentence: Optional[str] = None


class DatasListResponse(BaseModel):
    datas: list[DataItem]


class DataColItem(BaseModel):
    datauid: str
    querycolnm: str
    dispcolnm: Optional[str] = None
    datatypecd: Optional[str] = None
    measureyn: Optional[bool] = False
    orderno: Optional[int] = None


class DataColsResponse(BaseModel):
    columns: list[DataColItem]


class DbDataSaveRequest(BaseModel):
    datauid: Optional[str] = None
    projectid: int
    datanm: str
    connectid: Optional[str] = None
    query: Optional[str] = None


class AiDataSaveRequest(BaseModel):
    datauid: Optional[str] = None
    projectid: int
    datanm: str
    sourcedatauid: Optional[str] = None
    sentence: Optional[str] = None
