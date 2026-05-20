import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Spin } from 'antd'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useOpenInTab } from '@/hooks/useOpenInTab'

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

const TYPE_TAB_LABEL_KEY = {
  TU: 'ttl.table.manage',
  CU: 'ttl.chart.manage',
  SU: 'ttl.sentence.manage',
  TA: 'ttl.ai.table.manage',
  CA: 'ttl.ai.chart.manage',
  SA: 'ttl.ai.sentence.manage',
}

export default function ReqChapterObjectsPage() {
  useLangStore((s) => s.translations)

  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
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
    gendocuid,
    docid,
    chapteruid,
    closeyn = false,
  } = data

  const openInTab = useOpenInTab()

  const editbuttonyn = user?.editbuttonyn === 'Y'
  const roleid = user?.roleid

  const handleBack = () => {
    if (gendocuid) navigate(`/req/chapters-read?gendocs=${gendocuid}`)
    else navigate('/req/list')
  }

  const handleObjectSetting = (row) => {
    const fn = OBJECT_TYPE_SETTING_MAP[row.objecttypecd]
    if (fn) {
      const fullPath = fn(docid, row.chapteruid || chapteruid, row.objectnm)
      const withoutSlash = fullPath.replace(/^\//, '')
      const sepIdx = withoutSlash.indexOf('?')
      const routePath = sepIdx >= 0 ? withoutSlash.slice(0, sepIdx) : withoutSlash
      const query = sepIdx >= 0 ? withoutSlash.slice(sepIdx) : undefined
      const tabLabel = TYPE_TAB_LABEL_KEY[row.objecttypecd] ? t(TYPE_TAB_LABEL_KEY[row.objecttypecd]) : row.objectnm
      openInTab(routePath, query, tabLabel)
    }
  }

  const handleRewrite = async (row) => {
    setLoadingText(t('msg.loading.object.writing'))
    setShowLoading(true)
    try {
      await rewriteMutation.mutateAsync(row.objectuid)
      alert(t('msg.object.write.complete'))
      setSelectedRow((prev) => prev)
    } catch (err) {
      alert(t('msg.server.error') + ': ' + (err.response?.data?.detail || err.message))
    } finally {
      setShowLoading(false)
      setLoadingText('')
    }
  }

  const handleApply = async () => {
    if (!window.confirm(t('msg.confirm.object.apply'))) return
    setLoadingText(t('msg.loading.object.applying'))
    setShowLoading(true)
    try {
      await applyMutation.mutateAsync()
      alert(t('msg.object.apply.complete'))
    } catch (err) {
      alert(t('msg.server.error') + ': ' + (err.response?.data?.detail || err.message))
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
          <div>{t('ttl.chapter.objects')}: {chapternm}</div>
        </div>
        <button type="button" className="btn btn-back" onClick={handleBack}>
          {t('btn.back')}
        </button>
      </div>

      {/* 메타 정보 */}
      {data.createfiledts !== undefined && (
        <div className="form-filter-group">
          <div className="filter-item">
            <label style={{ width: 160 }}>{t('lbl.chapter.create.dts')}: </label>
            <label style={{ width: 200 }}>{data.createfiledts || ''}</label>
          </div>
        </div>
      )}

      {/* 본문 */}
      <div style={{ display: 'flex', gap: 20 }}>

        {/* 좌측: 항목 목록 */}
        <div style={{ flex: 1.5, overflowY: 'auto', maxHeight: 'calc(100vh - 264px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.chapter.objects')}</h3>
            <div />
          </div>
          {isLoading ? (
            <div style={{ padding: 20, textAlign: 'center' }}>{t('msg.loading')}</div>
          ) : (
            <table className="table table-bordered table-sm">
              <thead>
                <tr>
                  <th style={{ width: '18%' }}>{t('thd.objectnm_thd')}</th>
                  <th style={{ width: '16%' }}>{t('thd.objectdesc_thd')}</th>
                  <th style={{ width: '8%' }}>{t('thd.objecttypecd_thd')}</th>
                  <th style={{ width: '18%' }}>{t('thd.filterjson')}</th>
                  <th style={{ width: '10%' }}>{t('thd.obj.setting.dts')}</th>
                  <th style={{ width: '8%' }}>{t('thd.new.object.yn')}</th>
                  <th style={{ width: '12%' }}>{t('thd.obj.write.dts')}</th>
                  <th style={{ width: '10%' }}>{t('thd.new.genobject.yn')}</th>
                </tr>
              </thead>
              <tbody>
                {objects.map((obj) => (
                  <tr
                    key={obj.genobjectuid || obj.objectuid || obj.objectnm}
                    className={selectedRow?.genobjectuid === obj.genobjectuid ? 'selected-row' : ''}
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
          )}
        </div>

        {/* 우측: 항목 내용 */}
        <div style={{ flex: 1, overflowY: 'auto', maxHeight: 'calc(100vh - 264px)' }}>
          {/* 소제목 행 + 버튼 */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.object.detail')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {selectedRow && roleid === 7 && (
                <>
                  <button type="button" className="btn btn-primary" onClick={() => handleObjectSetting(selectedRow)}>
                    {t('btn.objectconfig')}
                  </button>
                  <span style={{ color: '#d9d9d9', margin: '0 12px' }}>|</span>
                </>
              )}
              {editbuttonyn && selectedRow && (
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={closeyn || rewriteMutation.isPending}
                  onClick={() => handleRewrite(selectedRow)}
                >
                  {t('btn.object.rewrite')}
                </button>
              )}
              {editbuttonyn && (
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={closeyn || applyMutation.isPending}
                  onClick={handleApply}
                >
                  {t('btn.object.apply')}
                </button>
              )}
            </div>
          </div>

          {/* 항목 내용 */}
          {selectedRow && (
            <div className="contents" style={{ whiteSpace: 'pre-line' }}>
              {selectedRow.resulttext && selectedRow.resulttext !== 'None' ? (
                <div dangerouslySetInnerHTML={{ __html: selectedRow.resulttext }} />
              ) : (
                <div>{t('msg.object.empty')}</div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 로딩 오버레이 */}
      {showLoading && (
        <div style={{
          position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
          background: 'rgba(0,0,0,0.5)',
          display: 'flex', justifyContent: 'center', alignItems: 'center',
          zIndex: 9999,
        }}>
          <div style={{
            background: '#fafae5', padding: '20px 30px', borderRadius: 8,
            fontSize: 16, fontWeight: 'bold', color: '#6c757d',
            boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
            display: 'flex', alignItems: 'center', gap: 12,
          }}>
            <Spin />
            <span>{loadingText || t('msg.loading.wait')}</span>
          </div>
        </div>
      )}
    </div>
  )
}
