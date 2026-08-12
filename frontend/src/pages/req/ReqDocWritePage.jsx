import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { App, Spin } from 'antd'
import { useGenchapters } from '@/hooks/useGendocs'
import apiClient from '@/api/client'
import { supabase } from '@/lib/supabaseClient'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'

// 라디오 초기값 계산: createfiledts vs updatefiledts 비교
function getInitialMode(ch) {
  const c = ch.createfiledts || ''
  const u = ch.updatefiledts || ''
  if (!c && !u) return null
  if (c && !u) return 'create'
  if (!c && u) return 'update'
  // 둘 다 있으면 더 최신인 쪽
  return c > u ? 'create' : 'update'
}

export default function ReqDocWritePage() {
  useLangStore((s) => s.translations)

  const { message } = App.useApp()
  const navigate = useNavigate()
  const { appcd } = useParams()
  const [searchParams] = useSearchParams()
  const gendocuid = searchParams.get('gendocs')
  const { user } = useAuthStore()

  const { data: chapData = {}, isLoading } = useGenchapters(gendocuid)
  const chapters = chapData.chapters || []
  const gendoc = chapData.gendoc || {}

  const editbuttonyn = user?.editbuttonyn === 'Y'

  // 챕터별 라디오 선택 상태 { [genchapteruid]: 'create' | 'update' | null }
  const [modes, setModes] = useState({})

  // 챕터 데이터 로드 후 초기 라디오값 설정
  useEffect(() => {
    if (chapters.length === 0) return
    const initial = {}
    chapters.forEach((ch) => {
      initial[ch.genchapteruid] = getInitialMode(ch)
    })
    setModes(initial)
  }, [chapters.length]) // eslint-disable-line react-hooks/exhaustive-deps

  const [generating,     setGenerating]     = useState(false)
  const [requestLoading, setRequestLoading] = useState(false)

  const handleModeChange = (genchapteruid, value) => {
    setModes((prev) => ({ ...prev, [genchapteruid]: value }))
  }

  // 탭 재진입 시 조합 작성 진행 상태 자동 조회
  useEffect(() => {
    if (!gendocuid) return
    apiClient.get(`/gendocs/${gendocuid}/generate/status`)
      .then((res) => { if (res.data.JobStatusCD === 'S') setGenerating(true) })
      .catch(() => {})
  }, [gendocuid])

  // 문서 조합 작성 완료 감지 (Realtime)
  useEffect(() => {
    if (!generating || !gendocuid) return
    const channel = supabase
      .channel(`doc_combine_${gendocuid}`)
      .on('postgres_changes',
        { event: 'UPDATE', schema: 'sdoc', table: 'gendocs_realtimes', filter: `gendocuid=eq.${gendocuid}` },
        (payload) => {
          if (payload.new.jobstatuscd !== 'E') return  // 'S'->'merging'->'E' 순서로 바뀌므로 'E'일 때만 완료로 판단
          setGenerating(false)
          if (payload.new.errorcd) {
            message.error(payload.new.errormessage || t('msg.server.error'))
            return
          }
          message.success(`${t('msg.doc.write.complete')}: ${gendoc.gendocnm || ''}`)
          navigate(`/app/${appcd}/req/doc-read?gendocs=${gendocuid}&type=auto`)
        })
      .subscribe()
    return () => { supabase.removeChannel(channel) }
  }, [generating, gendocuid]) // eslint-disable-line

  // ── 문서 조합 작성 (SQS 비동기 — 이미 작성된 챕터만 선택 그대로 병합, 신규 생성 없음) ──
  const handleCombine = async () => {
    if (!gendocuid) return
    const written = chapters.filter((ch) => modes[ch.genchapteruid])
    if (written.length === 0) {
      message.warning(t('msg.chapter.combine.none'))
      return
    }

    setRequestLoading(true)
    try {
      const res = await apiClient.post(`/gendocs/${gendocuid}/combine`, {
        chapters: written.map((ch) => ({ genchapteruid: ch.genchapteruid, mode: modes[ch.genchapteruid] })),
        projectid: user?.projectid, tenantid: user?.tenantid, accountuid: user?.accountuid,
      })
      if (res.data.locked) {
        message.warning(res.data.message || t('msg.doc.already.writing'))
        return
      }
      if (res.data.no_written_chapters) {
        message.warning(res.data.message || t('msg.chapter.combine.none'))
        return
      }
      setGenerating(true)
      message.success(t('msg.doc.write.started'))
    } catch (e) {
      message.error(t('msg.server.error') + ': ' + (e.response?.data?.detail || e.message))
    } finally {
      setRequestLoading(false)
    }
  }

  const handleBack = () => {
    const stored = sessionStorage.getItem('chapter_read_gendocuid')
    const target = stored || gendocuid
    navigate(`/app/${appcd}/req/chapters-read?gendocs=${target}`)
  }

  return (
    <div>
      {/* 페이지 타이틀 */}
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.doc.write_ttl')}: {gendoc.gendocnm || ''}</div>
        </div>
        <button type="button" className="btn btn-back" onClick={handleBack}>
          {t('btn.back')}
        </button>
      </div>

      {/* 메타 정보 */}
      {gendoc.gendocnm && (
        <div className="form-filter-group">
          <div className="filter-item">
            <label style={{ width: 80 }}>{t('lbl.paramnm_lbl')}: </label>
            <label style={{ width: 312 }}>{gendoc.paramvalue || ''}</label>
          </div>
          <div className="filter-item">
            <label style={{ width: 120 }}>{t('lbl.doc.final.dts')}: </label>
            <label style={{ width: 120 }}>{gendoc.finaldts || ''}</label>
          </div>
          <div className="filter-item">
            <label style={{ width: 120 }}>{t('lbl.doc.upload.dts')}:</label>
            <label style={{ width: 120 }}>{gendoc.updatefiledts || ''}</label>
          </div>
        </div>
      )}

      {/* 챕터 목록 테이블 */}
      <div style={{ height: '80%' }}>
        {isLoading ? (
          <div style={{ padding: 20, textAlign: 'center' }}>{t('msg.loading')}</div>
        ) : chapters.length > 0 ? (
          <table className="table table-bordered table-sm">
            <thead>
              <tr>
                <th style={{ width: '30%' }}>{t('thd.chapternm')}</th>
                <th style={{ width: '6%' }}>{t('thd.createuser')}</th>
                <th style={{ width: '6%' }}>{t('thd.updateuser')}</th>
                <th style={{ width: '9%' }}>{t('thd.createfiledts')}</th>
                <th style={{ width: '9%' }}>{t('thd.updatefiledts')}</th>
                <th style={{ width: '5%' }}>{t('thd.auto.write')}</th>
                <th style={{ width: '6%' }}>{t('thd.modified.upload')}</th>
              </tr>
            </thead>
            <tbody>
              {chapters.map((ch, idx) => {
                const hasCreate = !!ch.createfiledts
                const hasUpdate = !!ch.updatefiledts
                const selected = modes[ch.genchapteruid]
                return (
                  <tr key={ch.genchapteruid} className="chapter-row">
                    <td>{ch.chapternm}</td>
                    <td className="info">{ch.createuser || ''}</td>
                    <td className="info">{ch.updateuser || ''}</td>
                    <td className="info">{ch.createfiledts || ''}</td>
                    <td className="info">{ch.updatefiledts || ''}</td>
                    <td className="info">
                      <input
                        type="radio"
                        name={`mode_${idx}`}
                        value="create"
                        disabled={!hasCreate}
                        checked={selected === 'create'}
                        onChange={() => handleModeChange(ch.genchapteruid, 'create')}
                      />
                    </td>
                    <td className="info">
                      <input
                        type="radio"
                        name={`mode_${idx}`}
                        value="update"
                        disabled={!hasUpdate}
                        checked={selected === 'update'}
                        onChange={() => handleModeChange(ch.genchapteruid, 'update')}
                      />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        ) : (
          <div style={{ padding: 20, textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</div>
        )}
      </div>

      {/* 문서 조합 작성 버튼 */}
      <div style={{ marginTop: 10, textAlign: 'center' }}>
        {editbuttonyn && (
          <button
            id="docWriteBtn"
            className="btn btn-primary"
            disabled={gendoc.closeyn || generating}
            onClick={handleCombine}
          >
            {generating ? t('msg.doc.writing') : t('btn.doc.write')}
          </button>
        )}
      </div>

      {/* 로딩 오버레이 (접수 완료까지만 표시 — 조합 작성 진행 중에는 다른 탭 이동 가능해야 함) */}
      {requestLoading && (
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
            <span>{t('msg.loading.wait')}</span>
          </div>
        </div>
      )}
    </div>
  )
}
