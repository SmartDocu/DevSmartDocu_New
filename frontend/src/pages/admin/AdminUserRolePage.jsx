import { useEffect, useState } from 'react'
import { Pagination } from 'antd'
import { SaveOutlined } from '@ant-design/icons'
import { useLangStore, t } from '@/stores/langStore'
import { useAdminUserRoles, useSaveUserRole } from '@/hooks/useAdmin'

const PAGE_SIZE = 10

export default function AdminUserRolePage() {
  const { data = {}, isLoading, refetch } = useAdminUserRoles()
  const saveMutation = useSaveUserRole()

  useLangStore((s) => s.translations)

  const [pendingRoles, setPendingRoles] = useState({})
  const [savingUid, setSavingUid] = useState(null)
  const [emailFilter, setEmailFilter] = useState('')
  const [page, setPage] = useState(1)

  const { users = [], role_options: roleOptions = [] } = data

  const filteredUsers = users.filter((u) =>
    (u.email || '').toLowerCase().includes(emailFilter.trim().toLowerCase())
  )
  const pagedUsers = filteredUsers.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  useEffect(() => { setPage(1) }, [emailFilter])

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
          // ✅ 1. 데이터 갱신 (성공 안내는 useSaveUserRole 훅에서 표시)
          await refetch()

          // ✅ 2. pending 정리
          setPendingRoles((prev) => {
            const next = { ...prev }
            delete next[useruid]
            return next
          })
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
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('mnu.system.users')}</div>
        </div>
      </div>

      <div className="panel-section" style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
        <div className="filter-item">
          <label style={{ fontWeight: 'bold' }}>{t('lbl.email')}</label>
          <input
            type="text"
            value={emailFilter}
            placeholder={t('msg.search.email.placeholder')}
            style={{ height: 32, width: 240 }}
            onChange={(e) => setEmailFilter(e.target.value)}
          />
        </div>
      </div>

      <div className="panel-section" style={{ height: 'calc(100vh - 306px)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', height: 60, flexShrink: 0,
          margin: '-16px -18px 16px', padding: '16px 18px 12px',
          borderBottom: '1px solid var(--border-color, #e3e6eb)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <h3 style={{ margin: 0, lineHeight: 1 }}>{t('ttl.list')}</h3>
            <span style={{
              display: 'inline-flex', alignItems: 'center', lineHeight: 1,
              font: '500 11px monospace', color: '#8d9199', background: '#f2efe9',
              borderRadius: 6, padding: '5px 8px 4px',
            }}>
              {t('lbl.count.docs').replace('{n}', filteredUsers.length)}
            </span>
          </div>
          <div />
        </div>

        {isLoading ? (
          <div style={{ textAlign: 'center', padding: 48 }}>
            <div className="spinner" />
          </div>
        ) : (
          <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
            <table className="table table-bordered table-sm" style={{ tableLayout: 'fixed', maxWidth: 640 }}>
              <thead>
                <tr>
                  <th style={{ width: '50%' }}>{t('thd.email_thd')}</th>
                  <th style={{ width: '30%' }}>{t('thd.rolecd_thd')}</th>
                  <th style={{ width: '20%' }} />
                </tr>
              </thead>
              <tbody>
                {filteredUsers.length === 0 ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : pagedUsers.map((user) => (
                  <tr key={user.useruid}>
                    <td>{user.email}</td>
                    <td style={{ textAlign: 'center' }}>
                      <select
                        style={{ width: '90%', height: 38 }}
                        value={pendingRoles[user.useruid] ?? user.roleid}
                        onChange={(e) => handleRoleChange(user.useruid, e.target.value)}
                      >
                        {roleOptions.map((r) => (
                          <option key={r.value} value={r.value}>{t(r.term_key) || r.default_name}</option>
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
                        <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {filteredUsers.length > PAGE_SIZE && (
          <div style={{ marginTop: 'auto', paddingTop: 12, display: 'flex', justifyContent: 'center' }}>
            <Pagination
              current={page}
              pageSize={PAGE_SIZE}
              total={filteredUsers.length}
              showSizeChanger={false}
              onChange={setPage}
            />
          </div>
        )}
      </div>
    </div>
  )
}
