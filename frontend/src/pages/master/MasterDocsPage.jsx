import { useState } from 'react'
import { App, Tag } from 'antd'
import { PlusOutlined, SaveOutlined, DeleteOutlined, UploadOutlined } from '@ant-design/icons'
import { useDocs, useProjects, useSaveDoc, useDeleteDoc } from '@/hooks/useDocs'
import { useLangStore, t } from '@/stores/langStore'
import { useDataParams } from '@/hooks/useDataParams'
import { useDocDatasets } from '@/hooks/useDocDatasets'
import { useMenuCodes } from '@/hooks/useMenus'
import DocGroupSelectModal from './DocGroupSelectModal'

export default function MasterDocsPage() {
  const { message, modal } = App.useApp()
  const { data: docs = [] } = useDocs()
  const { data: projects = [] } = useProjects()
  const saveDoc = useSaveDoc()
  const deleteDoc = useDeleteDoc()

  const [selectedDoc, setSelectedDoc] = useState(null)
  const [docForm, setDocForm] = useState({ docid: '', projectid: '', docnm: '', docdesc: '', docgroupid: '', docgroupnm: '' })
  const [templateFile, setTemplateFile] = useState(null)
  const [templateName, setTemplateName] = useState(null)
  const [docSaving, setDocSaving] = useState(false)
  const [groupModalOpen, setGroupModalOpen] = useState(false)

  const selectedDocEditYn = selectedDoc?.editbuttonyn === 'Y'
  const canEdit = selectedDoc ? selectedDocEditYn : projects.length > 0
  useLangStore((s) => s.translations)

  const { data: docParams = [] } = useDataParams(docForm.docid ? String(docForm.docid) : null)
  const { data: datasetData } = useDocDatasets(docForm.docid ? String(docForm.docid) : null)
  const { data: dataSourceCodes = [] } = useMenuCodes('datasourcecd')
  const dataSourceLabel = (code) => {
    const c = dataSourceCodes.find((dc) => dc.codevalue === code)
    return c ? (t(c.term_key) || c.default_name) : code
  }

  const selectDoc = (doc) => {
    setSelectedDoc(doc)
    setDocForm({ docid: doc.docid, projectid: doc.projectid, docnm: doc.docnm, docdesc: doc.docdesc || '', docgroupid: doc.docgroupid || '', docgroupnm: doc.docgroupnm || '' })
    setTemplateName(doc.basetemplatenm || null)
    setTemplateFile(null)
  }

  const handleDocNew = () => {
    setSelectedDoc(null)
    setDocForm({ docid: '', projectid: projects[0]?.projectid || '', docnm: '', docdesc: '', docgroupid: '', docgroupnm: '' })
    setTemplateName(null)
    setTemplateFile(null)
  }

  const handleDocSave = () => {
    if (!docForm.projectid) { message.warning(t('msg.select.project')); return }
    if (!docForm.docnm) { message.warning(t('msg.docnm.required')); return }
    setDocSaving(true)
    const fd = new FormData()
    fd.append('projectid', docForm.projectid)
    fd.append('docnm', docForm.docnm)
    if (docForm.docdesc) fd.append('docdesc', docForm.docdesc)
    if (docForm.docid) fd.append('docid', docForm.docid)
    if (docForm.docgroupid) fd.append('docgroupid', docForm.docgroupid)
    if (templateFile) fd.append('templatefile', templateFile)
    saveDoc.mutate(fd, {
      onSuccess: () => setDocSaving(false),
      onError: () => setDocSaving(false),
    })
  }

  const handleDocDelete = () => {
    if (!docForm.docid) { message.warning(t('msg.doc.select.delete')); return }
    modal.confirm({
      content: t('msg.confirm.delete'),
      okType: 'danger',
      onOk: () => deleteDoc.mutate(docForm.docid, { onSuccess: handleDocNew }),
    })
  }

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('ttl.master_data.docs.base')}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
        {/* Left: doc list */}
        <div className="panel-section" style={{ flex: 1.5, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 224px)' }}>
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
                {t('lbl.count.docs').replace('{n}', docs.length)}
              </span>
            </div>
            <button className="btn btn-primary" type="button" onClick={handleDocNew}>
              <PlusOutlined style={{ marginRight: 6 }} />{t('btn.new')}
            </button>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          <div className="table-container">
            <table className="table table-bordered table-sm" style={{ tableLayout: 'fixed' }}>
              <thead>
                <tr>
                  <th style={{ width: '20%' }}>{t('lbl.docnm')}</th>
                  <th style={{ width: '28%' }}>{t('lbl.projectnm_lbl')}</th>
                  <th style={{ width: '18%' }}>{t('lbl.docgroupnm')}</th>
                  <th style={{ width: '34%' }}>{t('lbl.desc_lbl')}</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((doc) => (
                  <tr
                    key={doc.docid}
                    className={selectedDoc?.docid === doc.docid ? 'selected-row' : ''}
                    style={{ cursor: 'pointer' }}
                    onClick={() => selectDoc(doc)}
                  >
                    <td style={{ wordBreak: 'break-word' }}>{doc.docnm}</td>
                    <td style={{ wordBreak: 'break-word' }}>{doc.projectnm}</td>
                    <td style={{ wordBreak: 'break-word' }}>{doc.docgroupnm || ''}</td>
                    <td style={{ wordBreak: 'break-word' }}>{doc.docdesc || ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </div>
        </div>

        {/* Right: doc detail */}
        <div className="panel-section" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 224px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            {canEdit && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button className="btn btn-primary" type="button" onClick={handleDocSave} disabled={docSaving || saveDoc.isPending || deleteDoc.isPending}>
                  <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
                </button>
                {selectedDoc && (
                  <>
                    <span style={{ color: '#d9d9d9' }}>|</span>
                    <button
                      className="btn btn-danger"
                      type="button"
                      onClick={handleDocDelete}
                      disabled={deleteDoc.isPending}
                      title={t('btn.delete')}
                      style={{ width: 38, height: 38, padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                    >
                      <DeleteOutlined />
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          <div className="form-group">
            <label htmlFor="doc-projectid"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.projectnm_lbl')}:</label>
            {docForm.docid ? (
              <span style={{ padding: '6px 4px', fontWeight: 600 }}>
                {selectedDoc?.projectnm || docForm.projectid}
              </span>
            ) : (
              <select
                id="doc-projectid"
                value={docForm.projectid}
                onChange={(e) => setDocForm((f) => ({ ...f, projectid: e.target.value }))}
                style={{ height: 38 }}
              >
                <option value="">{t('msg.select.project')}</option>
                {projects.map((p) => <option key={p.projectid} value={p.projectid}>{p.projectnm}</option>)}
              </select>
            )}
          </div>
          <div className="form-group">
            <label>{t('lbl.docgroupnm')}:</label>
            {docForm.docgroupid ? (
              <Tag
                color="blue"
                closable={canEdit}
                onClose={() => setDocForm((f) => ({ ...f, docgroupid: '', docgroupnm: '' }))}
                onClick={canEdit && docForm.projectid ? () => setGroupModalOpen(true) : undefined}
                style={{ fontSize: 13, padding: '3px 10px', cursor: canEdit ? 'pointer' : 'default', userSelect: 'none' }}
              >
                {docForm.docgroupnm}
              </Tag>
            ) : canEdit && docForm.projectid ? (
              <button
                type="button"
                onClick={() => setGroupModalOpen(true)}
                style={{ background: 'none', border: '1px dashed #d9d9d9', borderRadius: 6, padding: '3px 12px', color: '#1677ff', cursor: 'pointer', fontSize: 13 }}
              >
                + {t('btn.select.group')}
              </button>
            ) : (
              <span style={{ color: '#bbb', fontSize: 13 }}>-</span>
            )}
          </div>
          <div className="form-group">
            <label htmlFor="doc-docnm"><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.docnm')}:</label>
            <input
              id="doc-docnm"
              type="text"
              value={docForm.docnm}
              onChange={(e) => setDocForm((f) => ({ ...f, docnm: e.target.value }))}
              style={{ height: 38 }}
            />
          </div>
          <div className="form-group">
            <label htmlFor="doc-docdesc">{t('lbl.desc_lbl')}:</label>
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
                className="btn btn-secondary"
                onClick={() => document.getElementById('doc-template-input').click()}
              >
                <UploadOutlined style={{ marginRight: 6 }} />{t('btn.upload')}
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
            const lines = checkedDatas.map((d) => `[${d.datanm}] (${dataSourceLabel(d.datasourcecd)})`)
            return (
              <div style={{ marginTop: 16 }}>
                <h4 style={{ margin: '0 0 8px', fontWeight: 600 }}>{t('ttl.dataset_ttl')}</h4>
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

      <DocGroupSelectModal
        open={groupModalOpen}
        onClose={() => setGroupModalOpen(false)}
        projectid={docForm.projectid}
        onSelect={(docgroupid, docgroupnm) => setDocForm((f) => ({ ...f, docgroupid, docgroupnm }))}
      />
    </div>
  )
}
