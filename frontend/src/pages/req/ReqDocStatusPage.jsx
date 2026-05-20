import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Spin, Tag } from 'antd'
import { useGendocStatus } from '@/hooks/useGendocs'
import { useLangStore, t } from '@/stores/langStore'
import { useOpenInTab } from '@/hooks/useOpenInTab'

export default function ReqDocStatusPage() {
  useLangStore((s) => s.translations)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const gendocuid = searchParams.get('gendocs')
  const openInTab = useOpenInTab()

  const { data = {}, isLoading } = useGendocStatus(gendocuid)
  const [selectedRow, setSelectedRow] = useState(null)

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
          <div>{t('ttl.doc.status_ttl')}{gendocnm && ` - ${gendocnm}`}</div>
        </div>
        <button className="btn btn-back" type="button" onClick={() => navigate(-1)}>
          {t('btn.back')}
        </button>
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button className="btn btn-primary" type="button"
            onClick={() => openInTab('req/chapters-read', `?gendocs=${gendocuid}`, t('btn.chapter.read'))}>
            {t('btn.chapter.read')}
          </button>
          {selectedRow && (
            <button className="btn btn-primary" type="button"
              onClick={() => openInTab('req/chapter-objects', `?genchapteruid=${selectedRow.genchapteruid}`, t('btn.item.manage'))}>
              {t('btn.item.manage')}
            </button>
          )}
        </div>
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
              <tr
                key={row.genchapteruid || row.chapternm}
                onClick={() => setSelectedRow(row)}
                className={selectedRow?.genchapteruid === row.genchapteruid ? 'selected-row' : ''}
                style={{ cursor: 'pointer' }}
              >
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
