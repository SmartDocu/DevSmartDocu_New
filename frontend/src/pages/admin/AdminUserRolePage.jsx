import { useState } from 'react'
import { App } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useAdminUserRoles, useSaveUserRole } from '@/hooks/useAdmin'

const ROLE_OPTIONS = [
  { value: 1, label: '일반유저' },
  { value: 5, label: 'Power User' },
  { value: 7, label: '관리자' },
]

export default function AdminUserRolePage() {
  const { message } = App.useApp()
  const { data = {}, isLoading, refetch } = useAdminUserRoles()
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
        onSuccess: async () => {
          // ✅ 1. 메시지 먼저 (샘플 방식)
          message.success(t('msg.save.success'))

          // ✅ 2. 데이터 갱신
          await refetch()

          // ✅ 3. pending 정리
          setPendingRoles((prev) => {
            const next = { ...prev }
            delete next[useruid]
            return next
          })
        },
        onError: (err) => {
          message.error(
            err?.response?.data?.detail || t('msg.save.error')
          )
        },
        onSettled: () => {
          setSavingUid(null)
        }
      }
    )
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('mnu.system.users')}</div>
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
                <th style={{ width: '50%' }}>{t('thd.email_thd')}</th>
                <th style={{ width: '30%' }}>{t('thd.rolecd_thd')}</th>
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
                      className="btn btn-primary"
                      disabled={savingUid === user.useruid}
                      onClick={() => handleSave(user.useruid)}
                    >
                      {t('btn.save')}
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
