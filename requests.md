
요청 : 
"문서" 메뉴에서 생성기간을 지정후 조회를 하면 문서 목록이 보입니다.                                                              
문서 목록 중 한 문서를 선택한 후  오른쪽 아래에 "신규, 저장, 삭제, 문서 조회, 챕터 조회" 아이콘을 클릭 후 다시 돌아왔을 때 문서  
목록이 보여져야 합니다. 그런데 리셋되어 아무 문서가 없습니다.                                                                    
그리고 문서 목록은 테이블 형태이고 선택된 문서는 그대로 유지되어야 합니다.(테이블 행의 색이 선택된 것과 선택되지 않은 것이       
다릅니다.)                                                                                                                       
그리고 Django의 페이지의 헤더 아래 오른편에 뒤로가기 아이콘이 있는데 이것도 찾아서 넣어주세요.                                   
                                                                                                                                
오른쪽 아래 아이콘 중 "문서 조회"를 클릭하면 "./_old_ref/pages/templates/pages/req_chapter_read.html 또는                        
req_chapters_read.html"을 통해 문서 내용을 확인할 수 있어야 합니다.


요청 : 
CLAUDE.md 파일에서 33줄 아래에 있는 컨텍스트에서 필수적인 부분만 남기고 다른 내용들은 별도 md 파일을 만들어 보관해주세요.


요청 : 
"기준 정보" 메뉴에 대한 내용입니다.

- 문서 관리 : ./_old_ref/pages/templates/pages/master_docs.html
- 챕터 관리 : ./_old_ref/pages/templates/pages/master_chapters.html
- 항목 관리 : ./_old_ref/pages/templates/pages/master_object.html
- Excel 데이터 : ./_old_ref/pages/templates/pages/master_datas_ex.html
- AI 데이터 : ./_old_ref/pages/templates/pages/master_datas_ai.html

이고 아이콘, 버튼, 카드 또는 테이블에서는 행 클릭할 경우 이동되거나 실행되는 부분도 모두 Django와 같게 해 주세요.





