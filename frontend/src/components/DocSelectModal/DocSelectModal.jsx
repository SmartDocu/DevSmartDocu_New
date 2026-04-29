import { useEffect, useState } from 'react'
import { App, Modal, Tabs, Spin, Divider } from 'antd'
import { useNavigate } from 'react-router-dom'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useTabStore } from '@/stores/tabStore'
import { useLangStore, t } from '@/stores/langStore'

export default function DocSelectModal({ open, onClose }) {
  const navigate = useNavigate()
  const { message, modal } = App.useApp()
  const { updateUser, user } = useAuthStore()
  const { clearTabs } = useTabStore()
  useLangStore((s) => s.translations)

  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [activeTab, setActiveTab] = useState('doc')
  const [selectedDoc, setSelectedDoc] = useState(null)
  const [hoveredDocId, setHoveredDocId] = useState(null)

  // 모달 열릴 때 문서 목록 로드
  useEffect(() => {
    if (!open) return
    setLoading(true)
    setDocs([])
    setSelectedDoc(null)
    setActiveTab('doc')

    apiClient
      .get('/docs')
      .then((r) => {
        const list = r.data.docs || []
        console.log('[DocSelectModal] 문서 목록:', list.length, '건')
        setDocs(list)
      })
      .catch((err) => {
        const status = err.response?.status
        const detail = err.response?.data?.detail || err.message
        console.error('[DocSelectModal] GET /docs 오류:', status, detail)
        message.error(`${t('msg.load.error')} (${status ?? 'network'}): ${detail}`)
      })
      .finally(() => setLoading(false))
  }, [open])

  const filtered = docs.filter((d) =>
    activeTab === 'doc' ? !d.sampleyn : !!d.sampleyn,
  )

  const handleSelect = (doc) => setSelectedDoc(doc)

  // Django docs_save에 해당: /docs/select 호출 후 authStore 갱신
  const handleOk = async () => {
    if (!selectedDoc) {
      message.warning(t('msg.docselect.required'))
      return
    }

    setSaving(true)
    try {
      const res = await apiClient.post('/docs/select', {
        docid: selectedDoc.docid,
        docnm: selectedDoc.docnm,
      })
      const data = res.data

      // Django docs_save와 동일하게 사용자 컨텍스트 전체 업데이트
      updateUser({
        docid: data.docid,
        docnm: data.docnm,
        projectid: data.projectid,
        tenantid: data.tenantid,
        tenantmanager: data.tenantmanager,
        projectmanager: data.projectmanager,
        editbuttonyn: data.editbuttonyn,
        sampledocyn: data.sampledocyn,
      })

      onClose()

      modal.confirm({
        title: t('ttl.docselect.change'),
        content: t('msg.docselect.tabs.close'),
        okText: t('btn.ok'),
        cancelText: t('btn.cancel'),
        onOk: () => {
          clearTabs()
          navigate('/')
        },
      })
    } catch (err) {
      const status = err.response?.status
      const detail = err.response?.data?.detail || err.message
      console.error('[DocSelectModal] POST /docs/select 오류:', status, detail)
      message.error(`${t('msg.docselect.error')} (${status ?? 'network'}): ${detail}`)
    } finally {
      setSaving(false)
    }
  }

  const tabItems = [
    { key: 'doc', label: t('lbl.doc') },
    { key: 'sample', label: t('lbl.sample') },
  ]

  const modalFooter = (
    <div style={{ display: 'flex', justifyContent: 'center', gap: 20, paddingTop: 8 }}>
      <button type="button" className="icon-btn" onClick={handleOk} disabled={saving}>
        <div className="icon-wrapper">
          <img src="/icons/ok.svg" className="icon-img config-icon" alt={t('btn.ok')} />
          <span className="icon-label">{t('btn.ok')}</span>
        </div>
      </button>
    </div>
  )

  return (
    <Modal
      title={t('ttl.docselect')}
      open={open}
      onCancel={onClose}
      footer={modalFooter}
      width={520}
      styles={{ body: { maxHeight: '60vh', overflowY: 'auto', padding: '8px 0' } }}
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
        centered
        size="small"
        style={{ marginBottom: 8 }}
      />

      {loading ? (
        <div style={{ textAlign: 'center', padding: 24 }}>
          <Spin />
          <div style={{ marginTop: 8, color: '#888' }}>{t('msg.doc.loading')}</div>
        </div>
      ) : filtered.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 24, color: '#888' }}>
          {activeTab === 'doc' ? t('msg.doc.empty') : t('msg.sample.empty')}
        </div>
      ) : (
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {filtered.map((doc) => {
            const isCurrent = user?.docid != null && String(user.docid) === String(doc.docid)
            const isSelected = selectedDoc?.docid === doc.docid
            const isHovered = hoveredDocId === doc.docid
            const currentBorder = '#A7BFD5'
            const hoverBg = '#C2D9EC'
            const normalBg = '#fafafa'
            const bg = isSelected
              ? '#e6f4ff'
              : isCurrent
              ? (isHovered ? normalBg : hoverBg)
              : (isHovered ? hoverBg : normalBg)
            const borderColor = isSelected
              ? '#1677ff'
              : isCurrent
              ? (isHovered ? '#ddd' : currentBorder)
              : (isHovered ? currentBorder : '#ddd')
            return (
            <li
              key={doc.docid}
              onClick={() => handleSelect(doc)}
              onMouseEnter={() => setHoveredDocId(doc.docid)}
              onMouseLeave={() => setHoveredDocId(null)}
              style={{
                padding: '10px 12px',
                border: `1px solid ${borderColor}`,
                borderRadius: 8,
                marginBottom: 8,
                cursor: 'pointer',
                background: bg,
                fontWeight: isSelected ? 700 : 400,
                transition: 'background 0.15s, border-color 0.15s',
              }}
            >
              <div style={{ fontSize: 15, fontWeight: 600 }}>{doc.docnm}</div>
              {(doc.projectnm || doc.tenantnm) && (
                <div style={{ fontSize: 13, marginTop: 4, color: '#555' }}>
                  {t('lbl.project')} : {doc.projectnm || ''}
                  {doc.tenantnm ? ` (${doc.tenantnm})` : ''}
                </div>
              )}
              {doc.docdesc && (
                <div style={{ fontSize: 12, marginTop: 4, color: '#888', whiteSpace: 'pre-wrap' }}>
                  {doc.docdesc}
                </div>
              )}
            </li>
            )
          })}
        </ul>
      )}
    </Modal>
  )
}
