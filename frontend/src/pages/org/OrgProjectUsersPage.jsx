import { useState, useEffect } from 'react'
import { App, Modal, Popconfirm } from 'antd'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import {
  useOrgProjectUsers,
  useSaveProjectUser,
  useDeleteProjectUser,
} from '@/hooks/useOrg'

const roStyle = { backgroundColor: '#f0f0f0', color: '#555', border: '1px solid #ccc' }

const EMPTY_FORM = {
  useruid: '', email: '', usernm: '', rolecd: 'U',
  useyn: true, creatornm: '', createdts: '',
}

export default function OrgProjectUsersPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { user } = useAuthStore()
  const roleid = user?.roleid
  const tenantmanager = user?.tenantmanager

  const paramProjectid = searchParams.get('projects') || ''
  const [selectedProjectid, setSelectedProjectid] = useState(paramProjectid)

  const { data = {}, isLoading } = useOrgProjectUsers(selectedProjectid)
  const saveMutation = useSaveProjectUser()
  const deleteMutation = useDeleteProjectUser()

  const [form, setForm] = useState(EMPTY_FORM)
  const [selectedUid, setSelectedUid] = useState(null)
  const [userModalOpen, setUserModalOpen] = useState(false)

  const { projects = [], projectusers = [], tenantusers = [] } = data

  useEffect(() => {
    if (paramProjectid) setSelectedProjectid(paramProjectid)
  }, [paramProjectid])

  const handleProjectChange = (e) => {
    const value = e.target.value
    setSelectedProjectid(value)
    setSearchParams(value ? { projects: value } : {})
    setSelectedUid(null)
    setForm(EMPTY_FORM)
  }

  const handleRowClick = (row) => {
    setSelectedUid(row.useruid)
    setForm({
      useruid:   row.useruid || '',
      email:     row.email || '',
      usernm:    row.usernm || '',
      rolecd:    row.rolecd || 'U',
      useyn:     !!row.useyn,
      creatornm: row.creatornm || '',
      createdts: row.createdts || '',
    })
  }

  const handleNew = () => { setSelectedUid(null); setForm(EMPTY_FORM) }

  const handleSave = () => {
    if (!selectedProjectid) { message.warning('프로젝트를 선택하세요.'); return }
    if (!form.email.trim()) { message.warning('이메일을 입력하세요.'); return }
    saveMutation.mutate(
      {
        projectid: selectedProjectid,
        email: form.email,
        rolecd: form.rolecd || 'U',
        useyn: form.useyn ?? true,
      },
      {
        onSuccess: () => { message.success('저장되었습니다.'); handleNew() },
        onError: (err) => message.error(err.response?.data?.detail || '저장 실패'),
      },
    )
  }

  const handleDelete = () => {
    if (!form.useruid) { message.warning('삭제할 사용자를 선택하세요.'); return }
    Modal.confirm({
      title: '삭제 확인', content: '정말 삭제하시겠습니까?',
      okText: '삭제', cancelText: '취소', okButtonProps: { danger: true },
      onOk: () => deleteMutation.mutate(
        { projectid: selectedProjectid, useruid: form.useruid },
        {
          onSuccess: () => { message.success('삭제되었습니다.'); handleNew() },
          onError: (err) => message.error(err.response?.data?.detail || '삭제 실패'),
        },
      ),
    })
  }

  const handleModalUserSelect = (u) => {
    setForm(f => ({ ...f, email: u.email, usernm: u.usernm }))
    setUserModalOpen(false)
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>프로젝트 사용자 관리</div>
        </div>
        {(roleid === 7 || tenantmanager === 'Y') && (
          <button type="button" className="icon-btn" onClick={() => navigate('/org/projects')}>
            <img src="/icons/back.svg" alt="뒤로가기" className="icon-img config-icon" />
          </button>
        )}
      </div>

      {/* 프로젝트 선택 필터 */}
      <div className="form-filter-group">
        <div className="filter-item">
          <label htmlFor="projects" style={{ width: 100 }}>프로젝트 목록:</label>
          <select name="projects" id="projects" value={selectedProjectid} onChange={handleProjectChange}>
            <option value="">-- 프로젝트 선택 --</option>
            {projects.map((p) => (
              <option key={p.projectid} value={p.projectid}>{p.projectnm}</option>
            ))}
          </select>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 20, minHeight: '80%' }}>
        {/* 왼쪽: 목록 */}
        <div style={{ flex: 1.5 }}>
          <h3>사용자 목록</h3>
          <div className="table-container">
            <table className="table table-bordered table-sm" style={{ cursor: 'pointer' }}>
              <thead>
                <tr>
                  <th style={{ width: '30%' }}>이메일</th>
                  <th style={{ width: '20%' }}>사용자명</th>
                  <th style={{ width: '10%' }}>역할</th>
                  <th style={{ width: '10%' }}>사용</th>
                  <th style={{ width: '20%' }}>생성일시</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={5} style={{ textAlign: 'center' }}>로딩 중...</td></tr>
                ) : projectusers.length === 0 ? (
                  <tr><td colSpan={5} style={{ textAlign: 'center', color: '#888' }}>등록된 사용자가 없습니다.</td></tr>
                ) : projectusers.map((u) => (
                  <tr key={u.useruid}
                    className={selectedUid === u.useruid ? 'selected-row' : ''}
                    onClick={() => handleRowClick(u)}
                  >
                    <td>{u.email}</td>
                    <td>{u.usernm}</td>
                    <td>{u.rolecd === 'M' ? 'Manager' : 'User'}</td>
                    <td style={{ textAlign: 'center' }}>{u.useyn ? '✔' : ''}</td>
                    <td>{u.createdts}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 오른쪽: 상세 */}
        <div style={{ flex: 1.5, paddingLeft: 20 }}>
          <h3>사용자 상세</h3>

          <div className="form-group-left">
            <label>이메일:</label>
            <input type="text" value={form.email} placeholder="직접 입력 또는 조회"
              onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))} />
            <button type="button" className="icon-btn" style={{ marginLeft: 5 }}
              onClick={() => setUserModalOpen(true)}>
              조회
            </button>
          </div>

          <div className="form-group-left">
            <label>사용자명:</label>
            <input type="text" value={form.usernm} disabled style={roStyle} />
          </div>

          <div className="form-group-left">
            <label>역할:</label>
            <label>
              <input type="radio" name="rolecd" value="M"
                checked={form.rolecd === 'M'}
                onChange={() => setForm(f => ({ ...f, rolecd: 'M' }))} />
              {' '}Manager
            </label>
            <label style={{ marginLeft: 10 }}>
              <input type="radio" name="rolecd" value="U"
                checked={form.rolecd === 'U'}
                onChange={() => setForm(f => ({ ...f, rolecd: 'U' }))} />
              {' '}User
            </label>
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
              disabled={!form.useruid}>
              <button type="button" className="icon-btn" disabled={deleteMutation.isPending}>
                <div className="icon-wrapper">
                  <img src="/icons/delete.svg" className="icon-img del-icon" alt="삭제" />
                  <span className="icon-label">삭제</span>
                </div>
              </button>
            </Popconfirm>
          </div>
        </div>
      </div>

      {/* 사용자 선택 Modal */}
      <div id="user-modal" style={{
        display: userModalOpen ? 'flex' : 'none',
        position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
        background: 'rgba(0,0,0,0.5)', justifyContent: 'center', alignItems: 'center', zIndex: 1050,
      }}>
        <div style={{
          background: '#fff', padding: 20, width: 500, maxHeight: '80%', overflow: 'auto',
          borderRadius: 8, position: 'relative', zIndex: 1060,
        }}>
          <h4>사용자 선택</h4>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f0f0f0' }}>
                <th style={{ padding: 8, border: '1px solid #ccc' }}>이름</th>
                <th style={{ padding: 8, border: '1px solid #ccc' }}>이메일</th>
              </tr>
            </thead>
            <tbody>
              {tenantusers.map((u) => (
                <tr key={u.useruid} style={{ cursor: 'pointer' }}
                  onClick={() => handleModalUserSelect(u)}>
                  <td style={{ padding: 6, border: '1px solid #ccc' }}>{u.usernm}</td>
                  <td style={{ padding: 6, border: '1px solid #ccc' }}>{u.email}</td>
                </tr>
              ))}
              {tenantusers.length === 0 && (
                <tr><td colSpan={2} style={{ textAlign: 'center', padding: 8 }}>추가 가능한 사용자가 없습니다.</td></tr>
              )}
            </tbody>
          </table>
          <div style={{ textAlign: 'right', marginTop: 10 }}>
            <button type="button" onClick={() => setUserModalOpen(false)}>닫기</button>
          </div>
        </div>
      </div>
    </div>
  )
}
