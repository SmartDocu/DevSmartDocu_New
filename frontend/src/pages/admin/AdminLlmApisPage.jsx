import { useState } from 'react'
import { App } from 'antd'
import { useAdminLlmApis, useSaveLlmApi, useDeleteLlmApi } from '@/hooks/useAdmin'

export default function AdminLlmApisPage() {
  const { message, modal } = App.useApp()
  const { data = {}, isLoading } = useAdminLlmApis()
  const saveMutation = useSaveLlmApi()
  const deleteMutation = useDeleteLlmApi()

  const { llmapis = [], llmmodels = [], tenants = [] } = data

  const EMPTY = { llmapiuid: '', llmmodelnm: '', apikey: '', usetypecd: '', desc: '' }
  const [form, setForm] = useState(EMPTY)
  const [selectedRow, setSelectedRow] = useState(null)

  const handleRowClick = (row) => {
    setSelectedRow(row)
    setForm({
      llmapiuid: row.llmapiuid || '',
      llmmodelnm: row.llmmodelnm || '',
      apikey: '',
      usetypecd: row.usetypecd || '',
      desc: row.usetypecd === 'D' ? (row.desc || '') : '',
    })
  }

  const handleNew = () => {
    setSelectedRow(null)
    setForm(EMPTY)
  }

  const handleUsetypeChange = (val) => {
    setForm((f) => ({ ...f, usetypecd: val, desc: val !== 'D' ? '' : f.desc }))
  }

  const handleSave = () => {
    if (!form.llmmodelnm) { message.warning('LLM 모델을 선택하세요.'); return }
    if (!form.usetypecd) { message.warning('사용 유형을 선택하세요.'); return }
    saveMutation.mutate(
      {
        llmapiuid: form.llmapiuid || null,
        llmmodelnm: form.llmmodelnm,
        apikey: form.apikey || '',
        usetypecd: form.usetypecd,
        desc: form.usetypecd === 'D' ? (form.desc || null) : null,
      },
      { onSuccess: handleNew },
    )
  }

  const handleDelete = () => {
    if (!selectedRow) { message.warning('삭제할 LLM API를 먼저 선택하세요.'); return }
    modal.confirm({
      title: '삭제 확인',
      content: '정말 삭제하시겠습니까?',
      okText: '삭제', cancelText: '취소', okButtonProps: { danger: true },
      onOk: () => deleteMutation.mutate(selectedRow.llmapiuid, { onSuccess: handleNew }),
    })
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>LLM API 관리</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* 왼쪽: LLM API 목록 */}
        <div style={{ flex: '60%' }}>
          <h3>LLM API 목록</h3>
          <div className="table-container">
            {isLoading ? (
              <div style={{ textAlign: 'center', padding: 32 }}><div className="spinner" /></div>
            ) : (
              <table id="llmapis-table">
                <thead>
                  <tr>
                    <th style={{ width: '25%' }}>LLM 모델명</th>
                    <th style={{ width: '8%' }}>사용 유형</th>
                    <th style={{ width: '10%' }}>비고(기업명)</th>
                    <th style={{ width: '10%' }}>등록자</th>
                    <th style={{ width: '10%' }}>등록일시</th>
                  </tr>
                </thead>
                <tbody>
                  {llmapis.map((api) => (
                    <tr
                      key={api.llmapiuid}
                      className={selectedRow?.llmapiuid === api.llmapiuid ? 'selected-row' : ''}
                      style={{ cursor: 'pointer' }}
                      onClick={() => handleRowClick(api)}
                    >
                      <td>{api.llmmodelnm}</td>
                      <td>{api.usetypenm}</td>
                      <td>{api.desc || ''}</td>
                      <td>{api.createuser}</td>
                      <td>{api.createdts}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* 오른쪽: LLM API 상세 */}
        <div style={{ flex: '40%' }}>
          <h3>LLM API 상세</h3>
          <input type="hidden" value={form.llmapiuid} />

          <div className="form-group">
            <label>LLM 모델명:</label>
            <select
              value={form.llmmodelnm}
              onChange={(e) => setForm((f) => ({ ...f, llmmodelnm: e.target.value }))}
              required
            >
              <option value="">사용 모델을 선택하세요</option>
              {llmmodels.map((m) => (
                <option key={m.llmmodelnm} value={m.llmmodelnm}>
                  {m.llmvendornm} → {m.llmmodelnm}
                </option>
              ))}
            </select>
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

          <div className="form-group">
            <label>사용 유형:</label>
            <select
              value={form.usetypecd}
              onChange={(e) => handleUsetypeChange(e.target.value)}
              required
            >
              <option value="">사용 유형을 선택하세요</option>
              <option value="R">Round</option>
              <option value="D">Direct</option>
              <option value="N">No</option>
            </select>
          </div>

          <div className="form-group">
            <label>비고:</label>
            <select
              value={form.desc}
              disabled={form.usetypecd !== 'D'}
              onChange={(e) => setForm((f) => ({ ...f, desc: e.target.value }))}
            >
              <option value="">기업을 선택하세요</option>
              {tenants.map((t) => (
                <option key={t.tenantnm} value={t.tenantnm}>{t.tenantnm}</option>
              ))}
            </select>
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
