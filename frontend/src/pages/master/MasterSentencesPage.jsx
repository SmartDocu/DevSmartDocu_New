/**
 * MasterSentencesPage — UI 문장 설정
 * Django master_sentences.html 구조 그대로 반영
 * 3열: 데이터 목록 | 데이터 미리보기 | 문장 미리보기(템플릿+결과)
 */
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { App } from 'antd'
import { EyeOutlined, RedoOutlined, SaveOutlined, DeleteOutlined } from '@ant-design/icons'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useChapterDatas } from '@/hooks/useDatas'
import { useSentence, useSaveSentence, useDeleteSentence } from '@/hooks/useSentences'
import { useObjectFilterDatauid } from '@/hooks/useTables'
import { getErrorDetail } from '@/utils/apiError'

export default function MasterSentencesPage() {
  useLangStore((s) => s.translations)
  const { message, modal } = App.useApp()
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

  const { data: filterDatauid } = useObjectFilterDatauid(objectuid, sentenceSuccess)

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
    apiClient.get('/datas/rows', { params: { datauid: selectedDatauid, docid: user?.docid || undefined } })
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
        docid: user?.docid || null,
        template_text: templateText,
      })
      setPreviewResult(resp.data.result || '')
    } catch (e) {
      message.error(t('msg.preview.error') + ': ' + (getErrorDetail(e) || e.message))
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
        onSuccess: () => { message.success(t('msg.save.success')) },
        onError: (err) => {
          const detail = err.response?.data?.detail
          message.error((typeof detail === 'string' && t(detail)) || t('msg.save.error'))
        },
      }
    )
  }

  const handleDelete = () => {
    modal.confirm({
      content: t('msg.confirm.delete'),
      onOk: () => {
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
            onError: (err) => {
              const detail = err.response?.data?.detail
              message.error((typeof detail === 'string' && t(detail)) || t('msg.delete.error'))
            },
          }
        )
      },
    })
  }

  const handleReset = () => {
    setTemplateText('')
    setPreviewResult('')
  }

  const dataColumns = dataRows.length > 0 ? Object.keys(dataRows[0]) : []

  return (
    <div>

      {/* 헤더 */}
      <div className="page-title" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('ttl.sentence.manage')}{docnm ? ` - ${docnm}` : ''}</div>
        </div>
      </div>

      {/* 챕터/항목 정보 */}
      <div className="panel-section" style={{ display: 'flex', alignItems: 'center', fontSize: 13, marginBottom: 16 }}>
        <span style={{ color: '#888', flexShrink: 0 }}>{t('thd.chapternm')}: </span>
        <span style={{ flexShrink: 0 }}>{chapternm || '-'}</span>
        <span style={{ margin: '0 10px', color: '#d9d9d9', flexShrink: 0 }}>|</span>
        <span style={{ color: '#888', flexShrink: 0 }}>{t('lbl.objectnm_lbl')}: </span>
        <span style={{ flexShrink: 0 }}>{objectnm || '-'}</span>
      </div>

      {isFilterDefault && (
        <div className="panel-section" style={{ marginBottom: 16, background: '#fff7e6', border: '1px solid #ffd591', color: '#d46b08', fontSize: 13, padding: '13px 18px' }}>
          {t('msg.dataset.filter.readonly')}
        </div>
      )}

      {/* 3열 */}
      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>

        {/* 영역1: 데이터 목록 */}
        <div className="panel-section" style={{ flex: 2, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 264px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h3 style={{ margin: 0, lineHeight: 1 }}>{t('ttl.data.list')}</h3>
              <span style={{
                display: 'inline-flex', alignItems: 'center', lineHeight: 1,
                font: '500 11px monospace', color: '#8d9199', background: '#f2efe9',
                borderRadius: 6, padding: '5px 8px 4px',
              }}>
                {t('lbl.count.docs').replace('{n}', allDatas.length)}
              </span>
            </div>
            <div />
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          <div className="chapter-card-container" style={{ flexDirection: 'column' }}>
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
        </div>

        {/* 영역2: 데이터 미리보기 */}
        <div className="panel-section" style={{ flex: 5, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 264px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.data.preview')}</h3>
            <div />
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          <p style={{ fontSize: 12, color: '#888', marginBottom: 8 }}>* {t('inf.preview.rows')}</p>
          <div>
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
        </div>

        {/* 영역3: 문장 미리보기 */}
        <div className="panel-section" style={{ flex: 4, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 264px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.preview_ttl')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button type="button" className="btn btn-secondary" onClick={handlePreview} disabled={previewLoading}>
                <EyeOutlined style={{ marginRight: 6 }} />{t('btn.preview_btn')}
              </button>
              <button type="button" className="btn btn-secondary" onClick={handleReset}>
                <RedoOutlined style={{ marginRight: 6 }} />{t('btn.new')}
              </button>
              {isEditYn && (
                <>
                  <span style={{ color: '#d9d9d9' }}>|</span>
                  <button type="button" className="btn btn-primary" onClick={handleSave} disabled={saveSentence.isPending || deleteSentence.isPending}>
                    <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger"
                    onClick={handleDelete}
                    disabled={deleteSentence.isPending}
                    title={t('btn.delete')}
                    style={{ width: 38, height: 38, padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                  >
                    <DeleteOutlined />
                  </button>
                </>
              )}
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
          <div>
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
    </div>
  )
}
