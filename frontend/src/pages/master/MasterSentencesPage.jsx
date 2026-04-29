/**
 * MasterSentencesPage — UI 문장 설정
 * Django master_sentences.html 구조 그대로 반영
 * 3열: 데이터 목록 | 데이터 미리보기 | 문장 미리보기(템플릿+결과)
 */
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { App } from 'antd'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useChapterDatas } from '@/hooks/useDatas'
import { useSentence, useSaveSentence, useDeleteSentence } from '@/hooks/useSentences'
import { useObjectFilterDatauid } from '@/hooks/useTables'

export default function MasterSentencesPage() {
  useLangStore((s) => s.translations)
  const { message } = App.useApp()
  const [searchParams] = useSearchParams()
  const chapteruid = searchParams.get('chapteruid') || ''
  const objectnm   = searchParams.get('objectnm')   || ''
  const objectuid  = searchParams.get('objectuid')  || ''
  const chapternm  = searchParams.get('chapternm')  || ''
  const user     = useAuthStore((s) => s.user)
  const docnm    = user?.docnm
  const isEditYn = user?.editbuttonyn === 'Y'

  const { data: allDatas = [], isLoading: datasLoading } = useChapterDatas(chapteruid)
  const { data: sentenceData, isSuccess: sentenceSuccess } = useSentence(chapteruid, objectnm)
  const saveSentence   = useSaveSentence()
  const deleteSentence = useDeleteSentence()

  const { data: filterDatauid } = useObjectFilterDatauid(objectuid, sentenceSuccess && sentenceData === null)

  const [selectedDatauid, setSelectedDatauid] = useState('')
  const [isFilterDefault,  setIsFilterDefault] = useState(false)
  const [templateText,     setTemplateText]    = useState('')
  const [previewResult,    setPreviewResult]   = useState('')
  const [previewLoading,   setPreviewLoading]  = useState(false)

  // 데이터 미리보기
  const [dataRows,    setDataRows]    = useState([])
  const [dataLoading, setDataLoading] = useState(false)

  // 기존 저장값 로드
  useEffect(() => {
    if (!sentenceData) return
    if (sentenceData.datauid) setSelectedDatauid(sentenceData.datauid)
    if (sentenceData.sentencestext !== undefined) setTemplateText(sentenceData.sentencestext || '')
  }, [sentenceData])

  // objectfilters 기본 데이터 적용
  useEffect(() => {
    if (!filterDatauid) return
    setSelectedDatauid(filterDatauid)
    setIsFilterDefault(true)
  }, [filterDatauid])

  // 데이터 선택 → 미리보기 행 로드
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
      message.warning(t('msg.sentence.preview.required'))
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
      message.error(t('msg.preview.error') + ': ' + (e.response?.data?.detail || e.message))
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleSave = () => {
    if (!selectedDatauid || !chapteruid || !objectnm || !objectuid) {
      message.warning(t('msg.select.data'))
      return
    }
    saveSentence.mutate(
      { objectuid, chapteruid, objectnm, datauid: selectedDatauid, sentencestext: templateText },
      {
        onSuccess: () => message.success(t('msg.save.success')),
        onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
      }
    )
  }

  const handleDelete = () => {
    if (!window.confirm(t('msg.confirm.delete'))) return
    deleteSentence.mutate(
      { chapteruid, objectnm },
      {
        onSuccess: () => {
          message.success(t('msg.delete.success'))
          setTemplateText('')
          setPreviewResult('')
          setSelectedDatauid('')
          setDataRows([])
        },
        onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
      }
    )
  }

  const handleReset = () => {
    setTemplateText('')
    setPreviewResult('')
  }

  const dataColumns = dataRows.length > 0 ? Object.keys(dataRows[0]) : []

  return (
    <div>

      {/* 헤더 */}
      <div className="page-title" style={{ marginBottom: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.sentence.manage')}{docnm ? ` - ${docnm}` : ''}</div>
        </div>
      </div>
      <div style={{ marginBottom: 16, paddingLeft: 16, fontSize: 15, fontWeight: 500, color: 'var(--gray-700)' }}>
        {chapternm && <span>{t('lbl.chapternm')}: {chapternm}</span>}
        {chapternm && objectnm && <span style={{ margin: '0 14px', color: '#d9d9d9' }}>|</span>}
        {objectnm && <span>{t('lbl.objectnm_lbl')}: {objectnm}</span>}
      </div>
      {isFilterDefault && (
        <div style={{ marginBottom: 12, padding: '8px 14px', background: '#fff7e6', border: '1px solid #ffd591', borderRadius: 6, color: '#d46b08', fontSize: 13 }}>
          {t('msg.dataset.filter.readonly')}
        </div>
      )}

      {/* 3열 */}
      <div style={{ display: 'flex', gap: 20, paddingRight: 10 }}>

        {/* 영역1: 데이터 목록 */}
        <div style={{ flex: 2 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.data.list')}</h3>
            <div />
          </div>
          <div className="chapter-card-container" style={{ overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
            {datasLoading ? (
              <div style={{ fontSize: 12, color: '#aaa', padding: 8 }}>{t('msg.loading')}</div>
            ) : allDatas.length === 0 ? (
              <div style={{ fontSize: 12, color: '#aaa', padding: 8 }}>{t('msg.no.data')}</div>
            ) : allDatas.map((d) => (
              <div
                key={d.datauid}
                className={`chapter-card${selectedDatauid === d.datauid ? ' selected' : ''}`}
                onClick={() => { if (!isFilterDefault) handleDataSelect(d.datauid) }}
                style={isFilterDefault ? { cursor: 'not-allowed', opacity: 0.6 } : {}}
              >
                <div className="card-title">{d.datanm}</div>
              </div>
            ))}
          </div>
        </div>

        {/* 영역2: 데이터 미리보기 */}
        <div style={{ flex: 5, paddingLeft: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.data.preview')}</h3>
            <div />
          </div>
          <p style={{ fontSize: 12, color: '#888', marginBottom: 8 }}>* {t('inf.preview.rows')}</p>
          <div style={{ overflowY: 'auto', maxHeight: 'calc(100vh - 260px)' }}>
            {dataLoading ? (
              <div style={{ textAlign: 'center', padding: 20 }}>{t('msg.loading')}</div>
            ) : dataRows.length > 0 ? (
              <table style={{ fontSize: 12, tableLayout: 'auto' }}>
                <thead>
                  <tr>
                    {dataColumns.map((col) => (
                      <th key={col} style={{ whiteSpace: 'nowrap' }}>{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {dataRows.map((row, i) => (
                    <tr key={i}>
                      {dataColumns.map((col) => (
                        <td key={col}>{String(row[col] ?? '')}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p style={{ color: '#aaa', fontSize: 12, padding: 8 }}>{t('inf.preview.empty')}</p>
            )}
          </div>
        </div>

        {/* 영역3: 문장 미리보기 */}
        <div style={{ flex: 4, paddingLeft: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.preview_ttl')}</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="button" className="btn btn-primary" onClick={handleReset}>{t('btn.new')}</button>
              {isEditYn && (
                <>
                  <button type="button" className="btn btn-primary" onClick={handleSave} disabled={saveSentence.isPending}>{t('btn.save')}</button>
                  <button type="button" className="btn btn-danger" onClick={handleDelete} disabled={deleteSentence.isPending}>{t('btn.delete')}</button>
                </>
              )}
              <button type="button" className="btn btn-primary" onClick={handlePreview} disabled={previewLoading}>{t('btn.preview_btn')}</button>
            </div>
          </div>
          <div style={{ overflowY: 'auto', maxHeight: 'calc(100vh - 224px)' }}>
            <textarea
              value={templateText}
              onChange={(e) => setTemplateText(e.target.value)}
              rows={4}
              placeholder={t('msg.ph.sentence.template')}
              style={{
                width: '100%', padding: 8, boxSizing: 'border-box',
                border: '1px solid #ccc', borderRadius: 4, fontSize: 13,
                resize: 'vertical', marginBottom: 8,
              }}
            />
            <textarea
              value={previewResult}
              readOnly
              rows={12}
              style={{
                width: '100%', padding: 8, boxSizing: 'border-box',
                border: '1px solid #ccc', borderRadius: 4, fontSize: 13,
                backgroundColor: '#f8f9fa', resize: 'vertical',
              }}
            />
          </div>
        </div>

      </div>
    </div>
  )
}
