import { useState } from 'react'
import { App, Modal, Popconfirm } from 'antd'
import { useOrgTenantLlms, useSaveTenantLlm, useDeleteTenantLlm } from '@/hooks/useOrg'

const roStyle = { backgroundColor: '#f0f0f0', color: '#555', border: '1px solid #ccc' }

const EMPTY_FORM = { jobnm: '', llmmodelnm: '', apikey: '' }

export default function OrgTenantLlmsPage() {
  const { message } = App.useApp()
  const { data = {}, isLoading } = useOrgTenantLlms()
  const saveMutation = useSaveTenantLlm()
  const deleteMutation = useDeleteTenantLlm()

  const [form, setForm] = useState(EMPTY_FORM)
  const [selectedType, setSelectedType] = useState(null)  // 'tenant' | 'project'
  const [selectedId,   setSelectedId]   = useState(null)
  const [selectedRow,  setSelectedRow]  = useState(null)

  const { tenant = {}, projects = [], llmmodels = [] } = data

  const handleTenantRowClick = (row) => {
    setSelectedType('tenant')
    setSelectedId(row.tenantid?.toString())
    setSelectedRow(row)
    setForm({ jobnm: row.tenantnm || '', llmmodelnm: row.llmmodelnm || '', apikey: '' })
  }

  const handleProjectRowClick = (row) => {
    setSelectedType('project')
    setSelectedId(row.projectid?.toString())
    setSelectedRow(row)
    setForm({ jobnm: row.projectnm || '', llmmodelnm: row.llmmodelnm || '', apikey: '' })
  }

  const handleSave = () => {
    if (!selectedType) { message.warning('선택된 항목이 없습니다.'); return }
    const body = selectedType === 'tenant'
      ? { tenantid: selectedId, llmmodelnm: form.llmmodelnm || null, apikey: form.apikey || '' }
      : { projectid: selectedId, llmmodelnm: form.llmmodelnm || null, apikey: form.apikey || '' }
    saveMutation.mutate(body, {
      onSuccess: () => message.success('저장되었습니다.'),
      onError: (err) => message.error(err.response?.data?.detail || '저장 실패'),
    })
  }

  const handleDelete = () => {
    if (!selectedType) return
    const label = selectedType === 'tenant' ? '기업' : `프로젝트 "${form.jobnm}"`
    Modal.confirm({
      title: '삭제 확인',
      content: `정말 ${label}의 LLM 정보를 삭제하시겠습니까?`,
      okText: '삭제', cancelText: '취소', okButtonProps: { danger: true },
      onOk: () => {
        const body = selectedType === 'tenant' ? { tenantid: selectedId } : { projectid: selectedId }
        deleteMutation.mutate(body, {
          onSuccess: () => { message.success('삭제되었습니다.'); setSelectedType(null); setSelectedId(null); setForm(EMPTY_FORM) },
          onError: (err) => message.error(err.response?.data?.detail || '삭제 실패'),
        })
      },
    })
  }

  const jobnmLabel = selectedType === 'tenant' ? '기업명:' : selectedType === 'project' ? '프로젝트명:' : '작업명:'

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>기업 LLM 관리</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 왼쪽: 기업 + 프로젝트 테이블 */}
        <div style={{ flex: '60%' }}>
          <div>
            <h3>기업 LLM 정보</h3>
            <div className="table-container" style={{ height: 100 }}>
              <table id="tenant-table" style={{ cursor: 'pointer' }}>
                <thead>
                  <tr>
                    <th style={{ width: '15%' }}>기업명</th>
                    <th style={{ width: '25%' }}>LLM 모델명</th>
                    <th style={{ width: '15%' }}>LLM 사용방법</th>
                    <th style={{ width: '10%' }}>활성</th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr><td colSpan={4} style={{ textAlign: 'center' }}>로딩 중...</td></tr>
                  ) : tenant.tenantid ? (
                    <tr
                      className={selectedType === 'tenant' && selectedId === tenant.tenantid?.toString() ? 'selected-row' : ''}
                      onClick={() => handleTenantRowClick(tenant)}
                    >
                      <td>{tenant.tenantnm}</td>
                      <td>{tenant.llmmodelnicknm || ''}</td>
                      <td style={{ textAlign: 'center' }}>{tenant.llmmodeluseyn ? '고객사' : '서비스사'}</td>
                      <td style={{ textAlign: 'center' }}>{tenant.llmmodelactiveyn ? '✔' : ''}</td>
                    </tr>
                  ) : (
                    <tr><td colSpan={4} style={{ textAlign: 'center', color: '#888' }}>데이터가 없습니다.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div>
            <h3>프로젝트 LLM 정보</h3>
            <div className="table-container" style={{ height: 500 }}>
              <table id="project-table" style={{ cursor: 'pointer' }}>
                <thead>
                  <tr>
                    <th style={{ width: '15%' }}>프로젝트명</th>
                    <th style={{ width: '25%' }}>프로젝트설명</th>
                    <th style={{ width: '15%' }}>LLM 모델명</th>
                    <th style={{ width: '10%' }}>활성</th>
                  </tr>
                </thead>
                <tbody>
                  {projects.length === 0 ? (
                    <tr><td colSpan={4} style={{ textAlign: 'center', color: '#888' }}>등록된 프로젝트가 없습니다.</td></tr>
                  ) : projects.map((p) => (
                    <tr key={p.projectid}
                      className={selectedType === 'project' && selectedId === p.projectid?.toString() ? 'selected-row' : ''}
                      onClick={() => handleProjectRowClick(p)}
                    >
                      <td>{p.projectnm}</td>
                      <td>{p.projectdesc || ''}</td>
                      <td>{p.llmmodelnicknm || ''}</td>
                      <td style={{ textAlign: 'center' }}>{p.llmmodelactiveyn ? '✔' : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* 오른쪽: LLM 상세 */}
        <div style={{ flex: '40%' }}>
          <h3>LLM 상세</h3>

          <div className="form-group">
            <label>{jobnmLabel}</label>
            <input type="text" value={form.jobnm} readOnly style={roStyle} />
          </div>

          <div className="form-group">
            <label htmlFor="llmmodelnm">LLM 모델명:</label>
            <select id="llmmodelnm" value={form.llmmodelnm}
              onChange={(e) => setForm(f => ({ ...f, llmmodelnm: e.target.value }))}>
              <option value="">-- LLM 모델 선택 --</option>
              {llmmodels.map((m) => (
                <option key={m.llmmodelnm} value={m.llmmodelnm}>{m.llmmodelnicknm}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>API Key:</label>
            <input type="password" value={form.apikey} placeholder="변경 시에만 입력"
              autoComplete="new-password"
              onChange={(e) => setForm(f => ({ ...f, apikey: e.target.value }))} />
            <small style={{ color: '#888' }}>※ 기존 키는 표시되지 않습니다.</small>
          </div>

          <div className="button-group">
            <button type="button" className="icon-btn" onClick={handleSave} disabled={saveMutation.isPending}>
              <div className="icon-wrapper">
                <img src="/icons/save.svg" className="icon-img save-icon" alt="저장" />
                <span className="icon-label">저장</span>
              </div>
            </button>
            <button type="button" className="icon-btn" onClick={handleDelete} disabled={deleteMutation.isPending || !selectedType}>
              <div className="icon-wrapper">
                <img src="/icons/delete.svg" className="icon-img del-icon" alt="삭제" />
                <span className="icon-label">삭제</span>
              </div>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
