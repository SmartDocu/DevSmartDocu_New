import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useChapters, useSaveChapter, useDeleteChapter } from '@/hooks/useChapters'
import { useAuthStore } from '@/stores/authStore'

export default function MasterChaptersPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const user = useAuthStore((s) => s.user)

  const selectedDocid = user?.docid ? Number(user.docid) : null
  const { data: chapters = [] } = useChapters(selectedDocid)
  const saveChapter = useSaveChapter()
  const deleteChapter = useDeleteChapter()

  const [selectedChap, setSelectedChap] = useState(null)
  const [form, setForm] = useState({ chapternm: '', chapterno: '', useyn: true })
  const [templateFile, setTemplateFile] = useState(null)
  const [templateName, setTemplateName] = useState('적용할 서식 파일 없음')
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
    setTemplateName(ch.chaptertemplatenm || '적용할 서식 파일 없음')
    setTemplateFile(null)
  }

  const handleNew = () => {
    setSelectedChap(null)
    setForm({ chapternm: '', chapterno: '', useyn: true })
    setTemplateName('적용할 서식 파일 없음')
    setTemplateFile(null)
  }

  const handleSave = () => {
    if (!form.chapterno) { alert('순번을 입력해주세요.'); return }
    if (!selectedDocid) { alert('문서를 선택해주세요.'); return }
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
    if (!selectedChap) { alert('삭제할 챕터를 선택하세요.'); return }
    if (!window.confirm('정말 삭제하시겠습니까?')) return
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
          <div>챕터 관리</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 30, paddingRight: 10 }}>
        {/* Left: chapter cards */}
        <div style={{ flex: '30%', paddingRight: 20 }}>
          <h3>챕터 목록</h3>
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

        {/* Middle: chapter detail */}
        <div style={{ flex: '50%', padding: '0 20px' }}>
          <h3>챕터 상세</h3>
          <div className="form-group">
            <label>챕터명:</label>
            <input
              type="text"
              value={form.chapternm}
              onChange={(e) => setForm((f) => ({ ...f, chapternm: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label>순번:</label>
            <input
              type="number"
              value={form.chapterno}
              onChange={(e) => setForm((f) => ({ ...f, chapterno: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label>사용:</label>
            <input
              type="checkbox"
              checked={!!form.useyn}
              onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))}
            />
          </div>
          <div className="form-group">
            <label>서식 파일 업로드(머리글, 바닥글):</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <button
                type="button"
                className="icon-btn"
                onClick={() => document.getElementById('chap-template-input').click()}
              >
                <img src="/icons/upload.svg" title="업로드" className="icon-img new-icon" alt="업로드" />
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
                      a.href = url; a.download = templateName
                      document.body.appendChild(a); a.click()
                      document.body.removeChild(a); URL.revokeObjectURL(url)
                    } catch { window.open(selectedChap.chaptertemplateurl, '_blank') }
                  }}
                >
                  {templateName}
                </a>
              ) : (
                <span>{templateName}</span>
              )}
            </div>
          </div>

          {/* Buttons */}
          <div className="form-group-left" style={{ justifyContent: 'center', marginBottom: 10, gap: 20 }}>
            {isEditYn && (
              <div className="button-group">
                <button className="icon-btn" type="button" onClick={handleNew}>
                  <div className="icon-wrapper">
                    <img src="/icons/new.svg" className="icon-img new-icon" alt="신규" />
                    <span className="icon-label">신규</span>
                  </div>
                </button>
                <button className="icon-btn" type="button" onClick={handleSave} disabled={saving}>
                  <div className="icon-wrapper">
                    <img src="/icons/save.svg" className="icon-img save-icon" alt="저장" />
                    <span className="icon-label">저장</span>
                  </div>
                </button>
                <button className="icon-btn" type="button" onClick={handleDelete}>
                  <div className="icon-wrapper">
                    <img src="/icons/delete.svg" className="icon-img del-icon" alt="삭제" />
                    <span className="icon-label">삭제</span>
                  </div>
                </button>
              </div>
            )}

            {/* Nav buttons - visible when chapter selected */}
            {selectedChap && (
              <div className="button-group">
                <button
                  className="icon-btn"
                  type="button"
                  onClick={() => {
                    sessionStorage.setItem('chapter_object_chapteruid', selectedChap.chapteruid)
                    navigate(`/master/object?chapteruid=${selectedChap.chapteruid}&docid=${selectedDocid}`)
                  }}
                >
                  <div className="icon-wrapper">
                    <img src="/icons/object-config.svg" className="icon-img config-icon" alt="항목 관리" />
                    <span className="icon-label">항목 관리</span>
                  </div>
                </button>
                <button
                  className="icon-btn"
                  type="button"
                  onClick={() => navigate(`/master/chapter-template?chapteruid=${selectedChap.chapteruid}&docid=${selectedDocid}`)}
                  title="양식 편집"
                >
                  <div className="icon-wrapper">
                    <img src="/icons/edit.svg" className="icon-img config-icon" alt="양식 편집" />
                    <span className="icon-label">양식 편집</span>
                  </div>
                </button>
              </div>
            )}
          </div>
        </div>

        <div style={{ flex: '20%', paddingLeft: 20 }} />
      </div>
    </div>
  )
}
