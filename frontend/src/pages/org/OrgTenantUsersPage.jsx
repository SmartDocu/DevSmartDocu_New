import { useState, useMemo } from 'react'
import { App, Modal, Popconfirm } from 'antd'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useOrgTenantUsers, useSaveTenantUser, useDeleteTenantUser } from '@/hooks/useOrg'

const roStyle = { backgroundColor: '#f0f0f0', color: '#555', border: '1px solid #ccc' }

const EMPTY_FORM = {
  sep: '', tenantnewuid: '', useruid: '',
  email: '', usernm: '', rolecd: 'U', useyn: true, creatornm: '', createdts: '',
}

export default function OrgTenantUsersPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { user } = useAuthStore()
  const roleid = user?.roleid

  const paramTenantid = roleid === 7 ? searchParams.get('tenantid') : null

  const { data = {}, isLoading } = useOrgTenantUsers(paramTenantid)
  const saveMutation = useSaveTenantUser()
  const deleteMutation = useDeleteTenantUser()

  const [form, setForm] = useState(EMPTY_FORM)
  const [selectedUid, setSelectedUid] = useState(null)

  const [sepFilter,    setSepFilter]    = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [roleFilter,   setRoleFilter]   = useState('all')

  const { tenantid, tenantnm, users = [] } = data

  const filteredUsers = useMemo(() => {
    return [...users]
      .sort((a, b) => (a.email || '').toLowerCase().localeCompare((b.email || '').toLowerCase()))
      .filter((u) => {
        if (sepFilter !== 'all' && u.sep !== sepFilter) return false
        if (statusFilter === 'active' && !u.useyn) return false
        if (statusFilter === 'inactive' && u.useyn) return false
        if (roleFilter !== 'all' && u.rolecd !== roleFilter) return false
        return true
      })
  }, [users, sepFilter, statusFilter, roleFilter])

  const handleRowClick = (row) => {
    setSelectedUid(row.useruid || row.tenantnewuid)
    setForm({
      sep:         row.sep || '',
      tenantnewuid: row.tenantnewuid || '',
      useruid:     row.useruid || '',
      email:       row.email || '',
      usernm:      row.usernm || '',
      rolecd:      row.rolecd || 'U',
      useyn:       !!row.useyn,
      creatornm:   row.creatornm || '',
      createdts:   row.createdts || '',
    })
  }

  const handleNew = () => { setSelectedUid(null); setForm(EMPTY_FORM) }

  const handleSave = () => {
    if (!form.email.trim()) { message.warning('이메일을 입력하세요.'); return }
    saveMutation.mutate(
      {
        sep: form.sep || null,
        tenantnewuid: form.tenantnewuid || null,
        tenantid: tenantid?.toString(),
        useruid: form.useruid || null,
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
    if (!form.useruid && !form.tenantnewuid) { message.warning('삭제할 사용자를 선택하세요.'); return }

    const doDelete = (approvenote) => {
      deleteMutation.mutate(
        {
          sep: form.sep,
          tenantnewuid: form.tenantnewuid || null,
          tenantid: tenantid?.toString(),
          useruid: form.useruid,
          approvenote: approvenote || null,
        },
        {
          onSuccess: () => { message.success('삭제되었습니다.'); handleNew() },
          onError: (err) => message.error(err.response?.data?.detail || '삭제 실패'),
        },
      )
    }

    if (form.sep === 'newusers') {
      let note = ''
      Modal.confirm({
        title: '가입 거절',
        content: (
          <div>
            <p>가입 거절 사유를 입력해주세요:</p>
            <textarea rows={3} style={{ width: '100%' }}
              onChange={(e) => { note = e.target.value }} />
          </div>
        ),
        okText: '삭제', cancelText: '취소', okButtonProps: { danger: true },
        onOk: () => {
          if (!note.trim()) { Modal.error({ title: '삭제 사유를 입력해야 합니다.' }); return Promise.reject() }
          doDelete(note.trim())
        },
      })
    } else {
      Modal.confirm({
        title: '삭제 확인', content: '정말 삭제하시겠습니까?',
        okText: '삭제', cancelText: '취소', okButtonProps: { danger: true },
        onOk: () => doDelete(null),
      })
    }
  }

  const pageTitle = roleid === 7 && tenantnm
    ? `기업 사용자 관리: ${tenantnm}` : '기업 사용자 관리'

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

      {/* 필터 */}
      <div className="form-filter-group">
        <div className="filter-item">
          <label>신규:</label>
          {[['all','전체'],['newusers','신규']].map(([v,t]) => (
            <span key={v}>
              <input type="radio" id={`sep_${v}`} name="sepFilter" value={v}
                checked={sepFilter === v} onChange={() => setSepFilter(v)} />
              <label className="radio-label" htmlFor={`sep_${v}`}>{t}</label>
            </span>
          ))}
        </div>
        <div className="filter-item">
          <label>상태:</label>
          {[['all','전체'],['active','활성'],['inactive','비활성']].map(([v,t]) => (
            <span key={v}>
              <input type="radio" id={`status_${v}`} name="statusFilter" value={v}
                checked={statusFilter === v} onChange={() => setStatusFilter(v)} />
              <label className="radio-label" htmlFor={`status_${v}`}>{t}</label>
            </span>
          ))}
        </div>
        <div className="filter-item">
          <label>역할:</label>
          {[['all','전체'],['M','Manager'],['U','User']].map(([v,t]) => (
            <span key={v}>
              <input type="radio" id={`role_${v}`} name="roleFilter" value={v}
                checked={roleFilter === v} onChange={() => setRoleFilter(v)} />
              <label className="radio-label" htmlFor={`role_${v}`}>{t}</label>
            </span>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 20, minHeight: '80%' }}>
        {/* 왼쪽: 목록 */}
        <div style={{ flex: 1.5, paddingRight: 20 }}>
          <h3>사용자 목록</h3>
          <div className="table-container">
            <table className="table table-bordered table-sm" style={{ cursor: 'pointer' }}>
              <thead>
                <tr>
                  <th style={{ width: '30%' }}>이메일</th>
                  <th style={{ width: '20%' }}>사용자명</th>
                  <th style={{ width: '10%' }}>역할</th>
                  <th style={{ width: '10%' }}>사용</th>
                  <th style={{ width: '10%' }}>신규</th>
                  <th style={{ width: '20%' }}>생성일시</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center' }}>로딩 중...</td></tr>
                ) : filteredUsers.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', color: '#888' }}>등록된 사용자가 없습니다.</td></tr>
                ) : filteredUsers.map((u) => {
                  const key = u.useruid || u.tenantnewuid
                  return (
                    <tr key={key}
                      className={selectedUid === key ? 'selected-row' : ''}
                      onClick={() => handleRowClick(u)}
                    >
                      <td>{u.email}</td>
                      <td>{u.usernm}</td>
                      <td>{u.rolecd === 'M' ? 'Manager' : 'User'}</td>
                      <td style={{ textAlign: 'center' }}>{u.useyn ? '✔' : ''}</td>
                      <td>{u.sep === 'newusers' ? '신규' : ''}</td>
                      <td>{u.createdts}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* 오른쪽: 상세 */}
        <div style={{ flex: 1.5, paddingLeft: 20 }}>
          <h3>사용자 상세</h3>

          <div className="form-group-left">
            <label>이메일:</label>
            <input type="text" value={form.email}
              onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))} />
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
              disabled={!form.useruid && !form.tenantnewuid}>
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
    </div>
  )
}
