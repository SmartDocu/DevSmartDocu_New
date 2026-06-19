import { useState } from 'react'
import { Modal, App } from 'antd'
import { useDocGroups, useSaveDocGroup, useDeleteDocGroup } from '@/hooks/useDocGroups'
import { t } from '@/stores/langStore'

export default function DocGroupSelectModal({ open, onClose, projectid, onSelect }) {
  const { modal, message } = App.useApp()
  const { data: docgroups = [], isLoading } = useDocGroups(projectid)
  const saveDocGroup = useSaveDocGroup()
  const deleteDocGroup = useDeleteDocGroup()

  const [newNm, setNewNm] = useState('')
  const [newDesc, setNewDesc] = useState('')

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

  const handleDelete = (group) => {
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
      title={t('ttl.docgroup.select')}
      width={760}
    >
      <div style={{ marginBottom: 20 }}>
        {isLoading ? (
          <div style={{ padding: '16px 0', color: '#999' }}>{t('msg.loading')}</div>
        ) : docgroups.length === 0 ? (
          <div style={{ padding: '16px 0', color: '#999' }}>{t('msg.no.data')}</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, tableLayout: 'fixed' }}>
            <colgroup>
              <col style={{ width: '22%' }} />
              <col style={{ width: '55%' }} />
              <col style={{ width: '23%' }} />
            </colgroup>
            <thead>
              <tr style={{ background: '#f5f5f5' }}>
                <th style={thStyle}>{t('lbl.docgroupnm')}</th>
                <th style={thStyle}>{t('lbl.desc_lbl')}</th>
                <th style={thStyle}></th>
              </tr>
            </thead>
            <tbody>
              {docgroups.map((g) => (
                <tr key={g.docgroupid} style={{ borderBottom: '1px solid #f0f0f0' }}>
                  <td style={tdStyle}>{g.docgroupnm}</td>
                  <td style={tdStyle}>{g.docgroupdesc || '-'}</td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>
                    <button
                      className="btn btn-primary"
                      type="button"
                      style={{ marginRight: 6, padding: '2px 10px', fontSize: 12 }}
                      onClick={() => handleSelect(g)}
                    >
                      {t('btn.select')}
                    </button>
                    <button
                      className="btn btn-danger"
                      type="button"
                      style={{ padding: '2px 10px', fontSize: 12 }}
                      onClick={() => handleDelete(g)}
                      disabled={deleteDocGroup.isPending}
                    >
                      {t('btn.delete')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 16, display: 'flex', gap: 8, alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}>
          <input
            type="text"
            placeholder={t('lbl.docgroupnm')}
            value={newNm}
            onChange={(e) => setNewNm(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
            style={{ width: '100%', marginBottom: 4 }}
          />
          <input
            type="text"
            placeholder={t('lbl.desc_lbl')}
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
            style={{ width: '100%' }}
          />
        </div>
        <button
          className="btn btn-primary"
          type="button"
          onClick={handleAdd}
          disabled={!newNm.trim() || saveDocGroup.isPending}
          style={{ alignSelf: 'center' }}
        >
          {t('btn.add')}
        </button>
      </div>
    </Modal>
  )
}

const thStyle = {
  padding: '8px 10px',
  textAlign: 'left',
  fontWeight: 600,
  borderBottom: '1px solid #e8e8e8',
}

const tdStyle = {
  padding: '8px 10px',
  verticalAlign: 'middle',
}
