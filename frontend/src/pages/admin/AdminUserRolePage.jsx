import { useState } from 'react'
import { App } from 'antd'
import { useAdminUserRoles, useSaveUserRole } from '@/hooks/useAdmin'

const ROLE_OPTIONS = [
  { value: 1, label: '일반유저' },
  { value: 5, label: 'Power User' },
  { value: 7, label: '관리자' },
]

export default function AdminUserRolePage() {
  const { message } = App.useApp()
  const { data = {}, isLoading } = useAdminUserRoles()
  const saveMutation = useSaveUserRole()

  const [pendingRoles, setPendingRoles] = useState({})
  const [savingUid, setSavingUid] = useState(null)

  const { users = [], role_options = [] } = data
  const roleOptions = role_options.length > 0 ? role_options : ROLE_OPTIONS

  const handleRoleChange = (useruid, newRoleid) => {
    setPendingRoles((prev) => ({ ...prev, [useruid]: parseInt(newRoleid) }))
  }

  const handleSave = (useruid) => {
    const originalUser = users.find((u) => u.useruid === useruid)
    const roleid = pendingRoles[useruid] ?? originalUser?.roleid
    if (!roleid) return
    setSavingUid(useruid)
    saveMutation.mutate(
      { useruid, roleid },
      {
        onSettled: () => {
          setSavingUid(null)
          setPendingRoles((prev) => {
            const next = { ...prev }
            delete next[useruid]
            return next
          })
        },
      },
    )
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>사용자 권한 관리</div>
        </div>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <div className="spinner" />
        </div>
      ) : (
        <div style={{ height: 'calc(100vh - 330px)', overflowY: 'auto' }}>
          <table style={{ width: '50%' }}>
            <thead>
              <tr>
                <th style={{ width: '50%' }}>이메일</th>
                <th style={{ width: '30%' }}>역할</th>
                <th style={{ width: '20%' }} />
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.useruid}>
                  <td>{user.email}</td>
                  <td style={{ textAlign: 'center' }}>
                    <select
                      style={{ width: '90%' }}
                      value={pendingRoles[user.useruid] ?? user.roleid}
                      onChange={(e) => handleRoleChange(user.useruid, e.target.value)}
                    >
                      {roleOptions.map((r) => (
                        <option key={r.value} value={r.value}>{r.label}</option>
                      ))}
                    </select>
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    <button
                      type="button"
                      className="icon-btn"
                      disabled={savingUid === user.useruid}
                      onClick={() => handleSave(user.useruid)}
                    >
                      <img
                        src="/icons/save.svg"
                        title="저장"
                        className="icon-img-tbl save-icon"
                        alt="저장"
                      />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
