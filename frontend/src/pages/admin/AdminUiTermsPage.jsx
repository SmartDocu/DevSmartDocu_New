import { useEffect, useState, useMemo } from 'react'
import { Input, Pagination } from 'antd'
import { useLangStore, t } from '@/stores/langStore'
import { useAdminUiTerms } from '@/hooks/useUiTerms'

const PAGE_SIZE = 15

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

  const [page, setPage] = useState(1)
  useEffect(() => { setPage(1) }, [searchText])
  const pagedItems = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('ttl.translations')}</div>
        </div>
      </div>

      <div className="panel-section" style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
        <div className="filter-item" style={{ width: '100%' }}>
          <label style={{ fontWeight: 'bold' }}>{t('lbl.search')}</label>
          <Input
            placeholder={`${t('thd.termkey_thd')} / ${t('thd.termgroupcd_thd')} / ${t('thd.default_text_thd')} / ${t('thd.translated_text')}`}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ height: 32, maxWidth: 480 }}
          />
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>

        {/* 좌측: 목록 */}
        <div className="panel-section" style={{ flex: 1.5, height: 'calc(100vh - 306px)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
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
                {t('lbl.count.docs').replace('{n}', filtered.length)}
              </span>
            </div>
            <div />
          </div>
          <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
            <table className="table table-bordered table-sm" style={{ cursor: 'pointer', tableLayout: 'fixed', width: '100%' }}>
              <thead>
                <tr>
                  <th style={{ width: '25%' }}>{t('thd.termgroupcd_thd')}</th>
                  <th style={{ width: '45%' }}>{t('thd.termkey_thd')}</th>
                  <th style={{ width: '30%' }}>{t('thd.menu_table')}</th>
                </tr>
              </thead>
              <tbody>
                {pagedItems.length === 0 ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : pagedItems.map((item) => (
                  <tr
                    key={item.term_key}
                    className={selectedItem?.term_key === item.term_key ? 'selected-row' : ''}
                    onClick={() => setSelectedItem(item)}
                  >
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={item.term_group}>{item.term_group}</td>
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={item.term_key}>{item.term_key}</td>
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{getSourceTable(item.term_group)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filtered.length > PAGE_SIZE && (
            <div style={{ marginTop: 'auto', paddingTop: 12, display: 'flex', justifyContent: 'center' }}>
              <Pagination
                current={page}
                pageSize={PAGE_SIZE}
                total={filtered.length}
                showSizeChanger={false}
                onChange={setPage}
              />
            </div>
          )}
        </div>

        {/* 우측: 번역 목록 */}
        <div className="panel-section" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 306px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.translations')}</h3>
            <div />
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          {selectedItem ? (
            <>
              <div style={{ marginBottom: 12, padding: '8px 12px', background: '#f9f9f9', borderRadius: 4, fontSize: 13 }}>
                <div><strong>{t('thd.termkey_thd')}:</strong> {selectedItem.term_key}</div>
                <div><strong>{t('thd.termgroupcd_thd')}:</strong> {selectedItem.term_group}</div>
                <div><strong>{t('thd.default_text_thd')}:</strong> {selectedItem.default_text}</div>
                <div><strong>{t('thd.menu_table')}:</strong> {getSourceTable(selectedItem.term_group)}</div>
              </div>
              <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
                <table className="table table-bordered table-sm">
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
    </div>
  )
}
