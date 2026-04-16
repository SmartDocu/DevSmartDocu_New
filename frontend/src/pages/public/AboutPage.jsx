export default function AboutPage() {
  const sectionStyle = {
    maxWidth: 950,
    margin: '50px auto 0 auto',
    fontFamily: "'Noto Sans', sans-serif",
  }
  const h2Style = {
    padding: '10px 15px',
    color: '#091747',
    fontSize: 22,
    fontWeight: 700,
    margin: '30px 0 10px 0',
    textAlign: 'left',
  }
  const h3Style = {
    padding: '10px 15px',
    paddingLeft: 50,
    color: '#091747',
    fontSize: 18,
    fontWeight: 700,
    margin: '30px 0 10px 0',
    textAlign: 'left',
  }
  const pStyle = {
    marginTop: 0,
    marginBottom: 25,
    paddingLeft: 20,
    color: '#333',
    fontSize: 18,
    lineHeight: 1.6,
  }
  const imgStyle = {
    display: 'block',
    maxWidth: '100%',
    margin: '30px auto',
  }

  return (
    <div>
      <div style={sectionStyle}>
        <h2 style={h2Style}>SmartDocu는 데이터베이스와의 연동을 통해 문서 작성 과정을 자동화합니다.</h2>
      </div>

      <div style={sectionStyle}>
        <h2 style={h2Style}>기능 구성</h2>
        <p style={pStyle}>
          ODBC를 지원하는 모든 데이터베이스와 연동할 수 있으며, <br />
          문서에 필요한 데이터, 매개변수, 템플릿, 개체를 미리 설정해 두고 <br />
          매개변수 값 변경만으로 문서를 생성합니다.
        </p>
        <img src="/about01.png" alt="기능 구성" style={imgStyle} />
      </div>

      {/* 문서 작성 흐름 */}
      <div style={sectionStyle}>
        <h2 style={h2Style}>문서 작성 흐름</h2>

        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 20, maxWidth: 950, margin: '40px auto' }}>

          <div style={{
            flex: 1, background: '#f7f9fc', border: '1px solid #d8dfeb', borderRadius: 12,
            padding: 20, textAlign: 'center', boxShadow: '0 2px 5px rgba(0,0,0,0.05)',
          }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: '#091747', marginBottom: 8 }}>데이터 설정</div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 26, fontWeight: 700, color: '#091747' }}>→</div>

          <div style={{
            flex: 1, background: '#f7f9fc', border: '1px solid #d8dfeb', borderRadius: 12,
            padding: 20, textAlign: 'center', boxShadow: '0 2px 5px rgba(0,0,0,0.05)',
          }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: '#091747', marginBottom: 8 }}>문서 설정</div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 26, fontWeight: 700, color: '#091747' }}>→</div>

          <div style={{
            flex: 1, background: '#f7f9fc', border: '1px solid #d8dfeb', borderRadius: 12,
            padding: 20, textAlign: 'center', boxShadow: '0 2px 5px rgba(0,0,0,0.05)',
          }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: '#091747', marginBottom: 8 }}>문서 작성</div>
          </div>

        </div>
      </div>

      <div style={sectionStyle}>
        <h3 style={h3Style}>데이터 설정</h3>
        <p style={{ ...pStyle, paddingLeft: 55 }}>ODBC를 지원하는 모든 데이터베이스와 Excel 자료에 대해 연결 정보, 쿼리, 데이터 항목을 정의합니다.</p>
      </div>

      <div style={sectionStyle}>
        <h3 style={h3Style}>문서 설정</h3>
        <p style={{ ...pStyle, paddingLeft: 55 }}>
          문서의 내용을 구성하기 위해 목차, 템플릿 및 템플릿 내 개체를 정의합니다.<br />
          개체에 해당하는 문장, 테이블, 차트는 AI 또는 UI를 통해 설정할 수 있으며,<br />
          AI에는 문장, 표, 차트를 어떻게 작성할지 프롬프트로 지시합니다.
        </p>
      </div>

      <div style={sectionStyle}>
        <h3 style={h3Style}>문서 작성</h3>
        <p style={{ ...pStyle, paddingLeft: 55 }}>문서에 노출된 매개변수에 값을 입력하면, 해당 매개변수를 기준으로 문서가 작성됩니다.</p>
      </div>

      <div style={sectionStyle}>
        <h2 style={h2Style}>문서 설정 - 챕터 관리</h2>
        <p style={pStyle}>
          주제별로 챕터를 분리하고, 템플릿에서 내용을 구성할 시나리오에 따라 항목을 정의합니다.<br />
          정의된 항목은 항목 추출 과정을 통해 데이터화되며, <br />
          이후 단계에서 각 항목에 대해 표현할 문장, 표, 차트의 구성 내용을 설정합니다.
        </p>
        <img src="/about02.png" alt="챕터 관리" style={imgStyle} />
      </div>

      <div style={sectionStyle}>
        <h2 style={h2Style}>문서 설정 - 항목 정의</h2>
        <p style={pStyle}>
          항목 정의는 문서에 작성될 문장, 표, 차트로 표현할 내용을 설정하는 단계이며,<br />
          AI와 UI 두 가지 방식으로 정의할 수 있습니다.
        </p>
        <img src="/about03.png" alt="항목 정의" style={imgStyle} />
      </div>

      <div style={sectionStyle}>
        <h2 style={h2Style}>문서 작성</h2>
        <p style={pStyle}>
          문서에 정의된 매개변수 값을 선택하여 새 문서를 생성합니다.<br />
          선택한 매개변수 값에 따라 챕터 템플릿과 항목 정의를 기반으로 문서가 자동으로 작성됩니다.
        </p>
        <img src="/about04.png" alt="문서 작성" style={imgStyle} />
      </div>
    </div>
  )
}
