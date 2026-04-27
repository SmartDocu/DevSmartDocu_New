import { useState } from 'react'
import { useDocs, useProjects, useSaveDoc, useDeleteDoc } from '@/hooks/useDocs'
import { useLangStore, t } from '@/stores/langStore'
import { useDataParams } from '@/hooks/useDataParams'
import { useDocDatasets } from '@/hooks/useDocDatasets'

export default function MasterDocsPage() {
  const { data: docs = [] } = useDocs()
  const { data: projects = [] } = useProjects()
  const saveDoc = useSaveDoc()
  const deleteDoc = useDeleteDoc()

  const [selectedDoc, setSelectedDoc] = useState(null)
  const [docForm, setDocForm] = useState({ docid: '', projectid: '', docnm: '', docdesc: '' })
  const [templateFile, setTemplateFile] = useState(null)
  const [templateName, setTemplateName] = useState(null)
  const [docSaving, setDocSaving] = useState(false)

  const selectedDocEditYn = selectedDoc?.editbuttonyn === 'Y'
  const canEdit = selectedDoc ? selectedDocEditYn : projects.length > 0
  useLangStore((s) => s.translations)

  const { data: docParams = [] } = useDataParams(docForm.docid ? String(docForm.docid) : null)
  const { data: datasetData } = useDocDatasets(docForm.docid ? String(docForm.docid) : null)

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
        <div style={{ flex: 3, paddingRight: 20, overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
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
        <div style={{ flex: 7, padding: '0 20px', overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            {canEdit && (
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-primary" type="button" onClick={handleDocSave} disabled={docSaving || saveDoc.isPending}>
                  {t('btn.save')}
                </button>
                {selectedDoc && (
                  <button className="btn btn-danger" type="button" onClick={handleDocDelete} disabled={deleteDoc.isPending}>
                    {t('btn.delete')}
                  </button>
                )}
              </div>
            )}
          </div>
          <div className="form-group">
            <label htmlFor="doc-projectid"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.projectnm')}:</label>
            {docForm.docid ? (
              <span style={{ padding: '6px 4px', fontWeight: 600 }}>
                {selectedDoc?.projectnm || docForm.projectid}
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
            <label htmlFor="doc-docnm"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.docnm')}:</label>
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
                  {templateName || t('msg.template.none')}
                </a>
              ) : (
                <span>{templateName || t('msg.template.none')}</span>
              )}
            </div>
          </div>
          {docForm.docid && (
            <div style={{ marginTop: 24 }}>
              <h4 style={{ margin: '0 0 8px', fontWeight: 600 }}>{t('ttl.condition')}</h4>
              <textarea
                readOnly
                rows={Math.max(3, docParams.length)}
                style={{ width: '100%', resize: 'vertical', background: '#fafafa', color: '#333', fontSize: 13 }}
                value={
                  docParams.length === 0
                    ? t('msg.no.data')
                    : docParams.map((p) =>
                        `${p.orderno ?? '-'}. ${p.paramnm}  ${p.operator}  ${p.samplevalue ?? ''}${p.datanm ? `  ← ${p.datanm}${p.keycolnm ? `(${p.keycolnm})` : ''}` : ''}`
                      ).join('\n')
                }
              />
            </div>
          )}
          {docForm.docid && (() => {
            const datas = datasetData?.datas || []
            const dataparam_map = datasetData?.dataparam_map || {}
            const selected_datauids = datasetData?.selected_datauids || []
            const allChecked = [...new Set([...selected_datauids, ...Object.keys(dataparam_map)])]
            const checkedDatas = datas.filter((d) => allChecked.includes(d.datauid))
            const lines = checkedDatas.map((d) => `[${d.datanm}] (${d.datasourcecd})`)
            return (
              <div style={{ marginTop: 16 }}>
                <h4 style={{ margin: '0 0 8px', fontWeight: 600 }}>{t('ttl.dataset')}</h4>
                <textarea
                  readOnly
                  rows={Math.max(3, lines.length)}
                  style={{ width: '100%', resize: 'vertical', background: '#fafafa', color: '#333', fontSize: 13 }}
                  value={lines.length === 0 ? t('msg.no.data') : lines.join('\n')}
                />
              </div>
            )
          })()}
        </div>
      </div>
    </div>
  )
}
