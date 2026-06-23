import { useState } from 'react'
import { Modal, App, Input, Button, Space, Tooltip } from 'antd'
import { DeleteOutlined, FolderOutlined } from '@ant-design/icons'
import { useDocGroups, useSaveDocGroup, useDeleteDocGroup } from '@/hooks/useDocGroups'
import { t } from '@/stores/langStore'

export default function DocGroupSelectModal({ open, onClose, projectid, onSelect }) {
  const { modal, message } = App.useApp()
  const { data: docgroups = [], isLoading } = useDocGroups(projectid)
  const saveDocGroup = useSaveDocGroup()
  const deleteDocGroup = useDeleteDocGroup()

  const [newNm, setNewNm] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [hoveredId, setHoveredId] = useState(null)

  const handleAdd = () => {
    if (!newNm.trim()) return
    saveDocGroup.mutate(
      { docgroupnm: newNm.trim(), docgroupdesc: newDesc.trim() || null, projectid },
      {
        onSuccess: () => {
          setNewNm('')
          setNewDesc('')
        },
      }
    )
  }

  const handleDelete = (e, group) => {
    e.stopPropagation()
    modal.confirm({
      content: t('msg.confirm.delete'),
      okType: 'danger',
      onOk: () =>
        deleteDocGroup.mutate(
          { docgroupid: group.docgroupid, projectid },
          { onError: (err) => message.error(t(err.response?.data?.detail) || t('msg.delete.error')) }
        ),
    })
  }

  const handleSelect = (group) => {
    onSelect(group.docgroupid, group.docgroupnm)
    onClose()
  }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      title={
        <Space>
          <FolderOutlined style={{ color: '#1677ff' }} />
          {t('ttl.docgroup.select')}
        </Space>
      }
      width={560}
    >
      {/* 그룹 목록 */}
      <div style={{ minHeight: 120, maxHeight: 340, overflowY: 'auto', marginBottom: 16 }}>
        {isLoading ? (
          <div style={{ padding: '32px 0', textAlign: 'center', color: '#bbb' }}>{t('msg.loading')}</div>
        ) : docgroups.length === 0 ? (
          <div style={{ padding: '32px 0', textAlign: 'center', color: '#bbb' }}>{t('msg.no.data')}</div>
        ) : (
          docgroups.map((g) => (
            <div
              key={g.docgroupid}
              onClick={() => handleSelect(g)}
              onMouseEnter={() => setHoveredId(g.docgroupid)}
              onMouseLeave={() => setHoveredId(null)}
              style={{
                display: 'flex',
                alignItems: 'center',
                padding: '10px 14px',
                borderRadius: 8,
                marginBottom: 4,
                cursor: 'pointer',
                background: hoveredId === g.docgroupid ? '#e6f4ff' : '#fafafa',
                border: `1px solid ${hoveredId === g.docgroupid ? '#91caff' : '#f0f0f0'}`,
                transition: 'all 0.15s',
              }}
            >
              <FolderOutlined style={{ color: '#1677ff', marginRight: 10, fontSize: 15, flexShrink: 0 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 13, color: '#222', lineHeight: 1.4 }}>{g.docgroupnm}</div>
                {g.docgroupdesc && (
                  <div style={{ fontSize: 12, color: '#999', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {g.docgroupdesc}
                  </div>
                )}
              </div>
              <Tooltip title={t('btn.delete')}>
                <Button
                  type="text"
                  icon={<DeleteOutlined />}
                  danger
                  size="small"
                  onClick={(e) => handleDelete(e, g)}
                  disabled={deleteDocGroup.isPending}
                  style={{ flexShrink: 0, opacity: hoveredId === g.docgroupid ? 1 : 0, transition: 'opacity 0.15s' }}
                />
              </Tooltip>
            </div>
          ))
        )}
      </div>

      {/* 새 그룹 추가 */}
      <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 14, display: 'flex', gap: 8, alignItems: 'center' }}>
        <Input
          placeholder={t('lbl.docgroupnm')}
          value={newNm}
          onChange={(e) => setNewNm(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
          style={{ flex: 2 }}
        />
        <Input
          placeholder={t('lbl.desc_lbl')}
          value={newDesc}
          onChange={(e) => setNewDesc(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
          style={{ flex: 3 }}
        />
        <Button
          type="primary"
          onClick={handleAdd}
          disabled={!newNm.trim() || saveDocGroup.isPending}
        >
          {t('btn.add')}
        </Button>
      </div>
    </Modal>
  )
}
