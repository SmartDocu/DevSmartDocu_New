from typing import Optional
from pydantic import BaseModel


class DbConnectorItem(BaseModel):
    connuid: str
    connnm: str


class DbConnectorsResponse(BaseModel):
    connectors: list[DbConnectorItem]


class DataItem(BaseModel):
    datauid: Optional[str] = None
    projectid: Optional[int] = None
    projectnm: Optional[str] = None
    datanm: Optional[str] = None
    datasourcecd: Optional[str] = None
    connuid: Optional[str] = None
    connectnm: Optional[str] = None
    query: Optional[str] = None
    querybasis: Optional[str] = None
    databasiscd: Optional[str] = None
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
    useyn: Optional[bool] = True
    orderno: Optional[int] = None
    field_path: Optional[str] = None


class ApiConnectorItem(BaseModel):
    connuid: str
    connnm: str


class ApiConnectorsResponse(BaseModel):
    connectors: list[ApiConnectorItem]


class ApiParamItem(BaseModel):
    paramnm: str
    param_locationcd: Optional[str] = 'query'
    datatypecd: Optional[str] = 'string'
    is_required: bool = False
    testvalue: Optional[str] = None
    is_fixed: bool = False
    fixed_value: Optional[str] = None
    desc: Optional[str] = None
    orderno: Optional[int] = None


class ApiDataSaveRequest(BaseModel):
    datauid: Optional[str] = None
    projectid: int
    datanm: str
    connuid: Optional[str] = None
    endpoint: Optional[str] = None
    desc: Optional[str] = None
    useyn: bool = True
    params: Optional[list[ApiParamItem]] = None


class DataColsResponse(BaseModel):
    columns: list[DataColItem]


class DbDataSaveRequest(BaseModel):
    datauid: Optional[str] = None
    projectid: int
    datanm: str
    desc: Optional[str] = None
    connuid: Optional[str] = None
    query: Optional[str] = None
    databasiscd: Optional[str] = None
    querybasis: Optional[str] = None


class AiDataSaveRequest(BaseModel):
    datauid: Optional[str] = None
    projectid: int
    datanm: str
    sourcedatauid: Optional[str] = None
    sentence: Optional[str] = None


class DfColItem(BaseModel):
    querycolnm: str
    dispcolnm: Optional[str] = None
    datatypecd: Optional[str] = None
    measureyn: Optional[bool] = False
    orderno: Optional[int] = None


class DfDataSaveRequest(BaseModel):
    datauid: Optional[str] = None
    projectid: int
    datanm: str
    sourcedatauid: Optional[str] = None
    gensentence: Optional[str] = None
    docid: int
    is_multirow: Optional[str] = None
    cols: Optional[list[DfColItem]] = None


class DfvDataSaveRequest(BaseModel):
    datauid: Optional[str] = None
    projectid: int
    datanm: str
    sourcedatauid: Optional[str] = None
    gensentence: Optional[str] = None
    dfv_docid: int
    is_multirow: Optional[str] = None
    cols: Optional[list[DfColItem]] = None


class AiPreviewRequest(BaseModel):
    sourcedatauid: str
    gensentence: str
    docid: Optional[int] = None
