import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDocs, useProjects, useSaveDoc, useDeleteDoc, useParams, useSaveParam, useDeleteParam } from '@/hooks/useDocs'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'

const OPERATORS = ['=', '>=', '<=', '>', '<']

export default function MasterDocsPage() {
  const navigate = useNavigate()
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

  // Params
  const { data: params = [], refetch: refetchParams } = useParams(selectedDoc?.docid || null)
  const saveParam = useSaveParam()
  const deleteParam = useDeleteParam()

  const [selectedParam, setSelectedParam] = useState(null)
  const [paramForm, setParamForm] = useState({
    paramuid: '', paramnm: '', orderno: '', samplevalue: '', operator: '=',
  })

  const isEditYn = user?.editbuttonyn === 'Y'
  const selectedDocEditYn = selectedDoc?.editbuttonyn === 'Y'
  // 언어 변경 시 re-render 트리거
  useLangStore((s) => s.translations)

  const selectDoc = (doc) => {
    setSelectedDoc(doc)
    setDocForm({ docid: doc.docid, projectid: doc.projectid, docnm: doc.docnm, docdesc: doc.docdesc || '' })
    setTemplateName(doc.basetemplatenm || null)
    setTemplateFile(null)
    setSelectedParam(null)
    setParamForm({ paramuid: '', paramnm: '', orderno: '', samplevalue: '', operator: '=' })
  }

  const handleDocNew = () => {
    setSelectedDoc(null)
    setDocForm({ docid: '', projectid: projects[0]?.projectid || '', docnm: '', docdesc: '' })
    setTemplateName(null)
    setTemplateFile(null)
    setSelectedParam(null)
  }

  const handleDocSave = () => {
    if (!docForm.projectid || !docForm.docnm) { alert('프로젝트와 문서명은 필수입니다.'); return }
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
    if (!docForm.docid) { alert('삭제할 문서를 선택하세요.'); return }
    if (!window.confirm('정말 삭제하시겠습니까?')) return
    deleteDoc.mutate(docForm.docid, { onSuccess: handleDocNew })
  }

  // Param actions
  const selectParam = (p) => {
    setSelectedParam(p)
    setParamForm({
      paramuid: p.paramuid,
      paramnm: p.paramnm,
      orderno: p.orderno ?? '',
      samplevalue: p.samplevalue || '',
      operator: p.operator || '=',
    })
  }

  const handleParamNew = () => {
    setSelectedParam(null)
    setParamForm({ paramuid: '', paramnm: '', orderno: '', samplevalue: '', operator: '=' })
  }

  const handleParamSave = () => {
    if (!selectedDoc?.docid) { alert('문서를 선택해주세요.'); return }
    if (!paramForm.paramnm) { alert('매개변수명을 입력해주세요.'); return }
    saveParam.mutate({
      paramuid: paramForm.paramuid || null,
      docid: selectedDoc.docid,
      paramnm: paramForm.paramnm,
      orderno: paramForm.orderno ? Number(paramForm.orderno) : null,
      samplevalue: paramForm.samplevalue,
      operator: paramForm.operator || '=',
    }, { onSuccess: handleParamNew })
  }

  const handleParamDelete = () => {
    if (!paramForm.paramuid) { alert('삭제할 매개변수를 선택하세요.'); return }
    if (!window.confirm('정말 삭제하시겠습니까?')) return
    deleteParam.mutate({ paramuid: paramForm.paramuid, docid: selectedDoc?.docid }, {
      onSuccess: handleParamNew,
    })
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
        <div style={{ flex: 1, paddingRight: 20 }}>
          <h3>{t('ttl.doc.list')}</h3>
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

        {/* Middle: doc detail */}
        <div style={{ flex: 1.5, padding: '0 20px' }}>
          <h3>{t('ttl.doc.detail')}</h3>
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
            <label htmlFor="doc-docdesc">{t('lbl.docdesc')}:</label>
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
                <img src="/icons/upload.svg" title="업로드" className="icon-img new-icon" alt="업로드" />
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

          <div className="button-group" id="doc-buttons">
            <button className="icon-btn" type="button" onClick={handleDocNew}>
              <div className="icon-wrapper">
                <img src="/icons/new.svg" className="icon-img new-icon" alt="신규" />
                <span className="icon-label">{t('btn.new')}</span>
              </div>
            </button>
            {(isEditYn || selectedDocEditYn) && (
              <>
                <button className="icon-btn" type="button" onClick={handleDocSave} disabled={docSaving || saveDoc.isPending}>
                  <div className="icon-wrapper">
                    <img src="/icons/save.svg" className="icon-img save-icon" alt="저장" />
                    <span className="icon-label">{t('btn.save')}</span>
                  </div>
                </button>
                <button className="icon-btn" type="button" onClick={handleDocDelete} disabled={deleteDoc.isPending}>
                  <div className="icon-wrapper">
                    <img src="/icons/delete.svg" className="icon-img del-icon" alt="삭제" />
                    <span className="icon-label">{t('btn.delete')}</span>
                  </div>
                </button>
              </>
            )}
            {selectedDoc?.docid && (
              <button
                className="icon-btn"
                type="button"
                onClick={() => navigate(`/master/doc-params?docid=${selectedDoc.docid}`)}
                title="매개변수 설정"
              >
                <div className="icon-wrapper">
                  <img src="/icons/config.svg" className="icon-img config-icon" alt="매개변수 설정" />
                  <span className="icon-label">{t('lbl.params.setting')}</span>
                </div>
              </button>
            )}
          </div>
        </div>

        {/* Right: 매개변수 */}
        <div style={{ flex: 2, paddingLeft: 20 }}>
          <h3>{t('ttl.params')}</h3>
          <div className="table-container" style={{ maxHeight: 200 }}>
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th>{t('thd.paramnm')}</th>
                  <th>{t('thd.samplevalue')}</th>
                  <th>{t('thd.operator')}</th>
                  <th>{t('thd.orderno')}</th>
                </tr>
              </thead>
              <tbody>
                {!selectedDoc ? (
                  <tr><td colSpan={4}>{t('msg.select.doc')}</td></tr>
                ) : params.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: 'center' }}>{t('msg.no.params')}</td></tr>
                ) : params.map((p) => (
                  <tr
                    key={p.paramuid}
                    className={selectedParam?.paramuid === p.paramuid ? 'selected-row' : ''}
                    style={{ cursor: 'pointer' }}
                    onClick={() => selectParam(p)}
                  >
                    <td>{p.paramnm}</td>
                    <td>{p.samplevalue || ''}</td>
                    <td>{p.operator || '='}</td>
                    <td>{p.orderno ?? ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Param form */}
          {selectedDoc && (
            <div style={{ paddingTop: 15 }}>
              <div className="form-group-left">
                <label htmlFor="param-paramnm">{t('lbl.paramnm')}</label>
                <input
                  id="param-paramnm"
                  type="text"
                  value={paramForm.paramnm}
                  onChange={(e) => setParamForm((f) => ({ ...f, paramnm: e.target.value }))}
                />
              </div>
              <div className="form-group-left">
                <label htmlFor="param-orderno">{t('lbl.orderno')}</label>
                <input
                  id="param-orderno"
                  type="number"
                  value={paramForm.orderno}
                  onChange={(e) => setParamForm((f) => ({ ...f, orderno: e.target.value }))}
                />
              </div>
              <div className="form-group-left">
                <label htmlFor="param-samplevalue">{t('lbl.samplevalue')}</label>
                <input
                  id="param-samplevalue"
                  type="text"
                  value={paramForm.samplevalue}
                  onChange={(e) => setParamForm((f) => ({ ...f, samplevalue: e.target.value }))}
                />
              </div>
              <div className="form-group-left">
                <label htmlFor="param-operator">Operator</label>
                <select
                  id="param-operator"
                  value={paramForm.operator}
                  onChange={(e) => setParamForm((f) => ({ ...f, operator: e.target.value }))}
                >
                  {OPERATORS.map((op) => <option key={op} value={op}>{op}</option>)}
                </select>
              </div>
              <div>
                <p style={{ fontSize: 12, color: '#888' }}>
                  ＊예시값은 기준정보 입력 화면에서 필요하기 때문에 반드시 입력해야 합니다.
                </p>
              </div>
              <div className="button-group">
                <button className="icon-btn" type="button" onClick={handleParamNew}>
                  <div className="icon-wrapper">
                    <img src="/icons/new.svg" className="icon-img new-icon" alt="신규" />
                    <span className="icon-label">{t('btn.new')}</span>
                  </div>
                </button>
                {(isEditYn || selectedDocEditYn) && (
                  <>
                    <button className="icon-btn" type="button" onClick={handleParamSave} disabled={saveParam.isPending}>
                      <div className="icon-wrapper">
                        <img src="/icons/save.svg" className="icon-img save-icon" alt="저장" />
                        <span className="icon-label">{t('btn.save')}</span>
                      </div>
                    </button>
                    <button className="icon-btn" type="button" onClick={handleParamDelete} disabled={deleteParam.isPending}>
                      <div className="icon-wrapper">
                        <img src="/icons/delete.svg" className="icon-img del-icon" alt="삭제" />
                        <span className="icon-label">{t('btn.delete')}</span>
                      </div>
                    </button>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
