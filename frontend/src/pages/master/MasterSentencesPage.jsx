/**
 * MasterSentencesPage — UI 문장 설정
 * Django master_sentences.html 구조 그대로 반영
 * 3열: 데이터 목록 | 데이터 미리보기 | 문장 미리보기(템플릿+결과)
 */
import { useEffect, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { App } from 'antd'
import apiClient from '@/api/client'
import { useChapterDatas } from '@/hooks/useDatas'
import { useSentence, useSaveSentence, useDeleteSentence } from '@/hooks/useSentences'

export default function MasterSentencesPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const chapteruid = searchParams.get('chapteruid') || ''
  const objectnm   = searchParams.get('objectnm')   || ''
  const objectuid  = searchParams.get('objectuid')  || ''
  const chapternm  = searchParams.get('chapternm')  || ''

  const { data: allDatas = [], isLoading: datasLoading } = useChapterDatas(chapteruid)
  const { data: sentenceData }   = useSentence(chapteruid, objectnm)
  const saveSentence    = useSaveSentence()
  const deleteSentence  = useDeleteSentence()

  const [selectedDatauid, setSelectedDatauid] = useState('')
  const [templateText,    setTemplateText]    = useState('')
  const [previewResult,   setPreviewResult]   = useState('')
  const [previewLoading,  setPreviewLoading]  = useState(false)

  // 데이터 미리보기 (15행)
  const [dataRows,        setDataRows]        = useState([])
  const [dataLoading,     setDataLoading]     = useState(false)

  // 기존 저장값 로드
  useEffect(() => {
    if (!sentenceData) return
    if (sentenceData.datauid)      setSelectedDatauid(sentenceData.datauid)
    if (sentenceData.sentencestext !== undefined) setTemplateText(sentenceData.sentencestext || '')
  }, [sentenceData])

  // 데이터 선택 → 15행 미리보기
  useEffect(() => {
    if (!selectedDatauid) { setDataRows([]); return }
    setDataLoading(true)
    apiClient.get('/datas/rows', { params: { datauid: selectedDatauid } })
      .then((r) => setDataRows(r.data.data || []))
      .catch(() => setDataRows([]))
      .finally(() => setDataLoading(false))
  }, [selectedDatauid])

  const handleDataSelect = (datauid) => {
    setSelectedDatauid(datauid)
    setPreviewResult('')
  }

  const handlePreview = async () => {
    if (!selectedDatauid || !templateText.trim()) {
      message.warning('데이터를 선택하고 템플릿을 입력해주세요.')
      return
    }
    setPreviewLoading(true)
    try {
      const resp = await apiClient.post('/sentences/preview', {
        chapteruid, objectnm,
        selected_datauid: selectedDatauid,
        template_text: templateText,
      })
      setPreviewResult(resp.data.result || '')
    } catch (e) {
      message.error('미리보기 실패: ' + (e.response?.data?.detail || e.message))
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleSave = () => {
    if (!selectedDatauid || !chapteruid || !objectnm || !objectuid) {
      message.warning('모든 항목을 선택해주세요.')
      return
    }
    saveSentence.mutate({ objectuid, chapteruid, objectnm, datauid: selectedDatauid, sentencestext: templateText })
  }

  const handleDelete = () => {
    if (!window.confirm('정말 삭제하시겠습니까?')) return
    deleteSentence.mutate({ chapteruid, objectnm })
    setTemplateText('')
    setPreviewResult('')
    setSelectedDatauid('')
    setDataRows([])
  }

  const handleReset = () => {
    setTemplateText('')
    setPreviewResult('')
  }

  const handleBack = () => {
    const ct = sessionStorage.getItem('chapter_template_chapteruid')
    const co = sessionStorage.getItem('chapter_objects_read_genchapteruid')
    if (ct) navigate(`/master/chapters?chapteruid=${ct}`)
    else if (co) navigate(`/req/chapter-objects?genchapteruid=${co}`)
    else if (chapteruid && objectuid) navigate(`/master/object?chapteruid=${chapteruid}&objectuid=${objectuid}`)
    else if (chapteruid) navigate(`/master/object?chapteruid=${chapteruid}`)
    else navigate('/master/object')
  }

  const dataColumns = dataRows.length > 0 ? Object.keys(dataRows[0]) : []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 200px)', overflow: 'hidden' }}>

      {/* 헤더 */}
      <div className="page-title" style={{ flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>문장관리 - {objectnm}{chapternm ? `(${chapternm})` : ''}</div>
        </div>
        <button type="button" className="icon-btn" onClick={handleBack}>
          <img src="/icons/back.svg" alt="뒤로가기" className="icon-img config-icon" />
        </button>
      </div>

      {/* 3열 */}
      <div style={{ flex: 1, display: 'flex', gap: 20, overflow: 'hidden', minHeight: 0, paddingRight: 10 }}>

        {/* 영역1: 데이터 목록 */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <h4 style={{ flexShrink: 0, marginBottom: 8 }}>데이터 목록</h4>
          <div className="chapter-card-container" style={{ flex: 1, overflowY: 'auto' }}>
            {datasLoading ? (
              <div style={{ fontSize: 12, color: '#aaa', padding: 8 }}>로딩 중...</div>
            ) : allDatas.length === 0 ? (
              <div style={{ fontSize: 12, color: '#aaa', padding: 8 }}>데이터가 없습니다.</div>
            ) : allDatas.map((d) => (
              <div
                key={d.datauid}
                className={`chapter-card${selectedDatauid === d.datauid ? ' selected' : ''}`}
                onClick={() => handleDataSelect(d.datauid)}
              >
                <div className="card-title">{d.datanm}</div>
              </div>
            ))}
          </div>
        </div>

        {/* 영역2: 데이터 미리보기 */}
        <div style={{ flex: 2, display: 'flex', flexDirection: 'column', minHeight: 0, paddingLeft: 10, paddingRight: 10 }}>
          <h4 style={{ flexShrink: 0, marginBottom: 4 }}>데이터 미리보기</h4>
          <p style={{ fontSize: 12, color: '#888', flexShrink: 0, marginBottom: 8 }}>* 미리보기 결과는 15개의 행만 보입니다.</p>
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {dataLoading ? (
              <div style={{ textAlign: 'center', padding: 20 }}>로딩 중...</div>
            ) : dataRows.length > 0 ? (
              <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
                <thead>
                  <tr>
                    {dataColumns.map((col) => (
                      <th key={col} style={{ border: '1px solid #ccc', padding: '4px 8px', backgroundColor: '#f0f0f0', whiteSpace: 'nowrap' }}>
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {dataRows.map((row, i) => (
                    <tr key={i}>
                      {dataColumns.map((col) => (
                        <td key={col} style={{ border: '1px solid #eee', padding: '3px 8px' }}>
                          {String(row[col] ?? '')}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p style={{ color: '#aaa' }}>데이터를 선택해주세요.</p>
            )}
          </div>
        </div>

        {/* 영역3: 문장 미리보기 */}
        <div style={{ flex: 1.5, display: 'flex', flexDirection: 'column', minHeight: 0, paddingLeft: 10 }}>
          <h4 style={{ flexShrink: 0, marginBottom: 8 }}>문장 미리보기</h4>

          {/* 템플릿 입력 */}
          <textarea
            value={templateText}
            onChange={(e) => setTemplateText(e.target.value)}
            rows={4}
            placeholder="예: {{제품명}} : {{함량/용량}}"
            style={{
              width: '100%', padding: 8, boxSizing: 'border-box',
              border: '1px solid #ccc', borderRadius: 4, fontSize: 13,
              resize: 'vertical', flexShrink: 0,
            }}
          />

          {/* 미리보기 버튼 */}
          <div className="button-group" style={{ flexShrink: 0, marginTop: 8, marginBottom: 8 }}>
            <button type="button" className="icon-btn" onClick={handlePreview} disabled={previewLoading}>
              <div className="icon-wrapper">
                <img src="/icons/view.svg" className="icon-img config-icon" alt="미리보기" />
                <span className="icon-label">미리보기</span>
              </div>
            </button>
          </div>

          {/* 변환 결과 */}
          <textarea
            value={previewResult}
            readOnly
            rows={10}
            style={{
              flex: 1, width: '100%', padding: 8, boxSizing: 'border-box',
              border: '1px solid #ccc', borderRadius: 4, fontSize: 13,
              backgroundColor: '#f8f9fa', resize: 'none',
            }}
          />

          {/* 저장/삭제 버튼 */}
          <div className="button-group" style={{ flexShrink: 0, marginTop: 8 }}>
            <button type="button" className="icon-btn" onClick={handleReset}>
              <div className="icon-wrapper">
                <img src="/icons/new.svg" className="icon-img new-icon" alt="신규" />
                <span className="icon-label">신규</span>
              </div>
            </button>
            <button type="button" className="icon-btn" onClick={handleSave} disabled={saveSentence.isPending}>
              <div className="icon-wrapper">
                <img src="/icons/save.svg" className="icon-img save-icon" alt="저장" />
                <span className="icon-label">저장</span>
              </div>
            </button>
            <button type="button" className="icon-btn" onClick={handleDelete} disabled={deleteSentence.isPending}>
              <div className="icon-wrapper">
                <img src="/icons/delete.svg" className="icon-img del-icon" alt="삭제" />
                <span className="icon-label">삭제</span>
              </div>
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}
