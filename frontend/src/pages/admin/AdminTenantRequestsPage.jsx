import { useState } from 'react'
import { useAdminTenantRequests } from '@/hooks/useAdmin'

export default function AdminTenantRequestsPage() {
  const { data = {}, isLoading } = useAdminTenantRequests()
  const [selected, setSelected] = useState(null)

  const { tenantreqs = [] } = data

  const handleRowClick = (row) => {
    setSelected(row)
  }

  const llmLimitLabel = (val) => {
    if (val === true || val === 'true') return '√'
    if (val === false || val === 'false') return '-'
    return val || '-'
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>요청 관리</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 20, minHeight: '80%' }}>
        {/* 왼쪽: 요청 목록 */}
        <div style={{ flex: 0.4, padding: '0 20px' }}>
          <h3>요청 목록</h3>
          <div className="table-container">
            {isLoading ? (
              <div style={{ textAlign: 'center', padding: 32 }}><div className="spinner" /></div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th style={{ width: '15%' }}>요청일시</th>
                    <th style={{ width: '17%' }}>사업자<br />등록번호</th>
                    <th style={{ width: '18%' }}>사업자명</th>
                    <th style={{ width: '12%' }}>과금<br />사용자수</th>
                  </tr>
                </thead>
                <tbody>
                  {tenantreqs.map((req) => (
                    <tr
                      key={req.tenantrequid || req.createdts}
                      className={selected?.tenantrequid === req.tenantrequid ? 'selected-row' : ''}
                      style={{ cursor: 'pointer' }}
                      onClick={() => handleRowClick(req)}
                    >
                      <td className="info">{req.createdts || ''}</td>
                      <td className="info">{req.bizregno || ''}</td>
                      <td className="info">{req.tenantnm || ''}</td>
                      <td className="info">{req.billingusercnt ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* 오른쪽: 요청 상세 */}
        <div style={{ flex: 0.7, paddingLeft: 20 }}>
          <h3>요청 상세</h3>
          <div>
            <div className="form-group-left">
              <span style={{ width: 180, flexShrink: 0 }}>요청일시</span>
              <input
                style={{ width: 200, flex: 'none', textAlign: 'right' }}
                type="text"
                value={selected?.createdts || ''}
                disabled
                readOnly
              />
            </div>

            <div className="form-group-left">
              <span style={{ width: 180, flexShrink: 0 }}>사용자수</span>
              <input
                style={{ width: 200, flex: 'none', textAlign: 'right' }}
                type="text"
                value={selected?.billingusercnt ?? ''}
                disabled
                readOnly
              />
            </div>

            <div className="form-group-left">
              <span style={{ width: 180, flexShrink: 0 }}>LLM사용제한여부</span>
              <input
                style={{ width: 200, flex: 'none', textAlign: 'right' }}
                type="text"
                value={selected ? llmLimitLabel(selected.llmlimityn) : ''}
                disabled
                readOnly
              />
            </div>

            <div className="form-group-left" style={{ alignItems: 'flex-start' }}>
              {/* 기업 정보 */}
              <div style={{ alignSelf: 'flex-start' }}>
                <h3>기업 정보</h3>
                <div className="form-group-left">
                  <label style={{ width: 180 }}>회사(법인) 명칭:</label>
                  <input
                    style={{ width: 200, flex: 'none', textAlign: 'right' }}
                    type="text"
                    value={selected?.tenantnm || ''}
                    disabled
                    readOnly
                  />
                </div>
                <div className="form-group-left">
                  <label style={{ width: 180 }}>법인(사업자) 등록번호:</label>
                  <input
                    style={{ width: 200, flex: 'none', textAlign: 'right' }}
                    type="text"
                    value={selected?.bizregno || ''}
                    disabled
                    readOnly
                  />
                </div>
                {selected?.bizregfilenm && (
                  <div className="form-group-left">
                    <label style={{ width: 180 }}>사업자 등록증:</label>
                    {selected.bizregfileurl ? (
                      <a href={selected.bizregfileurl} target="_blank" rel="noopener noreferrer">
                        {selected.bizregfilenm}
                      </a>
                    ) : (
                      <span>{selected.bizregfilenm}</span>
                    )}
                  </div>
                )}
              </div>

              {/* 서비스 담당자 정보 */}
              <div style={{ alignSelf: 'flex-start', marginLeft: 200 }}>
                <h3>서비스 담당자 정보</h3>
                <div className="form-group-left">
                  <label style={{ width: 180 }}>성명:</label>
                  <input
                    style={{ width: 200, flex: 'none', textAlign: 'right' }}
                    type="text"
                    value={selected?.managernm || ''}
                    disabled
                    readOnly
                  />
                </div>
                <div className="form-group-left">
                  <label style={{ width: 180 }}>부서:</label>
                  <input
                    style={{ width: 200, flex: 'none', textAlign: 'right' }}
                    type="text"
                    value={selected?.managerdepart || ''}
                    disabled
                    readOnly
                  />
                </div>
                <div className="form-group-left">
                  <label style={{ width: 180 }}>직책:</label>
                  <input
                    style={{ width: 200, flex: 'none', textAlign: 'right' }}
                    type="text"
                    value={selected?.managerposition || ''}
                    disabled
                    readOnly
                  />
                </div>
                <div className="form-group-left">
                  <label style={{ width: 180 }}>이메일주소:</label>
                  <input
                    style={{ width: 200, flex: 'none', textAlign: 'right' }}
                    type="email"
                    value={selected?.email || ''}
                    disabled
                    readOnly
                  />
                </div>
                <div className="form-group-left">
                  <label style={{ width: 180 }}>전화번호:</label>
                  <input
                    style={{ width: 200, flex: 'none', textAlign: 'right' }}
                    type="tel"
                    value={selected?.telno || ''}
                    disabled
                    readOnly
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
