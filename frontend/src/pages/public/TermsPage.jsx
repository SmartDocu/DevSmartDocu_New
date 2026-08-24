import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Tabs, Spin } from 'antd'
import { useLangStore } from '@/stores/langStore'

// terms.json의 label/content는 언어별 객체({ko, en, ja})다.
// 아직 번역이 없는 언어는 한국어 원문으로 폴백한다.
const pickLang = (val, languageCd) => val?.[languageCd] ?? val?.ko

const UI_TEXT = {
  pageTitle: { ko: '약관 및 조건', en: 'Terms and Conditions', ja: '約款及び条件' },
  loadError: { ko: '약관 내용을 불러올 수 없습니다.', en: 'Unable to load the terms content.', ja: '約款の内容を読み込めません。' },
}
const pickUiText = (key, languageCd) => UI_TEXT[key][languageCd] ?? UI_TEXT[key].ko

export default function TermsPage() {
  const languageCd = useLangStore((s) => s.languageCd)
  const [searchParams, setSearchParams] = useSearchParams()
  const [terms, setTerms] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/terms/terms.json')
      .then((r) => r.json())
      .then((data) => { setTerms(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
  if (!terms) {
    return (
      <div style={{ padding: 24, color: '#888' }}>
        {pickUiText('loadError', languageCd)}
      </div>
    )
  }

  const items = Object.entries(terms).map(([key, val]) => ({
    key,
    label: pickLang(val.label, languageCd),
    children: (
      <div
        style={{ maxHeight: '70vh', overflowY: 'auto', padding: '8px 4px' }}
        dangerouslySetInnerHTML={{ __html: pickLang(val.content, languageCd) }}
      />
    ),
  }))

  const requestedKey = searchParams.get('terms')
  const activeKey = requestedKey && terms[requestedKey] ? requestedKey : items[0]?.key

  const handleTabChange = (key) => {
    setSearchParams({ terms: key }, { replace: true })
  }

  return (
    <div style={{ padding: '0 8px' }}>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{pickUiText('pageTitle', languageCd)}</div>
        </div>
      </div>
      <Tabs items={items} activeKey={activeKey} onChange={handleTabChange} />
    </div>
  )
}
