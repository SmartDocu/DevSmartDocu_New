import { useState, useEffect } from 'react'
import { Select, Spin, Tag } from 'antd'
import dayjs from 'dayjs'
import { useGendocs, useGendocStatus } from '@/hooks/useGendocs'
import { useAuthStore } from '@/stores/authStore'
import { useLangStore, t } from '@/stores/langStore'
import { useReqStore } from '@/stores/reqStore'

const TODAY = dayjs().format('YYYY-MM-DD')
const ONE_YEAR_AGO = dayjs().subtract(365, 'day').format('YYYY-MM-DD')

export default function ReqDocStatusPage() {
  useLangStore((s) => s.translations)

  const { user } = useAuthStore()
  const { activeGendocuid } = useReqStore()

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

  const { data = {}, isLoading } = useGendocStatus(selectedGendocuid)

  const { status: rows = [], gendocnm = '', createfiledts = '' } = data

  const totalChapters = rows.length
  const unreflectedChapters = rows.filter((r) => r.new_chapteryn).length
  const unreflectedObjects = rows.reduce((sum, r) => sum + (r.new_object_cnt || 0), 0)

  return (
    <div>
      {/* 페이지 타이틀 */}
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.doc.status_ttl')}</div>
        </div>
        <Select
          style={{ width: 280 }}
          value={selectedGendocuid}
          onChange={(val) => setSelectedGendocuid(val)}
          options={gendocs.map((g) => ({ value: g.gendocuid, label: g.gendocnm }))}
          placeholder={t('msg.select')}
        />
      </div>

      {/* 요약 통계 */}
      <div style={{ display: 'flex', gap: 24, padding: '6px 10px', background: '#f5f5f5', borderRadius: 6, marginBottom: 10, fontSize: 13 }}>
        <span>
          <span style={{ color: '#888' }}>{t('lbl.doc.createfiledts')}: </span>
          <strong>{createfiledts || '-'}</strong>
        </span>
        <span>
          <span style={{ color: '#888' }}>{t('lbl.total.chapters')}: </span>
          <strong>{totalChapters}</strong>
        </span>
        <span>
          <span style={{ color: '#888' }}>{t('lbl.unreflected.chapters')}: </span>
          <strong style={{ color: unreflectedChapters > 0 ? 'orange' : undefined }}>{unreflectedChapters}</strong>
        </span>
        <span>
          <span style={{ color: '#888' }}>{t('lbl.unreflected.objects')}: </span>
          <strong style={{ color: unreflectedObjects > 0 ? 'red' : undefined }}>{unreflectedObjects}</strong>
        </span>
      </div>

      {/* 챕터 상태 테이블 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
        <h3 style={{ margin: 0 }}>{t('ttl.chapter.status')}</h3>
        <div />
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table className="table table-bordered table-sm">
          <thead>
            <tr>
              <th>{t('thd.chapternm')}</th>
              <th style={{ width: '8%', textAlign: 'center' }}>{t('thd.createuser')}</th>
              <th style={{ width: '11%', textAlign: 'center' }}>{t('thd.createfiledts')}</th>
              <th style={{ width: '8%', textAlign: 'center' }}>{t('thd.updateuser')}</th>
              <th style={{ width: '11%', textAlign: 'center' }}>{t('thd.updatefiledts')}</th>
              <th style={{ width: '9%', textAlign: 'center' }}>{t('thd.new_chapteryn')}</th>
              <th style={{ width: '8%', textAlign: 'center' }}>{t('thd.object_cnt')}</th>
              <th style={{ width: '10%', textAlign: 'center' }}>{t('thd.new_object_cnt')}</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={8} style={{ textAlign: 'center', padding: 16 }}><Spin /></td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={8} style={{ textAlign: 'center', padding: 16 }}>{t('msg.no.data')}</td></tr>
            ) : rows.map((row) => (
              <tr key={row.genchapteruid || row.chapternm}>
                <td>{row.chapternm}</td>
                <td style={{ textAlign: 'center' }}>{row.createuser || ''}</td>
                <td style={{ textAlign: 'center' }}>{row.createfiledts || '-'}</td>
                <td style={{ textAlign: 'center' }}>{row.updateuser || ''}</td>
                <td style={{ textAlign: 'center' }}>{row.updatefiledts || '-'}</td>
                <td style={{ textAlign: 'center' }}>{row.new_chapteryn ? <Tag color="orange">√</Tag> : ''}</td>
                <td style={{ textAlign: 'center' }}>{row.object_cnt ?? 0}</td>
                <td style={{ textAlign: 'center' }}>{row.new_object_cnt > 0 ? <Tag color="red">{row.new_object_cnt}</Tag> : (row.new_object_cnt ?? 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
