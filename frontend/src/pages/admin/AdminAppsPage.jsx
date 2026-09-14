import { useState, useEffect } from 'react'
import { App } from 'antd'
import { SaveOutlined } from '@ant-design/icons'
import { useLangStore, t } from '@/stores/langStore'
import { useLanguages } from '@/hooks/useI18n'
import { useApps, useAppTranslations, useSaveAppTranslation, useDeleteAppTranslation } from '@/hooks/useApps'
import { useAuthStore } from '@/stores/authStore'

export default function AdminAppsPage() {
  useLangStore((s) => s.translations)
  const { message } = App.useApp()

  const user = useAuthStore((s) => s.user)
  const { data: { apps = [] } = {} } = useApps({ enabled: !!user })
  const { data: languages = [] } = useLanguages()

  const [selectedAppcd, setSelectedAppcd] = useState(null)
  const [transEdits, setTransEdits] = useState({})

  const { data: translations = [] } = useAppTranslations(selectedAppcd)
  const saveTrans = useSaveAppTranslation()
  const deleteTrans = useDeleteAppTranslation()

  const translationsKey = translations.map((tr) => `${tr.languagecd}:${tr.translated_text}`).join(',')
  const languagesKey = languages.map((l) => l.languagecd).join(',')

  useEffect(() => {
    const init = {}
    languages.forEach((l) => {
      const found = translations.find((tr) => tr.languagecd === l.languagecd)
      init[l.languagecd] = found ? found.translated_text || '' : ''
    })
    setTransEdits(init)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [translationsKey, languagesKey])

  const handleAppSelect = (appcd) => {
    setSelectedAppcd(appcd)
  }

  const handleSave = async () => {
    if (!selectedAppcd) { message.warning(t('msg.app.select.trans')); return }
    await Promise.all(
      languages.map((l) => {
        const text = transEdits[l.languagecd] ?? ''
        const hasTrans = translations.some((tr) => tr.languagecd === l.languagecd)
        if (text) return saveTrans.mutateAsync({ appcd: selectedAppcd, languagecd: l.languagecd, translated_text: text })
        if (!text && hasTrans) return deleteTrans.mutateAsync({ appcd: selectedAppcd, languagecd: l.languagecd })
        return Promise.resolve()
      })
    )
    message.success(t('msg.save.success'))
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('ttl.system.translation.apps')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>

        {/* 좌측: 앱 목록 */}
        <div className="panel-section" style={{ flex: 4, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 224px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
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
                {t('lbl.count.docs').replace('{n}', apps.length)}
              </span>
            </div>
            <div />
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
            <table className="table table-bordered table-sm" style={{ tableLayout: 'fixed', width: '100%' }}>
              <thead>
                <tr>
                  <th style={{ width: '40%' }}>{t('lbl.appcd')}</th>
                  <th style={{ width: '60%' }}>{t('thd.appnm_thd')}</th>
                </tr>
              </thead>
              <tbody>
                {apps.map((app) => (
                  <tr
                    key={app.appcd}
                    className={selectedAppcd === app.appcd ? 'selected-row' : ''}
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleAppSelect(app.appcd)}
                  >
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={app.appcd}>{app.appcd}</td>
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={app.appnm}>{app.appnm}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </div>
        </div>

        {/* 우측: 번역 표 */}
        <div className="panel-section" style={{ flex: 6, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 224px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.translations')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleSave} disabled={!selectedAppcd || saveTrans.isPending || deleteTrans.isPending}>
              <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
            </button>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          {selectedAppcd ? (
            <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
              <table className="table table-bordered table-sm">
                <thead>
                  <tr>
                    <th style={{ width: '22%' }}>{t('thd.languagecd')}</th>
                    <th style={{ width: '28%' }}>{t('thd.languagenm')}</th>
                    <th>{t('thd.translated_text')}</th>
                  </tr>
                </thead>
                <tbody>
                  {languages.map((l) => (
                    <tr key={l.languagecd}>
                      <td>{l.languagecd}</td>
                      <td>{l.languagenm}</td>
                      <td style={{ padding: '3px 4px' }}>
                        <input
                          type="text"
                          style={{ width: '100%', boxSizing: 'border-box', height: 38 }}
                          value={transEdits[l.languagecd] ?? ''}
                          onChange={(e) => setTransEdits((prev) => ({ ...prev, [l.languagecd]: e.target.value }))}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ color: '#aaa', fontSize: 13, paddingTop: 8 }}>{t('msg.app.select.trans')}</div>
          )}
          </div>
        </div>

      </div>
    </div>
  )
}
