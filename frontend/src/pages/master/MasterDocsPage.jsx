import { useState } from 'react'
import { useDocs, useProjects, useSaveDoc, useDeleteDoc } from '@/hooks/useDocs'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'

export default function MasterDocsPage() {
  const user = useAuthStore((s) => s.user)
  const { data: docs = [] } = useDocs()
  const { data: projects = [] } = useProjects()
  const saveDoc = useSaveDoc()
  const deleteDoc = useDeleteDoc()

  const [selectedDoc, setSelectedDoc] = useState(null)
  const [docForm, setDocForm] = useState({ docid: '', projectid: '', docnm: '', docdesc: '' })
  const [templateFile, setTemplateFile] = useState(null)
  const [templateName, setTemplateName] = useState(null)
  const [docSaving, setDocSaving] = useState(false)

  const isEditYn = user?.editbuttonyn === 'Y'
  const selectedDocEditYn = selectedDoc?.editbuttonyn === 'Y'
  useLangStore((s) => s.translations)

  const selectDoc = (doc) => {
    setSelectedDoc(doc)
    setDocForm({ docid: doc.docid, projectid: doc.projectid, docnm: doc.docnm, docdesc: doc.docdesc || '' })
    setTemplateName(doc.basetemplatenm || null)
    setTemplateFile(null)
  }

  const handleDocNew = () => {
    setSelectedDoc(null)
    setDocForm({ docid: '', projectid: projects[0]?.projectid || '', docnm: '', docdesc: '' })
    setTemplateName(null)
    setTemplateFile(null)
  }

  const handleDocSave = () => {
    if (!docForm.projectid || !docForm.docnm) { alert(t('msg.doc.required')); return }
    setDocSaving(true)
    const fd = new FormData()
    fd.append('projectid', docForm.projectid)
    fd.append('docnm', docForm.docnm)
    if (docForm.docdesc) fd.append('docdesc', docForm.docdesc)
    if (docForm.docid) fd.append('docid', docForm.docid)
    if (templateFile) fd.append('templatefile', templateFile)
    saveDoc.mutate(fd, {
      onSuccess: () => setDocSaving(false),
      onError: () => setDocSaving(false),
    })
  }

  const handleDocDelete = () => {
    if (!docForm.docid) { alert(t('msg.doc.select.delete')); return }
    if (!window.confirm(t('msg.confirm.delete'))) return
    deleteDoc.mutate(docForm.docid, { onSuccess: handleDocNew })
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('mnu.master_data.docs.base')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* Left: doc cards */}
        <div style={{ flex: 3, paddingRight: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.doc.list')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleDocNew}>
              {t('btn.new')}
            </button>
          </div>
          <div className="chapter-card-container" style={{ flexDirection: 'column' }}>
            {docs.map((doc) => (
              <div
                key={doc.docid}
                className={`chapter-card${selectedDoc?.docid === doc.docid ? ' selected' : ''}`}
                onClick={() => selectDoc(doc)}
              >
                <div className="card-title">{doc.docnm} - {doc.projectnm}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: doc detail */}
        <div style={{ flex: 7, padding: '0 20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.doc.detail')}</h3>
            {(isEditYn || selectedDocEditYn) && (
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-primary" type="button" onClick={handleDocSave} disabled={docSaving || saveDoc.isPending}>
                  {t('btn.save')}
                </button>
                <button className="btn btn-danger" type="button" onClick={handleDocDelete} disabled={deleteDoc.isPending}>
                  {t('btn.delete')}
                </button>
              </div>
            )}
          </div>
          <div className="form-group">
            <label htmlFor="doc-projectid">{t('lbl.projectnm')}:</label>
            {docForm.docid ? (
              <span style={{ padding: '6px 4px', fontWeight: 600 }}>
                {projects.find((p) => String(p.projectid) === String(docForm.projectid))?.projectnm || docForm.projectid}
              </span>
            ) : (
              <select
                id="doc-projectid"
                value={docForm.projectid}
                onChange={(e) => setDocForm((f) => ({ ...f, projectid: e.target.value }))}
              >
                <option value="">{t('msg.select.project')}</option>
                {projects.map((p) => <option key={p.projectid} value={p.projectid}>{p.projectnm}</option>)}
              </select>
            )}
          </div>
          <div className="form-group">
            <label htmlFor="doc-docnm">{t('lbl.docnm')}:</label>
            <input
              id="doc-docnm"
              type="text"
              value={docForm.docnm}
              onChange={(e) => setDocForm((f) => ({ ...f, docnm: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label htmlFor="doc-docdesc">{t('lbl.description')}:</label>
            <textarea
              id="doc-docdesc"
              rows={3}
              value={docForm.docdesc}
              onChange={(e) => setDocForm((f) => ({ ...f, docdesc: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label>{t('lbl.template.upload')}:</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <button
                type="button"
                className="icon-btn"
                onClick={() => document.getElementById('doc-template-input').click()}
              >
                <img src="/icons/upload.svg" title={t('lbl.upload')} className="icon-img new-icon" alt={t('lbl.upload')} />
              </button>
              <input
                id="doc-template-input"
                type="file"
                style={{ display: 'none' }}
                accept=".docx"
                onChange={(e) => {
                  const f = e.target.files[0]
                  if (f) { setTemplateFile(f); setTemplateName(f.name) }
                }}
              />
              {selectedDoc?.basetemplateurl ? (
                <a
                  href="#"
                  onClick={async (e) => {
                    e.preventDefault()
                    try {
                      const res = await fetch(selectedDoc.basetemplateurl)
                      const blob = await res.blob()
                      const url = URL.createObjectURL(blob)
                      const a = document.createElement('a')
                      a.href = url; a.download = templateName || ''
                      document.body.appendChild(a); a.click()
                      document.body.removeChild(a); URL.revokeObjectURL(url)
                    } catch { window.open(selectedDoc.basetemplateurl, '_blank') }
                  }}
                >
                  {templateName || t('lbl.template.none')}
                </a>
              ) : (
                <span>{templateName || t('lbl.template.none')}</span>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
