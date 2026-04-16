import { useState, useEffect } from 'react'
import { Tabs, Spin } from 'antd'

export default function TermsPage() {
  const [terms, setTerms] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/terms/terms.json')
      .then((r) => r.json())
      .then((data) => { setTerms(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
  if (!terms) return <div style={{ padding: 24, color: '#888' }}>약관 내용을 불러올 수 없습니다.</div>

  const items = Object.entries(terms).map(([key, val]) => ({
    key,
    label: val.label,
    children: (
      <div
        style={{ maxHeight: '70vh', overflowY: 'auto', padding: '8px 4px' }}
        dangerouslySetInnerHTML={{ __html: val.content }}
      />
    ),
  }))

  return (
    <div style={{ padding: '0 8px' }}>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>약관 및 조건</div>
        </div>
      </div>
      <Tabs items={items} />
    </div>
  )
}
