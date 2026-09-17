import { useEffect, useState } from 'react'
import { useSearchParams, useLocation } from 'react-router-dom'
import { App } from 'antd'
import { PlusOutlined, SaveOutlined, DeleteOutlined, ExportOutlined, UploadOutlined } from '@ant-design/icons'
import { useMenus } from '@/hooks/useMenus'
import { useOpenInTab } from '@/hooks/useOpenInTab'
import { useChapters, useSaveChapter, useDeleteChapter } from '@/hooks/useChapters'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'

export default function MasterChaptersPage() {
  useLangStore((s) => s.translations)
  const { message, modal } = App.useApp()

  const [searchParams, setSearchParams] = useSearchParams()
  const location = useLocation()
  const { data: allMenus = [] } = useMenus()
  const currentMenu = allMenus.find((m) => m.route_path && location.pathname.includes(m.route_path))
  const menuNm = currentMenu ? (t(`mnu.${currentMenu.menucd}`) || currentMenu.default_text || '') : ''

  const openInTab = useOpenInTab()
  const user = useAuthStore((s) => s.user)
  const docnm = useAuthStore((s) => s.user?.docnm)

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
    if (searchParams.get('chapteruid')) {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.delete('chapteruid')
        return next
      }, { replace: true })
    }
  }

  const handleSave = () => {
    if (!selectedDocid) { message.warning(t('msg.doc.select')); return }
    if (!form.chapternm) { message.warning(t('msg.chapternm.required')); return }
    if (!form.chapterno) { message.warning(t('msg.chapter.required')); return }
    setSaving(true)
    const fd = new FormData()
    fd.append('docid', selectedDocid)
    fd.append('chapternm', form.chapternm)
    fd.append('chapterno', form.chapterno)
    fd.append('useyn', form.useyn ? 'true' : 'false')
    if (selectedChap?.chapteruid) fd.append('chapteruid', selectedChap.chapteruid)
    if (templateFile) fd.append('templatefile', templateFile)
    saveChapter.mutate(fd, {
      onSuccess: () => {
        setSaving(false)
        handleNew()   // 👈 여기 추가
      },
      onError: () => setSaving(false),
    })
  }

  const handleDelete = () => {
    if (!selectedChap) { message.warning(t('msg.chapter.select.delete')); return }
    modal.confirm({
      content: t('msg.confirm.delete'),
      onOk: () => {
        deleteChapter.mutate(
          { chapteruid: selectedChap.chapteruid, docid: selectedDocid },
          { onSuccess: () => { setSelectedChap(null); setForm({ chapternm: '', chapterno: '', useyn: true }) } },
        )
      },
    })
  }

  const isEditYn = user?.editbuttonyn === 'Y'

  if (!selectedDocid) {
    return <div style={{ padding: 24, color: '#888' }}>{t('msg.doc.select')}</div>
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{menuNm}{docnm ? ` - ${docnm}` : ''}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
        {/* Left: chapter cards */}
        <div className="panel-section" style={{ flex: 3, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 224px)' }}>
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
                {t('lbl.count.docs').replace('{n}', chapters.length)}
              </span>
            </div>
            <button className="btn btn-primary" type="button" onClick={handleNew}>
              <PlusOutlined style={{ marginRight: 6 }} />{t('btn.new')}
            </button>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          <div className="chapter-card-container" style={{ flexDirection: 'column' }}>
            {chapters.length === 0 ? (
              <div style={{ padding: 24, color: '#888', textAlign: 'center' }}>{t('msg.no.chapter')}</div>
            ) : chapters.map((ch) => (
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
        </div>

        {/* Right: chapter detail */}
        <div className="panel-section" style={{ flex: 7, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 224px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {selectedChap && (
                <>
                  <button
                    className="btn btn-secondary"
                    type="button"
                    onClick={() => {
                      sessionStorage.setItem('chapter_object_chapteruid', selectedChap.chapteruid)
                      openInTab('master/object', `?chapteruid=${selectedChap.chapteruid}&docid=${selectedDocid}`)
                    }}
                  >
                    {t('btn.object.manage')}<ExportOutlined style={{ marginLeft: 6 }} />
                  </button>
                  <button
                    className="btn btn-secondary"
                    type="button"
                    onClick={() => openInTab('master/chapter-template', `?chapteruid=${selectedChap.chapteruid}&docid=${selectedDocid}`)}
                  >
                    {t('btn.template.edit')}<ExportOutlined style={{ marginLeft: 6 }} />
                  </button>
                  <span style={{ color: '#d9d9d9', margin: '0 12px' }}>|</span>
                </>
              )}
              {isEditYn && (
                <>
                  <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saving || deleteChapter.isPending}>
                    <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
                  </button>
                  {selectedChap && (
                    <button
                      className="btn btn-danger"
                      type="button"
                      onClick={handleDelete}
                      disabled={deleteChapter.isPending}
                      title={t('btn.delete')}
                      style={{ width: 38, height: 38, padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                    >
                      <DeleteOutlined />
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>

          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('thd.chapternm')}:</label>
            <input
              type="text"
              value={form.chapternm}
              onChange={(e) => setForm((f) => ({ ...f, chapternm: e.target.value }))}
              style={{ height: 38 }}
            />
          </div>
          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.chapterno')}:</label>
            <input
              type="number"
              value={form.chapterno}
              onChange={(e) => setForm((f) => ({ ...f, chapterno: e.target.value }))}
              style={{ height: 38 }}
            />
          </div>
          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.useyn_lbl')}:</label>
            <div style={{ paddingLeft: 60 }}>
              <input
                type="checkbox"
                checked={!!form.useyn}
                onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
              />
            </div>
          </div>
          <div className="form-group">
            <label>{t('lbl.chapter_template.bgformat')}:</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => document.getElementById('chap-template-input').click()}
              >
                <UploadOutlined style={{ marginRight: 6 }} />{t('btn.upload')}
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
                  {templateName || t('msg.chapter_template.none')}
                </a>
              ) : (
                <span>{templateName || t('msg.chapter_template.none')}</span>
              )}
            </div>
          </div>

          </div>
        </div>
      </div>
    </div>
  )
}
