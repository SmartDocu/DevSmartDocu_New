import { useState } from 'react'
import { App, Modal, Popconfirm } from 'antd'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useOrgProjects, useSaveOrgProject, useDeleteOrgProject } from '@/hooks/useOrg'

const roStyle = { backgroundColor: '#f0f0f0', color: '#555', border: '1px solid #ccc' }

const EMPTY_FORM = {
  projectid: '', projectnm: '', projectdesc: '',
  useyn: true, creatornm: '', createdts: '',
}

export default function OrgProjectsPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { user } = useAuthStore()
  const roleid = user?.roleid

  const paramTenantid = roleid === 7 ? searchParams.get('tenantid') : null

  const { data = {}, isLoading } = useOrgProjects(paramTenantid)
  const saveMutation = useSaveOrgProject()
  const deleteMutation = useDeleteOrgProject()

  const [form, setForm] = useState(EMPTY_FORM)
  const [selectedRow, setSelectedRow] = useState(null)

  const { projects = [], tenantnm, tenantid } = data

  const handleRowClick = (row) => {
    setSelectedRow(row)
    setForm({
      projectid:   row.projectid || '',
      projectnm:   row.projectnm || '',
      projectdesc: row.projectdesc || '',
      useyn:       !!row.useyn,
      creatornm:   row.creatornm || '',
      createdts:   row.createdts || '',
    })
  }

  const handleNew = () => { setSelectedRow(null); setForm(EMPTY_FORM) }

  const handleSave = () => {
    if (!form.projectnm.trim()) { message.warning('프로젝트명을 입력하세요.'); return }
    saveMutation.mutate(
      {
        projectid:   form.projectid || null,
        tenantid:    tenantid?.toString() || null,
        projectnm:   form.projectnm,
        projectdesc: form.projectdesc || null,
        useyn:       form.useyn ?? true,
      },
      {
        onSuccess: () => { message.success('저장되었습니다.'); handleNew() },
        onError: (err) => message.error(err.response?.data?.detail || '저장 실패'),
      },
    )
  }

  const handleDelete = () => {
    if (!form.projectid) { message.warning('삭제할 프로젝트를 선택하세요.'); return }
    Modal.confirm({
      title: '삭제 확인', content: '정말 삭제하시겠습니까?',
      okText: '삭제', cancelText: '취소', okButtonProps: { danger: true },
      onOk: () => deleteMutation.mutate(
        { projectid: form.projectid },
        {
          onSuccess: () => { message.success('삭제되었습니다.'); handleNew() },
          onError: (err) => message.error(err.response?.data?.detail || '삭제 실패'),
        },
      ),
    })
  }

  const pageTitle = tenantnm ? `프로젝트 관리: ${tenantnm}` : '프로젝트 관리'

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{pageTitle}</div>
        </div>
        {roleid === 7 && (
          <button type="button" className="icon-btn" onClick={() => navigate('/settings/tenants')}>
            <img src="/icons/back.svg" alt="뒤로가기" className="icon-img config-icon" />
          </button>
        )}
      </div>

      <div style={{ display: 'flex', gap: 20, minHeight: '80%' }}>
        {/* 왼쪽: 목록 */}
        <div style={{ flex: 1.5 }}>
          <h3>프로젝트 목록</h3>
          <div className="table-container">
            <table className="table table-bordered table-sm" style={{ cursor: 'pointer' }}>
              <thead>
                <tr>
                  <th style={{ width: '30%' }}>프로젝트명</th>
                  <th style={{ width: '30%' }}>설명</th>
                  <th style={{ width: '10%' }}>사용</th>
                  <th style={{ width: '20%' }}>생성일시</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center' }}>로딩 중...</td></tr>
                ) : projects.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center', color: '#888' }}>등록된 프로젝트가 없습니다.</td></tr>
                ) : projects.map((p) => (
                  <tr key={p.projectid}
                    className={selectedRow?.projectid === p.projectid ? 'selected-row' : ''}
                    onClick={() => handleRowClick(p)}
                  >
                    <td>{p.projectnm}</td>
                    <td style={{ whiteSpace: 'pre-wrap' }}>{p.projectdesc || ''}</td>
                    <td style={{ textAlign: 'center' }}>{p.useyn ? '✔' : ''}</td>
                    <td>{p.createdts}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 오른쪽: 상세 */}
        <div style={{ flex: 1.5, paddingLeft: 20 }}>
          <h3>프로젝트 상세</h3>

          <div className="form-group-left">
            <label>프로젝트명:</label>
            <input type="text" value={form.projectnm}
              onChange={(e) => setForm(f => ({ ...f, projectnm: e.target.value }))} />
          </div>

          <div className="form-group-left">
            <label>설명:</label>
            <textarea value={form.projectdesc} rows={4}
              style={{ resize: 'none', height: '80%' }}
              onChange={(e) => setForm(f => ({ ...f, projectdesc: e.target.value }))} />
          </div>

          <div className="form-group-left" style={{ display: 'block' }}>
            <label>사용:</label>
            <input type="checkbox" checked={form.useyn} style={{ marginLeft: 50 }}
              onChange={(e) => setForm(f => ({ ...f, useyn: e.target.checked }))} />
          </div>

          <div className="form-group-left">
            <label>생성자:</label>
            <input type="text" value={form.creatornm} disabled style={roStyle} />
          </div>

          <div className="form-group-left">
            <label>생성일시:</label>
            <input type="text" value={form.createdts} disabled style={roStyle} />
          </div>

          <div className="button-group">
            <button type="button" className="icon-btn" onClick={handleNew}>
              <div className="icon-wrapper">
                <img src="/icons/new.svg" className="icon-img new-icon" alt="신규" />
                <span className="icon-label">신규</span>
              </div>
            </button>
            <button type="button" className="icon-btn" onClick={handleSave} disabled={saveMutation.isPending}>
              <div className="icon-wrapper">
                <img src="/icons/save.svg" className="icon-img save-icon" alt="저장" />
                <span className="icon-label">저장</span>
              </div>
            </button>
            <Popconfirm title="정말 삭제하시겠습니까?" onConfirm={handleDelete}
              okText="삭제" cancelText="취소" okButtonProps={{ danger: true }}
              disabled={!form.projectid}>
              <button type="button" className="icon-btn" disabled={deleteMutation.isPending}>
                <div className="icon-wrapper">
                  <img src="/icons/delete.svg" className="icon-img del-icon" alt="삭제" />
                  <span className="icon-label">삭제</span>
                </div>
              </button>
            </Popconfirm>
          </div>

          {/* 사용자 설정 이동 버튼 */}
          {selectedRow && (
            <div className="button-group" style={{ marginTop: 8 }}>
              <button type="button" className="btn btn-link"
                onClick={() => navigate(`/org/project-users?projects=${encodeURIComponent(form.projectid)}`)}>
                사용자 설정 이동 &#x279C;
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
