"""업로드/API 데이터셋을 보관하는 ExcelServer 모듈 싱글턴.

d2insight의 ReportAgent는 요청마다 새로 생성되는 인스턴스(d2chat의 MCPAgent 같은
앱 전역 싱글턴이 아님)이므로, 업로드 엔드포인트(요청 A)와 이후 보고서 생성 요청(요청 B)이
같은 세션 데이터를 보게 하려면 ExcelServer 자체를 모듈 레벨에서 공유해야 한다.
"""
from d2shared.excel_server import ExcelServer

_excel_server = ExcelServer()


def get_excel_server() -> ExcelServer:
    return _excel_server
