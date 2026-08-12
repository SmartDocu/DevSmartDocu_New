import { useState, useEffect } from 'react'
import { App } from 'antd'
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
          <div className="gradient-bar" />
          <div>{t('ttl.system.translation.apps')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 20, paddingRight: 10 }}>

        {/* 좌측: 앱 목록 */}
        <div style={{ flex: 4 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <div />
          </div>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>{t('lbl.appcd')}</th>
                  <th>{t('thd.appnm_thd')}</th>
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
                    <td>{app.appcd}</td>
                    <td>{app.appnm}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측: 번역 표 */}
        <div style={{ flex: 6, padding: '0 10px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.translations')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleSave} disabled={!selectedAppcd || saveTrans.isPending}>
              {t('btn.save')}
            </button>
          </div>
          {selectedAppcd ? (
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th style={{ width: '22%', padding: '4px 8px' }}>{t('thd.languagecd')}</th>
                    <th style={{ width: '28%', padding: '4px 8px' }}>{t('thd.languagenm')}</th>
                    <th style={{ padding: '4px 8px' }}>{t('thd.translated_text')}</th>
                  </tr>
                </thead>
                <tbody>
                  {languages.map((l) => (
                    <tr key={l.languagecd}>
                      <td style={{ padding: '3px 8px' }}>{l.languagecd}</td>
                      <td style={{ padding: '3px 8px' }}>{l.languagenm}</td>
                      <td style={{ padding: '3px 4px' }}>
                        <input
                          type="text"
                          style={{ width: '100%', boxSizing: 'border-box' }}
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
  )
}
