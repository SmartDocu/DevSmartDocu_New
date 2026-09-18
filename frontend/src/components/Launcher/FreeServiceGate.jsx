import { useState } from 'react'
import { CheckCircleFilled } from '@ant-design/icons'
import { t } from '@/stores/langStore'
import { useSelectFreeServices } from '@/hooks/useApps'

const SERVICES = [
  { servicecd: 'Do', titleKey: 'lbl.freeservice.do_title', descKey: 'inf.freeservice.do_desc' },
  { servicecd: 'Ch', titleKey: 'lbl.freeservice.ch_title', descKey: 'inf.freeservice.ch_desc' },
  { servicecd: 'In', titleKey: 'lbl.freeservice.in_title', descKey: 'inf.freeservice.in_desc' },
]

export default function FreeServiceGate() {
  const [selected, setSelected] = useState([])
  const selectMutation = useSelectFreeServices()

  const toggle = (servicecd) => {
    setSelected((prev) => prev.includes(servicecd) ? prev.filter((s) => s !== servicecd) : [...prev, servicecd])
  }

  const handleSubmit = () => {
    if (selected.length === 0) return
    selectMutation.mutate(selected)
  }

  return (
    <div style={{ maxWidth: 780, margin: '0 auto', padding: '20px 0' }}>
      <h2 style={{ textAlign: 'center', marginBottom: 8, color: '#163E64', fontSize: 22, fontWeight: 700 }}>
        {t('ttl.freeservice.heading')}
      </h2>
      <p style={{ textAlign: 'center', color: '#888', fontSize: 13, marginBottom: 32, whiteSpace: 'pre-line' }}>
        {t('inf.freeservice.subheading')}
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 28 }}>
        {SERVICES.map(({ servicecd, titleKey, descKey }) => {
          const isSelected = selected.includes(servicecd)
          return (
            <div
              key={servicecd}
              onClick={() => toggle(servicecd)}
              style={{
                position: 'relative',
                background: '#fff',
                borderRadius: 12,
                padding: '24px 16px 20px',
                textAlign: 'left',
                cursor: 'pointer',
                border: `2px solid ${isSelected ? '#163E64' : '#e3e6eb'}`,
                boxShadow: isSelected ? '0 4px 14px rgba(22,62,100,0.12)' : '0 2px 6px rgba(0,0,0,0.05)',
                transition: 'all 0.15s',
              }}
            >
              <div
                style={{
                  position: 'absolute', top: 12, right: 12,
                  width: 20, height: 20, borderRadius: '50%',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  border: isSelected ? 'none' : '1.5px solid #d9d9d9',
                  color: isSelected ? '#163E64' : 'transparent',
                  fontSize: 20, lineHeight: 1,
                }}
              >
                {isSelected && <CheckCircleFilled />}
              </div>
              <div style={{ fontSize: 16, fontWeight: 700, color: '#163E64', marginBottom: 6 }}>
                {t(titleKey)}
              </div>
              <div style={{ fontSize: 13, color: '#666', marginBottom: 14, minHeight: 36 }}>
                {t(descKey)}
              </div>
              <span
                style={{
                  display: 'inline-block', fontSize: 11, fontWeight: 600,
                  color: '#163E64', background: '#eef2f7', borderRadius: 20,
                  padding: '3px 10px',
                }}
              >
                {t('lbl.freeservice.badge')}
              </span>
            </div>
          )
        })}
      </div>

      <button
        type="button"
        onClick={handleSubmit}
        disabled={selected.length === 0 || selectMutation.isPending}
        style={{
          display: 'block', width: '100%', height: 46, borderRadius: 8, border: 'none',
          background: selected.length === 0 ? '#bbb' : '#163E64',
          color: '#fff', fontSize: 15, fontWeight: 600,
          cursor: selected.length === 0 ? 'not-allowed' : 'pointer',
        }}
      >
        {t('btn.freeservice.start')}
      </button>

      <p style={{ textAlign: 'center', color: '#888', fontSize: 13, marginTop: 16, marginBottom: 0 }}>
        {t('inf.freeservice.tenant_notice')}
      </p>
    </div>
  )
}
