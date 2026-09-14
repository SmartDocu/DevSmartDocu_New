import { useState, useEffect } from 'react'
import { App, Select, Spin } from 'antd'
import { RedoOutlined, CheckOutlined, CheckCircleFilled } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useReqStore } from '@/stores/reqStore'
import { useGendocs, useGenchapters } from '@/hooks/useGendocs'
import { getErrorDetail } from '@/utils/apiError'

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
  const { message, modal } = App.useApp()

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
      message.success(t('msg.object.write.complete'))
      setSelectedRow((prev) => prev)
    } catch (err) {
      message.error(t('msg.server.error') + ': ' + (getErrorDetail(err) || err.message))
    } finally {
      setShowLoading(false)
      setLoadingText('')
    }
  }

  const handleApply = () => {
    modal.confirm({
      content: t('msg.confirm.object.apply'),
      onOk: async () => {
        setLoadingText(t('msg.loading.object.applying'))
        setShowLoading(true)
        try {
          await applyMutation.mutateAsync()
          message.success(t('msg.object.apply.complete'))
        } catch (err) {
          message.error(t('msg.server.error') + ': ' + (getErrorDetail(err) || err.message))
        } finally {
          setShowLoading(false)
          setLoadingText('')
        }
      },
    })
  }

  return (
    <div>
      {/* 페이지 타이틀 */}
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('ttl.chapter.objects')}</div>
        </div>
      </div>

      {/* 필터 — req/list와 동일한 위치/형태 */}
      <div className="panel-section" style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16 }}>
        <Select
          style={{ width: 240, flexShrink: 0 }}
          value={selectedGendocuid}
          onChange={(val) => setSelectedGendocuid(val)}
          options={gendocs.map((g) => ({ value: g.gendocuid, label: g.gendocnm }))}
          placeholder={t('msg.select')}
        />
        <Select
          style={{ width: 200, flexShrink: 0 }}
          value={selectedGenchapteruid}
          onChange={(val) => setSelectedGenchapteruid(val)}
          options={chapters.map((c) => ({ value: c.genchapteruid, label: c.chapternm }))}
          placeholder={t('msg.select.chapter')}
        />
        {data.createfiledts !== undefined && (
          <>
            <span style={{ color: '#d9d9d9', flexShrink: 0 }}>|</span>
            <div style={{ fontSize: 13, flexShrink: 0 }}>
              <span style={{ color: '#888' }}>{t('lbl.chapter.create.dts')}: </span>
              <span>{data.createfiledts || '-'}</span>
            </div>
          </>
        )}
      </div>

      {/* 본문 */}
      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>

        {/* 좌측: 항목 목록 */}
        <div className="panel-section" style={{ flex: 1.5, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 264px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.object.list')}</h3>
            <div />
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
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
                  <th style={{ width: '11%' }}>{t('thd.obj.setting.dts')}</th>
                  <th style={{ width: '8%', whiteSpace: 'pre-line' }}>{t('thd.new.object.yn')}</th>
                  <th style={{ width: '11%' }}>{t('thd.obj.write.dts')}</th>
                  <th style={{ width: '10%', whiteSpace: 'pre-line' }}>{t('thd.new.genobject.yn')}</th>
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
                    <td className="info">
                      {obj.new_objectyn && <CheckCircleFilled style={{ color: '#2f7d4f' }} title={t('thd.new.object.yn')} />}
                    </td>
                    <td className="info">{obj.genobjcreatedts || ''}</td>
                    <td className="info">
                      {obj.new_genobjectyn && <CheckCircleFilled style={{ color: '#2f7d4f' }} title={t('thd.new.genobject.yn')} />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          </div>
        </div>

        {/* 우측: 항목 내용 */}
        <div className="panel-section" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 264px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.object.detail')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {editbuttonyn && selectedRow && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={closeyn || rewriteMutation.isPending}
                  onClick={() => handleRewrite(selectedRow)}
                >
                  <RedoOutlined style={{ marginRight: 6 }} />{t('btn.object.rewrite')}
                </button>
              )}
              {editbuttonyn && (
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={closeyn || applyMutation.isPending}
                  onClick={handleApply}
                >
                  <CheckOutlined style={{ marginRight: 6 }} />{t('btn.object.apply')}
                </button>
              )}
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>

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
