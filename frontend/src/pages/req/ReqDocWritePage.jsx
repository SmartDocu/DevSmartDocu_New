import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useGenchapters } from '@/hooks/useGendocs'
import { useAuthStore } from '@/stores/authStore'

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
    // 선택 안 된 챕터 확인
    const unselected = chapters.filter((ch) => !modes[ch.genchapteruid])
    if (unselected.length > 0) {
      alert('선택 되지 않은 챕터가 있습니다.\r\n확인 후 다시 작업 부탁드립니다.')
      return
    }

    setGenerating(true)
    setProgress({ step: 0, total: 1, message: '준비 중...', status: 'processing' })

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
        if (!res.ok) throw new Error('서버 오류 발생')
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
                  alert(data.message)
                  return
                }

                setProgress(data)

                if (data.status === 'completed') {
                  setGenerating(false)
                  setTimeout(() => {
                    alert(`문서 작성 완료: ${data.docnm || '완료'}`)
                    navigate(`/req/doc-read?gendocs=${gendocuid}&type=auto`)
                  }, 1000)
                } else if (data.status === 'error') {
                  setGenerating(false)
                  alert('오류 발생: ' + data.message)
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
        alert('오류 발생: ' + e.message)
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
          <div>문서 작성: {gendoc.gendocnm || ''}</div>
        </div>
        <button type="button" className="icon-btn" onClick={handleBack}>
          <img src="/icons/back.svg" alt="뒤로가기" className="icon-img config-icon" />
        </button>
      </div>

      {/* 메타 정보 */}
      {gendoc.gendocnm && (
        <div className="form-filter-group">
          <div className="filter-item">
            <label style={{ width: 80 }}>매개변수: </label>
            <label style={{ width: 312 }}>{gendoc.paramvalue || ''}</label>
          </div>
          <div className="filter-item">
            <label style={{ width: 120 }}>최종 작성 일시: </label>
            <label style={{ width: 120 }}>{gendoc.finaldts || ''}</label>
          </div>
          <div className="filter-item">
            <label style={{ width: 120 }}>문서 업로드 일시:</label>
            <label style={{ width: 120 }}>{gendoc.updatefiledts || ''}</label>
          </div>
        </div>
      )}

      {/* 챕터 목록 테이블 */}
      <div style={{ height: '80%' }}>
        {isLoading ? (
          <div style={{ padding: 20, textAlign: 'center' }}>불러오는 중...</div>
        ) : chapters.length > 0 ? (
          <table className="table table-bordered table-sm">
            <thead>
              <tr>
                <th style={{ width: '30%' }}>챕터명</th>
                <th style={{ width: '6%' }}>작성자</th>
                <th style={{ width: '6%' }}>업로더</th>
                <th style={{ width: '9%' }}>작성 일시</th>
                <th style={{ width: '9%' }}>업로드 일시</th>
                <th style={{ width: '5%' }}>자동 작성</th>
                <th style={{ width: '6%' }}>수정 업로드</th>
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
            className="btn btn-link"
            disabled={gendoc.closeyn || generating}
            onClick={handleGenerate}
          >
            문서 작성
          </button>
        )}
      </div>

      {/* 로딩 오버레이 */}
      {generating && (
        <div
          style={{
            position: 'fixed',
            top: 0, left: 0,
            width: '100%', height: '100%',
            backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            zIndex: 9999,
          }}
        >
          <div
            style={{
              background: 'white',
              padding: 30,
              borderRadius: 10,
              textAlign: 'center',
              boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
              width: 330,
            }}
          >
            <div style={{ fontSize: 16, fontWeight: 'bold', color: '#333', marginBottom: 10 }}>
              문서 작성 중...
            </div>
            <div
              style={{
                width: '100%',
                backgroundColor: '#f0f0f0',
                borderRadius: 10,
                marginBottom: 15,
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  height: 20,
                  background: 'linear-gradient(90deg,#007bff,#0056b3)',
                  borderRadius: 10,
                  transition: 'width 0.3s ease',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'white',
                  fontSize: 12,
                  fontWeight: 'bold',
                  width: `${percentage}%`,
                  minWidth: percentage > 0 ? 30 : 0,
                }}
              >
                {percentage > 0 ? `${percentage}%` : ''}
              </div>
            </div>
            <div style={{ fontSize: 14, color: '#333', marginBottom: 10, fontWeight: 'bold' }}>
              {progress ? `${progress.step} / ${progress.total} 단계` : '준비 중...'}
            </div>
            <div style={{ fontSize: 13, color: '#666', marginBottom: 5 }}>
              {progress?.message || ''}
            </div>
            <div style={{ fontSize: 14, color: '#666' }}>잠시만 기다려 주세요.</div>
          </div>
        </div>
      )}
    </div>
  )
}
