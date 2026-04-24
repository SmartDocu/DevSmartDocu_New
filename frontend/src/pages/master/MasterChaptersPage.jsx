import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTabStore } from '@/stores/tabStore'
import { useMenus } from '@/hooks/useMenus'
import { useChapters, useSaveChapter, useDeleteChapter } from '@/hooks/useChapters'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'

export default function MasterChaptersPage() {
  useLangStore((s) => s.translations)

  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { openTab } = useTabStore()
  const { data: allMenus = [] } = useMenus()

  const openInTab = (routePath, query) => {
    const menu = allMenus.find((m) => m.route_path === routePath)
    if (menu) openTab({ key: menu.menucd, label: t(`mnu.${menu.menucd}`, menu.default_text), path: `${routePath}${query}` })
    navigate(`/${routePath}${query}`)
  }
  const user = useAuthStore((s) => s.user)

  const selectedDocid = user?.docid ? Number(user.docid) : null
  const { data: chapters = [] } = useChapters(selectedDocid)
  const saveChapter = useSaveChapter()
  const deleteChapter = useDeleteChapter()

  const [selectedChap, setSelectedChap] = useState(null)
  const [form, setForm] = useState({ chapternm: '', chapterno: '', useyn: true })
  const [templateFile, setTemplateFile] = useState(null)
  const [templateName, setTemplateName] = useState('')
  const [saving, setSaving] = useState(false)

  // URL param: chapteruid → auto-select (한 번만)
  useEffect(() => {
    const uid = searchParams.get('chapteruid')
    if (uid && chapters.length > 0 && !selectedChap) {
      const ch = chapters.find((c) => String(c.chapteruid) === uid)
      if (ch) selectChapter(ch)
    }
  }, [chapters, searchParams])

  const selectChapter = (ch) => {
    setSelectedChap(ch)
    setForm({ chapternm: ch.chapternm, chapterno: ch.chapterno, useyn: ch.useyn })
    setTemplateName(ch.chaptertemplatenm || '')
    setTemplateFile(null)
  }

  const handleNew = () => {
    setSelectedChap(null)
    setForm({ chapternm: '', chapterno: '', useyn: true })
    setTemplateName('')
    setTemplateFile(null)
  }

  const handleSave = () => {
    if (!form.chapterno) { alert(t('msg.chapter.required')); return }
    if (!selectedDocid) { alert(t('msg.doc.select')); return }
    setSaving(true)
    const fd = new FormData()
    fd.append('docid', selectedDocid)
    fd.append('chapternm', form.chapternm)
    fd.append('chapterno', form.chapterno)
    fd.append('useyn', form.useyn ? 'true' : 'false')
    if (selectedChap?.chapteruid) fd.append('chapteruid', selectedChap.chapteruid)
    if (templateFile) fd.append('templatefile', templateFile)
    saveChapter.mutate(fd, {
      onSuccess: () => setSaving(false),
      onError: () => setSaving(false),
    })
  }

  const handleDelete = () => {
    if (!selectedChap) { alert(t('msg.chapter.select.delete')); return }
    if (!window.confirm(t('msg.confirm.delete'))) return
    deleteChapter.mutate(
      { chapteruid: selectedChap.chapteruid, docid: selectedDocid },
      { onSuccess: () => { setSelectedChap(null); setForm({ chapternm: '', chapterno: '', useyn: true }) } },
    )
  }

  const isEditYn = user?.editbuttonyn === 'Y'

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('mnu.master_data.chapters.base')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* Left: chapter cards */}
        <div style={{ flex: 3, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleNew}>
              {t('btn.new')}
            </button>
          </div>
          <div className="chapter-card-container" style={{ flexDirection: 'column' }}>
            {chapters.map((ch) => (
              <div
                key={ch.chapteruid}
                className={`chapter-card${selectedChap?.chapteruid === ch.chapteruid ? ' selected' : ''}`}
                data-useyn={ch.useyn ? 'true' : 'false'}
                onClick={() => selectChapter(ch)}
              >
                <div className="card-title">{ch.chapternm}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: chapter detail */}
        <div style={{ flex: 7, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {selectedChap && (
                <>
                  <button
                    className="btn btn-primary"
                    type="button"
                    onClick={() => {
                      sessionStorage.setItem('chapter_object_chapteruid', selectedChap.chapteruid)
                      openInTab('master/object', `?chapteruid=${selectedChap.chapteruid}&docid=${selectedDocid}`)
                    }}
                  >
                    {t('btn.object.manage')}
                  </button>
                  <button
                    className="btn btn-primary"
                    type="button"
                    onClick={() => openInTab('master/chapter-template', `?chapteruid=${selectedChap.chapteruid}&docid=${selectedDocid}`)}
                  >
                    {t('btn.template.edit')}
                  </button>
                  <span style={{ color: '#d9d9d9', margin: '0 12px' }}>|</span>
                </>
              )}
              {isEditYn && (
                <>
                  <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saving}>
                    {t('btn.save')}
                  </button>
                  {selectedChap && (
                    <button className="btn btn-danger" type="button" onClick={handleDelete}>
                      {t('btn.delete')}
                    </button>
                  )}
                </>
              )}
            </div>
          </div>

          <div className="form-group">
            <label>{t('lbl.chapternm')}:</label>
            <input
              type="text"
              value={form.chapternm}
              onChange={(e) => setForm((f) => ({ ...f, chapternm: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label>{t('lbl.chapterno')}:</label>
            <input
              type="number"
              value={form.chapterno}
              onChange={(e) => setForm((f) => ({ ...f, chapterno: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label>{t('lbl.useyn')}:</label>
            <input
              type="checkbox"
              checked={!!form.useyn}
              onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
            />
          </div>
          <div className="form-group">
            <label>{t('lbl.template.upload')}:</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <button
                type="button"
                className="icon-btn"
                onClick={() => document.getElementById('chap-template-input').click()}
              >
                <img src="/icons/upload.svg" title={t('lbl.upload')} className="icon-img new-icon" alt={t('lbl.upload')} />
              </button>
              <input
                id="chap-template-input"
                type="file"
                style={{ display: 'none' }}
                accept=".docx"
                onChange={(e) => {
                  const f = e.target.files[0]
                  if (f) { setTemplateFile(f); setTemplateName(f.name) }
                }}
              />
              {selectedChap?.chaptertemplateurl ? (
                <a
                  href="#"
                  onClick={async (e) => {
                    e.preventDefault()
                    try {
                      const res = await fetch(selectedChap.chaptertemplateurl)
                      const blob = await res.blob()
                      const url = URL.createObjectURL(blob)
                      const a = document.createElement('a')
                      a.href = url; a.download = templateName || ''
                      document.body.appendChild(a); a.click()
                      document.body.removeChild(a); URL.revokeObjectURL(url)
                    } catch { window.open(selectedChap.chaptertemplateurl, '_blank') }
                  }}
                >
                  {templateName || t('msg.template.none')}
                </a>
              ) : (
                <span>{templateName || t('msg.template.none')}</span>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  )
}
