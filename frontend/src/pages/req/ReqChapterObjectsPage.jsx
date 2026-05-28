import { useState, useEffect } from 'react'
import { App, Select, Spin } from 'antd'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useReqStore } from '@/stores/reqStore'
import { useGendocs, useGenchapters } from '@/hooks/useGendocs'

const TODAY = dayjs().format('YYYY-MM-DD')
const ONE_YEAR_AGO = dayjs().subtract(365, 'day').format('YYYY-MM-DD')

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

export default function ReqChapterObjectsPage() {
  useLangStore((s) => s.translations)

  const { user } = useAuthStore()
  const editbuttonyn = user?.editbuttonyn === 'Y'

  const { activeGendocuid, activeGenchapteruid } = useReqStore()

  // gendoc 목록
  const { data: gendocsData = {} } = useGendocs(ONE_YEAR_AGO, TODAY, user?.docid)
  const gendocs = gendocsData.gendocs || []

  // 선택된 gendocuid — mount 시점의 activeGendocuid로 초기화
  const [selectedGendocuid, setSelectedGendocuid] = useState(activeGendocuid)

  // gendocs 로드 후 선택값 없으면 첫 항목 자동 선택
  useEffect(() => {
    if (!gendocs.length || selectedGendocuid) return
    setSelectedGendocuid(gendocs[0]?.gendocuid)
  }, [gendocs.length]) // eslint-disable-line

  // req/list에서 gendoc 변경 시 동기화
  useEffect(() => {
    if (!activeGendocuid) return
    setSelectedGendocuid(activeGendocuid)
  }, [activeGendocuid]) // eslint-disable-line

  // 챕터 목록
  const { data: chapData = {} } = useGenchapters(selectedGendocuid)
  const chapters = chapData.chapters || []

  // 선택된 챕터 (로컬)
  const [selectedGenchapteruid, setSelectedGenchapteruid] = useState(null)

  // gendoc 변경 시 챕터 첫 항목 자동 선택
  useEffect(() => {
    if (!chapters.length) { setSelectedGenchapteruid(null); return }
    setSelectedGenchapteruid(chapters[0]?.genchapteruid)
  }, [selectedGendocuid, chapters.length]) // eslint-disable-line

  const { data = {}, isLoading } = useChapterObjects(selectedGenchapteruid)
  const rewriteMutation = useRewriteObject(selectedGenchapteruid)
  const applyMutation = useApplyObjects(selectedGenchapteruid)

  const [selectedRow, setSelectedRow] = useState(null)
  const [loadingText, setLoadingText] = useState('')
  const [showLoading, setShowLoading] = useState(false)

  const {
    objects = [],
    chapternm = '',
    closeyn = false,
  } = data

  // chapters-read에서 챕터 선택 시 동기화
  useEffect(() => {
    if (!activeGenchapteruid) return
    setSelectedGenchapteruid(activeGenchapteruid)
  }, [activeGenchapteruid]) // eslint-disable-line

  // 챕터 변경 시 선택 초기화
  useEffect(() => {
    setSelectedRow(null)
  }, [selectedGenchapteruid])

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
      {/* 페이지 타이틀 + 셀렉트박스 */}
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.chapter.objects')}{chapternm ? `: ${chapternm}` : ''}</div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Select
            style={{ width: 240 }}
            value={selectedGendocuid}
            onChange={(val) => setSelectedGendocuid(val)}
            options={gendocs.map((g) => ({ value: g.gendocuid, label: g.gendocnm }))}
            placeholder={t('msg.select')}
          />
          <Select
            style={{ width: 200 }}
            value={selectedGenchapteruid}
            onChange={(val) => setSelectedGenchapteruid(val)}
            options={chapters.map((c) => ({ value: c.genchapteruid, label: c.chapternm }))}
            placeholder={t('msg.select.chapter')}
          />
        </div>
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
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.object.detail')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
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
