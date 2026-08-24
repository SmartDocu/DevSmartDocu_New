import { useState } from 'react'
import { App, Select, Pagination, Spin, Input } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useOpenInTab } from '@/hooks/useOpenInTab'
import {
  useNotificationsList, useMarkNotificationRead, useMarkAllNotificationsRead,
  useDeleteNotification, navigateToNotificationTarget, translateNotification,
} from '@/hooks/useNotifications'

const { Search } = Input

const PAGE_SIZE = 20

export default function NotificationsPage() {
  useLangStore((s) => s.translations)
  const { message } = App.useApp()
  const openInTab = useOpenInTab()

  const CATEGORY_OPTIONS = [
    { value: '', label: t('cod.filter_all') },
    { value: 'doc', label: t('cod.notificationcategory_doc') },
    { value: 'chapter', label: t('cod.notificationcategory_chapter') },
    { value: 'payment', label: t('cod.notificationcategory_payment') },
  ]

  const NOTIFICATION_STATUS_OPTIONS = [
    { value: '', label: t('cod.filter_all') },
    { value: 'info', label: t('cod.notificationstatus_info') },
    { value: 'error', label: t('cod.notificationstatus_error') },
  ]

  const READ_STATUS_OPTIONS = [
    { value: '', label: t('cod.filter_all') },
    { value: 'unread', label: t('lbl.notification.unread') },
    { value: 'read', label: t('lbl.notification.read') },
  ]

  const [category, setCategory] = useState('')
  const [notificationStatus, setNotificationStatus] = useState('')
  const [readStatus, setReadStatus] = useState('unread')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [expandedUid, setExpandedUid] = useState(null)

  const { data, isLoading } = useNotificationsList({ category, notificationStatus, readStatus, search, page, pageSize: PAGE_SIZE })
  const notifications = data?.notifications || []
  const totalCount = data?.total_count || 0

  const markRead = useMarkNotificationRead()
  const markAllRead = useMarkAllNotificationsRead()
  const deleteNotification = useDeleteNotification()

  const handleTitleClick = (n) => {
    if (!n.is_read) markRead.mutate(n.notificationuid)
    setExpandedUid((prev) => (prev === n.notificationuid ? null : n.notificationuid))
  }

  const handleMove = (e, n) => {
    e.stopPropagation()
    navigateToNotificationTarget(n, openInTab)
  }

  const handleDelete = (e, n) => {
    e.stopPropagation()
    deleteNotification.mutate(n.notificationuid)
  }

  const handleMarkAllRead = () => {
    markAllRead.mutate(undefined, {
      onSuccess: () => { message.success(t('msg.notification.markall.success')) },
    })
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.notifications')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 12 }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <Select
            value={category}
            onChange={(v) => { setCategory(v); setPage(1) }}
            options={CATEGORY_OPTIONS}
            style={{ width: 160 }}
          />
          <Select
            value={notificationStatus}
            onChange={(v) => { setNotificationStatus(v); setPage(1) }}
            options={NOTIFICATION_STATUS_OPTIONS}
            style={{ width: 140 }}
          />
          <Select
            value={readStatus}
            onChange={(v) => { setReadStatus(v); setPage(1) }}
            options={READ_STATUS_OPTIONS}
            style={{ width: 140 }}
          />
          <Search
            placeholder={t('msg.ph.search')}
            allowClear
            onSearch={(v) => { setSearch(v); setPage(1) }}
            style={{ width: 360 }}
          />
        </div>
        <button className="btn btn-primary" type="button" onClick={handleMarkAllRead}>
          {t('btn.notification.markall')}
        </button>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
      ) : (
        <div className="table-container" style={{ height: 'auto' }}>
          <table className="table table-bordered table-sm">
            <thead>
              <tr>
                <th style={{ width: 160 }}>{t('thd.notification.title')}</th>
                <th style={{ maxWidth: 220 }}>{t('thd.notification.message')}</th>
                <th style={{ width: 100 }}>{t('thd.notification.category')}</th>
                <th style={{ width: 140 }}>{t('thd.createdts')}</th>
              </tr>
            </thead>
            <tbody>
              {notifications.length === 0 ? (
                <tr><td colSpan={4} style={{ textAlign: 'center', color: '#aaa' }}>{t('msg.notification.empty')}</td></tr>
              ) : notifications.map((n) => {
                const { title, message } = translateNotification(n)
                return (
                <tr
                  key={n.notificationuid}
                  style={{
                    background: n.notificationstatus === 'error' ? (n.is_read ? '#fdecea' : '#f8c9c4') : (n.is_read ? '#fafafa' : '#cfe3ff'),
                    borderLeft: n.notificationstatus === 'error' ? '4px solid #dc3545' : '4px solid transparent',
                    fontWeight: n.is_read ? 400 : 700,
                  }}
                >
                  <td
                    onClick={() => handleTitleClick(n)}
                    style={{ color: n.notificationstatus === 'error' ? '#a8202f' : 'inherit', cursor: 'pointer' }}
                  >{title}</td>
                  <td
                    onClick={() => handleTitleClick(n)}
                    style={{ fontWeight: 400, color: '#666', maxWidth: 220, cursor: 'pointer' }}
                  >
                    <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{message}</div>
                    {expandedUid === n.notificationuid && (
                      <div style={{ marginTop: 8 }}>
                        {n.target_url && (
                          <button className="btn btn-primary" type="button" onClick={(e) => handleMove(e, n)} style={{ marginRight: 6 }}>
                            {t('btn.notification.move')}
                          </button>
                        )}
                        <button className="btn btn-danger" type="button" onClick={(e) => handleDelete(e, n)}>
                          {t('btn.delete')}
                        </button>
                      </div>
                    )}
                  </td>
                  <td>{t(`cod.notificationcategory_${n.notificationcategory}`)}</td>
                  <td>{n.createdts}</td>
                </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {totalCount > PAGE_SIZE && (
        <div style={{ display: 'flex', justifyContent: 'center', marginTop: 16 }}>
          <Pagination current={page} pageSize={PAGE_SIZE} total={totalCount} onChange={setPage} showSizeChanger={false} />
        </div>
      )}
    </div>
  )
}
