import { useState, useMemo } from 'react'
import { Input } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useAdminUiTerms } from '@/hooks/useUiTerms'

function getSourceTable(termGroup) {
  if (!termGroup) return '-'
  const prefix = termGroup.split('.')[0]
  switch (prefix) {
    case 'term': return 'UI Register'
    case 'code': return 'Codes Register'
    case 'msg': return 'Message Register'
    case 'menu': return 'Menu Registration'
    case 'prm':
    case 'faq': return 'Sample Prompt'
    default: return '-'
  }
}

export default function AdminUiTermsPage() {
  useLangStore((s) => s.translations)

  const { data: items = [] } = useAdminUiTerms()

  const [searchText, setSearchText] = useState('')
  const [selectedItem, setSelectedItem] = useState(null)

  const filtered = useMemo(() => {
    const q = searchText.trim().toLowerCase()
    if (!q) return items
    return items.filter(
      (item) =>
        (item.term_key || '').toLowerCase().includes(q) ||
        (item.term_group || '').toLowerCase().includes(q) ||
        (item.default_text || '').toLowerCase().includes(q) ||
        item.translations.some((tr) => (tr.translated_text || '').toLowerCase().includes(q))
    )
  }, [items, searchText])

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('mnu.system.translation')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 20, paddingRight: 10 }}>

        {/* 좌측: 목록 */}
        <div style={{ flex: 3, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <div />
          </div>
          <Input
            placeholder={`${t('thd.termkey_thd')} / ${t('thd.termgroupcd_thd')} / ${t('thd.default_text_thd')} / ${t('thd.translated_text')}`}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ marginBottom: 8 }}
          />
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>{t('thd.termgroupcd_thd')}</th>
                  <th>{t('thd.termkey_thd')}</th>
                  <th>{t('thd.menu_table')}</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => (
                  <tr
                    key={item.term_key}
                    className={selectedItem?.term_key === item.term_key ? 'selected-row' : ''}
                    style={{ cursor: 'pointer' }}
                    onClick={() => setSelectedItem(item)}
                  >
                    <td>{item.term_group}</td>
                    <td>{item.term_key}</td>
                    <td>{getSourceTable(item.term_group)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측: 번역 목록 */}
        <div style={{ flex: 4, padding: '0 10px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.translations')}</h3>
            <div />
          </div>
          {selectedItem ? (
            <>
              <div style={{ marginBottom: 12, padding: '8px 12px', background: '#f9f9f9', borderRadius: 4, fontSize: 13 }}>
                <div><strong>{t('thd.termkey_thd')}:</strong> {selectedItem.term_key}</div>
                <div><strong>{t('thd.termgroupcd_thd')}:</strong> {selectedItem.term_group}</div>
                <div><strong>{t('thd.default_text_thd')}:</strong> {selectedItem.default_text}</div>
                <div><strong>{t('thd.menu_table')}:</strong> {getSourceTable(selectedItem.term_group)}</div>
              </div>
              <div>
                <table>
                  <thead>
                    <tr>
                      <th style={{ width: '30%' }}>{t('thd.languagecd')}</th>
                      <th>{t('thd.translated_text')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedItem.translations.length === 0 ? (
                      <tr>
                        <td colSpan={2} style={{ textAlign: 'center', color: '#aaa' }}>-</td>
                      </tr>
                    ) : (
                      selectedItem.translations.map((tr) => (
                        <tr key={tr.language_cd}>
                          <td>{tr.language_cd}</td>
                          <td>{tr.translated_text}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div style={{ color: '#aaa', fontSize: 13, paddingTop: 8 }}>{t('msg.term.select.trans')}</div>
          )}
        </div>

      </div>
    </div>
  )
}
