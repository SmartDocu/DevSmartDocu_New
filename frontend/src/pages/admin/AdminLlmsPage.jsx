import { useState } from 'react'
import { App } from 'antd'
import { useAdminLlms, useSaveLlm, useDeleteLlm } from '@/hooks/useAdmin'

export default function AdminLlmsPage() {
  const { message, modal } = App.useApp()
  const { data = {}, isLoading } = useAdminLlms()
  const saveMutation = useSaveLlm()
  const deleteMutation = useDeleteLlm()

  const { llmmodels = [] } = data

  const EMPTY = { llmvendornm: '', llmmodelnm: '', llmmodelnicknm: '', useyn: true, isdefault: false, apikey: '' }
  const [form, setForm] = useState(EMPTY)
  const [selectedRow, setSelectedRow] = useState(null)

  const handleRowClick = (row) => {
    setSelectedRow(row)
    setForm({
      llmvendornm: row.llmvendornm || '',
      llmmodelnm: row.llmmodelnm || '',
      llmmodelnicknm: row.llmmodelnicknm || '',
      useyn: !!row.useyn,
      isdefault: !!row.isdefault,
      apikey: '',
    })
  }

  const handleNew = () => {
    setSelectedRow(null)
    setForm(EMPTY)
  }

  const handleSave = () => {
    if (!form.llmmodelnm.trim()) { message.warning('LLM 모델명을 입력하세요.'); return }
    saveMutation.mutate(
      {
        llmmodelnm: form.llmmodelnm,
        llmvendornm: form.llmvendornm || null,
        llmmodelnicknm: form.llmmodelnicknm || null,
        useyn: form.useyn,
        isdefault: form.isdefault,
        apikey: form.apikey || '',
      },
      { onSuccess: handleNew },
    )
  }

  const handleDelete = () => {
    if (!selectedRow) { message.warning('삭제할 LLM을 먼저 선택하세요.'); return }
    modal.confirm({
      title: '삭제 확인',
      content: `"${selectedRow.llmmodelnm}" LLM을 삭제하시겠습니까?`,
      okText: '삭제', cancelText: '취소', okButtonProps: { danger: true },
      onOk: () => deleteMutation.mutate(selectedRow.llmmodelnm, { onSuccess: handleNew }),
    })
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>LLM 관리</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 왼쪽: LLM 목록 */}
        <div style={{ flex: '60%' }}>
          <h3>LLM 목록</h3>
          <div className="table-container">
            {isLoading ? (
              <div style={{ textAlign: 'center', padding: 32 }}><div className="spinner" /></div>
            ) : (
              <table id="llms-table">
                <thead>
                  <tr>
                    <th style={{ width: '10%' }}>LLM 벤더명</th>
                    <th style={{ width: '25%' }}>LLM 모델명</th>
                    <th style={{ width: '20%' }}>LLM 모델 별칭</th>
                    <th style={{ width: '8%' }} className="info">사용</th>
                    <th style={{ width: '10%' }}>등록자</th>
                    <th style={{ width: '10%' }}>등록일시</th>
                  </tr>
                </thead>
                <tbody>
                  {llmmodels.map((llm) => (
                    <tr
                      key={llm.llmmodelnm}
                      className={selectedRow?.llmmodelnm === llm.llmmodelnm ? 'selected-row' : ''}
                      style={{ cursor: 'pointer' }}
                      onClick={() => handleRowClick(llm)}
                    >
                      <td>{llm.llmvendornm}</td>
                      <td>{llm.llmmodelnm}</td>
                      <td>{llm.llmmodelnicknm}</td>
                      <td className="info">{llm.useyn ? '✔' : ''}</td>
                      <td>{llm.createuser}</td>
                      <td>{llm.createdts}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* 오른쪽: LLM 상세 */}
        <div style={{ flex: '40%' }}>
          <h3>LLM 상세</h3>
          <div className="form-group">
            <label>LLM 벤더명:</label>
            <input
              type="text"
              value={form.llmvendornm}
              onChange={(e) => setForm((f) => ({ ...f, llmvendornm: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label>LLM 모델명:</label>
            <input
              type="text"
              value={form.llmmodelnm}
              onChange={(e) => setForm((f) => ({ ...f, llmmodelnm: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label>LLM 모델별칭:</label>
            <input
              type="text"
              value={form.llmmodelnicknm}
              autoComplete="off"
              onChange={(e) => setForm((f) => ({ ...f, llmmodelnicknm: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label>사용:</label>
            <input
              type="checkbox"
              checked={form.useyn}
              onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
            />
          </div>
          <div className="form-group">
            <label>기본 모델:</label>
            <input
              type="checkbox"
              checked={form.isdefault}
              onChange={(e) => setForm((f) => ({ ...f, isdefault: e.target.checked }))}
            />
          </div>
          <div className="form-group">
            <label>API Key:</label>
            <input
              type="password"
              value={form.apikey}
              placeholder="변경 시에만 입력"
              autoComplete="new-password"
              onChange={(e) => setForm((f) => ({ ...f, apikey: e.target.value }))}
            />
            <small style={{ color: '#888' }}>※ 기존 키는 표시되지 않습니다.</small>
          </div>

          <div className="button-group">
            <button type="button" className="icon-btn" onClick={handleNew}>
              <div className="icon-wrapper">
                <img src="/icons/new.svg" className="icon-img new-icon" title="신규" alt="신규" />
                <span className="icon-label">신규</span>
              </div>
            </button>
            <button type="button" className="icon-btn" onClick={handleSave} disabled={saveMutation.isPending}>
              <div className="icon-wrapper">
                <img src="/icons/save.svg" className="icon-img save-icon" title="저장" alt="저장" />
                <span className="icon-label">저장</span>
              </div>
            </button>
            <button type="button" className="icon-btn" onClick={handleDelete} disabled={deleteMutation.isPending}>
              <div className="icon-wrapper">
                <img src="/icons/delete.svg" className="icon-img del-icon" title="삭제" alt="삭제" />
                <span className="icon-label">삭제</span>
              </div>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
