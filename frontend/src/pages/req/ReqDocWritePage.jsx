import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Spin } from 'antd'
import { useGenchapters } from '@/hooks/useGendocs'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'

// SSE progress 이벤트 → i18n 메시지 변환
function getProgressMessage(progress) {
  if (!progress) return ''
  const { type, obj, chapter_name, chapter_index, chapter_total } = progress
  if (type === 'wait') return t('msg.loading.preparing')
  if (obj === 'chapter') {
    if (chapter_index != null && chapter_total != null) {
      return t('msg.loading.chapter.count')
        .replace('{index}', chapter_index)
        .replace('{total}', chapter_total)
    }
    return chapter_name || t('msg.loading.chapter.preparing')
  }
  if (obj === 'chapter_done') return t('msg.loading.chapter.finalizing')
  if (obj === 'doc') return t('msg.loading.doc.merging')
  if (chapter_name) return chapter_name
  return ''
}

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

  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const gendocuid = searchParams.get('gendocs')
  const { accessToken, user } = useAuthStore()

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

  const [generating, setGenerating] = useState(false)
  const [progress, setProgress] = useState(null)   // { step, total, message, status }

  const handleModeChange = (genchapteruid, value) => {
    setModes((prev) => ({ ...prev, [genchapteruid]: value }))
  }

  const handleGenerate = () => {
    const unselected = chapters.filter((ch) => !modes[ch.genchapteruid])
    if (unselected.length > 0) {
      alert(t('msg.chapter.unselected'))
      return
    }

    setGenerating(true)
    setProgress({ step: 0, total: 1, message: t('msg.loading.preparing'), status: 'processing' })

    const results = chapters.map((ch) => ({
      genchapteruid: ch.genchapteruid,
      mode: modes[ch.genchapteruid],
    }))

    fetch(`/api/gendocs/${gendocuid}/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ results }),
    })
      .then((res) => {
        if (!res.ok) throw new Error(t('msg.server.error'))
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''

        const read = () => {
          reader.read().then(({ done, value }) => {
            if (done) {
              setGenerating(false)
              return
            }
            buf += decoder.decode(value, { stream: true })
            const parts = buf.split('\n\n')
            buf = parts.pop() || ''
            parts.forEach((part) => {
              if (!part.trim().startsWith('data:')) return
              try {
                const jsonStr = part.trim().replace(/^data:\s*/, '')
                if (!jsonStr) return
                const data = JSON.parse(jsonStr)

                if (data.type === 'locked') {
                  setGenerating(false)
                  alert(t('msg.doc.already.writing'))
                  return
                }

                setProgress(data)

                if (data.status === 'completed') {
                  setGenerating(false)
                  setTimeout(() => {
                    alert(`${t('msg.doc.write.complete')}: ${data.docnm || ''}`)
                    navigate(`/req/doc-read?gendocs=${gendocuid}&type=auto`)
                  }, 1000)
                } else if (data.status === 'error') {
                  setGenerating(false)
                  alert(t('msg.server.error') + ': ' + data.message)
                }
              } catch (_) {}
            })
            read()
          })
        }
        read()
      })
      .catch((e) => {
        setGenerating(false)
        alert(t('msg.server.error') + ': ' + e.message)
      })
  }

  const handleBack = () => {
    const stored = sessionStorage.getItem('chapter_read_gendocuid')
    const target = stored || gendocuid
    navigate(`/req/chapters-read?gendocs=${target}`)
  }

  const percentage = progress && progress.total > 0
    ? Math.round((progress.step / progress.total) * 100)
    : 0

  return (
    <div>
      {/* 페이지 타이틀 */}
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.doc.write_ttl')}: {gendoc.gendocnm || ''}</div>
        </div>
        <button type="button" className="btn btn-link" onClick={handleBack}>
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
                <th style={{ width: '30%' }}>{t('lbl.chapternm')}</th>
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
        ) : null}
      </div>

      {/* 문서 작성 버튼 */}
      <div style={{ marginTop: 10, textAlign: 'center' }}>
        {editbuttonyn && (
          <button
            id="docWriteBtn"
            className="btn btn-primary"
            disabled={gendoc.closeyn || generating}
            onClick={handleGenerate}
          >
            {t('btn.doc.write')}
          </button>
        )}
      </div>

      {/* 로딩 오버레이 */}
      {generating && (
        <div style={{
          position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
          background: 'rgba(0,0,0,0.5)',
          display: 'flex', justifyContent: 'center', alignItems: 'center',
          zIndex: 9999,
        }}>
          <div style={{
            background: '#fafae5', padding: '20px 30px', borderRadius: 8,
            color: '#6c757d', boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
            width: 330, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
          }}>
            <Spin />
            <div style={{ fontSize: 16, fontWeight: 'bold' }}>
              {t('msg.loading.doc.writing')}
            </div>
            <div style={{
              width: '100%', backgroundColor: '#e0e0e0', borderRadius: 10, overflow: 'hidden',
            }}>
              <div style={{
                height: 20,
                background: 'linear-gradient(90deg,#007bff,#0056b3)',
                borderRadius: 10,
                transition: 'width 0.3s ease',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: 'white', fontSize: 12, fontWeight: 'bold',
                width: `${percentage}%`,
                minWidth: percentage > 0 ? 30 : 0,
              }}>
                {percentage > 0 ? `${percentage}%` : ''}
              </div>
            </div>
            <div style={{ fontSize: 14, fontWeight: 'bold' }}>
              {progress ? `${progress.step} / ${progress.total} ${t('lbl.step')}` : t('msg.loading.preparing')}
            </div>
            <div style={{ fontSize: 13 }}>
              {getProgressMessage(progress)}
            </div>
            <div style={{ fontSize: 14 }}>{t('msg.loading.wait')}</div>
          </div>
        </div>
      )}
    </div>
  )
}
