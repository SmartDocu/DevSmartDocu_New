import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { App } from 'antd'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'

function useChapterObjects(genchapteruid) {
  return useQuery({
    queryKey: ['chapter-objects', genchapteruid],
    queryFn: () => apiClient.get(`/gendocs/genchapters/${genchapteruid}/objects`).then((r) => r.data),
    enabled: !!genchapteruid,
  })
}

function useRewriteObject(genchapteruid) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (objectuid) =>
      apiClient.post(`/gendocs/genchapters/${genchapteruid}/objects/${objectuid}/rewrite`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['chapter-objects', genchapteruid] })
    },
  })
}

function useApplyObjects(genchapteruid) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiClient.post(`/gendocs/genchapters/${genchapteruid}/apply`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['chapter-objects', genchapteruid] })
    },
  })
}

const OBJECT_TYPE_SETTING_MAP = {
  TU: (docid, chapteruid, objectnm) =>
    `/master/tables?docid=${docid}&chapteruid=${chapteruid}&objectnm=${encodeURIComponent(objectnm)}`,
  CU: (docid, chapteruid, objectnm) =>
    `/master/charts?docid=${docid}&chapteruid=${chapteruid}&objectnm=${encodeURIComponent(objectnm)}`,
  SU: (docid, chapteruid, objectnm) =>
    `/master/sentences?docid=${docid}&chapteruid=${chapteruid}&objectnm=${encodeURIComponent(objectnm)}`,
  TA: (docid, chapteruid, objectnm) =>
    `/master/ai-tables?chapteruid=${chapteruid}&objectnm=${encodeURIComponent(objectnm)}`,
  CA: (docid, chapteruid, objectnm) =>
    `/master/ai-charts?chapteruid=${chapteruid}&objectnm=${encodeURIComponent(objectnm)}`,
  SA: (docid, chapteruid, objectnm) =>
    `/master/ai-sentences?chapteruid=${chapteruid}&objectnm=${encodeURIComponent(objectnm)}`,
}

export default function ReqChapterObjectsPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { message } = App.useApp()
  const { user } = useAuthStore()
  const genchapteruid = searchParams.get('genchapteruid')

  const { data = {}, isLoading } = useChapterObjects(genchapteruid)
  const rewriteMutation = useRewriteObject(genchapteruid)
  const applyMutation = useApplyObjects(genchapteruid)

  const [selectedRow, setSelectedRow] = useState(null)
  const [loadingText, setLoadingText] = useState('')
  const [showLoading, setShowLoading] = useState(false)

  const {
    objects = [],
    chapternm = '',
    gendocnm = '',
    gendocuid,
    docid,
    chapteruid,
    closeyn = false,
  } = data

  const editbuttonyn = user?.editbuttonyn === 'Y'
  const roleid = user?.roleid

  const handleBack = () => {
    if (gendocuid) navigate(`/req/chapters-read?gendocs=${gendocuid}`)
    else navigate('/req/list')
  }

  const handleObjectSetting = (row) => {
    const fn = OBJECT_TYPE_SETTING_MAP[row.objecttypecd]
    if (fn) {
      navigate(fn(docid, row.chapteruid || chapteruid, row.objectnm))
    }
  }

  const handleRewrite = async (row) => {
    setLoadingText('항목 작성 중')
    setShowLoading(true)
    try {
      await rewriteMutation.mutateAsync(row.objectuid)
      alert('항목 작성이 완료 되었습니다.')
      // refresh selected row from new data
      setSelectedRow((prev) => prev)
    } catch (err) {
      alert('오류 발생: ' + (err.response?.data?.detail || err.message))
    } finally {
      setShowLoading(false)
      setLoadingText('')
    }
  }

  const handleApply = async () => {
    if (!window.confirm('생성된 항목들을 챕터에 반영하시겠습니까?')) return
    setLoadingText('항목 반영 중')
    setShowLoading(true)
    try {
      await applyMutation.mutateAsync()
      alert('항목 반영이 완료 되었습니다.')
    } catch (err) {
      alert('오류 발생: ' + (err.response?.data?.detail || err.message))
    } finally {
      setShowLoading(false)
      setLoadingText('')
    }
  }

  return (
    <div>
      {/* 페이지 타이틀 */}
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>챕터 항목 조회: {chapternm}</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <button type="button" className="icon-btn">
            <img src="/icons/help.svg" title="도움말" className="icon-img config-icon" alt="도움말" />
          </button>
          <button type="button" className="icon-btn" onClick={handleBack}>
            <img src="/icons/back.svg" title="뒤로가기" className="icon-img config-icon" alt="뒤로가기" />
          </button>
        </div>
      </div>

      {/* 메타 정보 */}
      {data.createfiledts !== undefined && (
        <div className="form-filter-group">
          <div className="filter-item">
            <label style={{ width: 120 }}>챕터 작성 일시: </label>
            <label style={{ width: 200 }}>{data.createfiledts || ''}</label>
          </div>
        </div>
      )}

      {/* 본문 */}
      <div style={{ display: 'flex', gap: 20, minHeight: '78%' }}>
        {/* 좌측: 항목 목록 */}
        <div style={{ flex: 1.5 }}>
          {isLoading ? (
            <div className="loading-content" style={{ position: 'relative', minHeight: 120 }}>
              <div className="spinner" />
              <div>불러오는 중...</div>
            </div>
          ) : (
            <div className="table-container">
              <table className="table table-bordered table-sm">
                <thead>
                  <tr>
                    <th style={{ width: '18%' }}>항목명</th>
                    <th style={{ width: '16%' }}>항목<br />설명</th>
                    <th style={{ width: '8%' }}>항목<br />구분</th>
                    <th style={{ width: '18%' }}>필터</th>
                    <th style={{ width: '10%' }}>설정<br />일시</th>
                    <th style={{ width: '8%' }}>설정<br />미반영</th>
                    <th style={{ width: '12%' }}>작성<br />일시</th>
                    <th style={{ width: '10%' }}>항목<br />미반영</th>
                  </tr>
                </thead>
                <tbody>
                  {objects.map((obj) => (
                    <tr
                      key={obj.objectuid || obj.objectnm}
                      className={selectedRow?.objectuid === obj.objectuid ? 'selected-row' : ''}
                      onClick={() => setSelectedRow(obj)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td>{obj.objectnm}</td>
                      <td className="multiline">
                        <span className="cell-center" style={{ whiteSpace: 'pre-line' }}>
                          {obj.objectdesc || ''}
                        </span>
                      </td>
                      <td className="info">{obj.objecttypenm}</td>
                      <td className="info" style={{ whiteSpace: 'pre-line' }}>
                        {(() => {
                          if (!obj.filterjson) return ''
                          try {
                            const parsed = typeof obj.filterjson === 'string' ? JSON.parse(obj.filterjson) : obj.filterjson
                            return Object.entries(parsed).map(([k, v]) => `${k}: ${v}`).join('\n')
                          } catch { return String(obj.filterjson) }
                        })()}
                      </td>
                      <td className="info">{obj.objcreatedts || ''}</td>
                      <td className="info">{obj.new_objectyn ? '√' : ''}</td>
                      <td className="info">{obj.genobjcreatedts || ''}</td>
                      <td className="info">{obj.new_genobjectyn ? '√' : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* 우측: 선택된 항목 내용 */}
        <div style={{ flex: 1 }}>
          <div id="htmlcode">
            {selectedRow && (
              <>
                {/* 버튼 영역 */}
                <div className="form-group-left" style={{ marginBottom: 10, justifyContent: 'center', gap: 20 }}>
                  {editbuttonyn && (
                    <button
                      type="button"
                      className="icon-btn"
                      disabled={closeyn || rewriteMutation.isPending}
                      onClick={() => handleRewrite(selectedRow)}
                    >
                      <div className="icon-wrapper">
                        <img src="/icons/object-write.svg" className="icon-img config-icon" alt="항목 (재)작성" />
                        <span className="icon-label">항목 (재)작성</span>
                      </div>
                    </button>
                  )}
                  {(roleid === 7) && (
                    <button
                      type="button"
                      className="icon-btn"
                      onClick={() => handleObjectSetting(selectedRow)}
                    >
                      <div className="icon-wrapper">
                        <img src="/icons/configuration.svg" className="icon-img config-icon" alt="항목 설정" />
                        <span className="icon-label">항목 설정</span>
                      </div>
                    </button>
                  )}
                </div>

                {/* 항목 내용 */}
                <div className="contents" style={{ whiteSpace: 'pre-line' }}>
                  {selectedRow.resulttext && selectedRow.resulttext !== 'None' ? (
                    <div dangerouslySetInnerHTML={{ __html: selectedRow.resulttext }} />
                  ) : (
                    <div>만들어진 항목이 없습니다.</div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* 하단: 항목 반영 버튼 */}
      {editbuttonyn && (
        <div style={{ marginTop: 10, textAlign: 'center' }}>
          <button
            type="button"
            className="icon-btn"
            disabled={closeyn || applyMutation.isPending}
            onClick={handleApply}
          >
            <div className="icon-wrapper">
              <img src="/icons/chapter-write.svg" className="icon-img config-icon" alt="항목 반영" />
              <span className="icon-label">항목 반영</span>
            </div>
          </button>
        </div>
      )}

      {/* 로딩 오버레이 */}
      {showLoading && (
        <div id="formatLoading" style={{ display: 'flex' }}>
          <div className="loading-content">
            <div className="spinner" />
            <div style={{ textAlign: 'center' }}>{loadingText}</div>
            <div>잠시만 기다려 주세요.</div>
          </div>
        </div>
      )}
    </div>
  )
}
