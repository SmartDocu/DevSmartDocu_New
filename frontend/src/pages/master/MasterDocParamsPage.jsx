import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { App, Popconfirm, Spin } from 'antd'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'

export default function MasterDocParamsPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const docid = searchParams.get('docid')
  const qc = useQueryClient()

  // 각 셀 선택값: { `${datauid}__${paramuid}`: querycolnm }
  const [selections, setSelections] = useState({})

  const { data, isLoading } = useQuery({
    queryKey: ['doc-params', docid],
    queryFn: () => apiClient.get(`/docs/${docid}/doc-params`).then((r) => r.data),
    enabled: !!docid,
  })

  const doc = data?.doc || {}
  const datas = data?.datas || []
  const dataparams = data?.dataparams || []
  const colMap = data?.col_map || {}
  const dataparamMap = data?.dataparam_map || {}

  // 서버 데이터로 초기 selections 설정
  useEffect(() => {
    if (!data) return
    const init = {}
    Object.entries(dataparamMap).forEach(([datauid, colToParam]) => {
      Object.entries(colToParam).forEach(([querycolnm, paramuid]) => {
        init[`${datauid}__${paramuid}`] = querycolnm
      })
    })
    setSelections(init)
  }, [data]) // eslint-disable-line

  const saveMutation = useMutation({
    mutationFn: (records) =>
      apiClient.post(`/docs/${docid}/doc-params`, { records }).then((r) => r.data),
    onSuccess: () => {
      message.success('저장되었습니다.')
      qc.invalidateQueries({ queryKey: ['doc-params', docid] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '저장에 실패했습니다.'),
  })

  const deleteMutation = useMutation({
    mutationFn: (datauids) =>
      apiClient.delete(`/docs/${docid}/doc-params`, { data: { datauids } }).then((r) => r.data),
    onSuccess: () => {
      message.success('삭제되었습니다.')
      setSelections({})
      qc.invalidateQueries({ queryKey: ['doc-params', docid] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '삭제에 실패했습니다.'),
  })

  const handleReset = () => setSelections({})

  const handleSave = () => {
    const records = []
    Object.entries(selections).forEach(([key, querycolnm]) => {
      if (!querycolnm) return
      const [datauid, paramuid] = key.split('__')
      records.push({ datauid, querycolnm, paramuid, docid: Number(docid) })
    })
    if (!records.length) { message.warning('설정된 값이 없습니다.'); return }
    saveMutation.mutate(records)
  }

  const handleDelete = () => {
    const datauids = datas.map((d) => d.datauid)
    deleteMutation.mutate(datauids)
  }

  const handleSelect = (datauid, paramuid, querycolnm) => {
    setSelections((prev) => ({ ...prev, [`${datauid}__${paramuid}`]: querycolnm }))
  }

  if (!docid) return <div style={{ padding: 24, color: '#888' }}>docid가 없습니다.</div>

  return (
    <div style={{ position: 'relative' }}>
      {/* 타이틀 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 4, height: 22, background: 'linear-gradient(#1677ff,#69b1ff)', borderRadius: 2 }} />
          <span style={{ fontSize: 16, fontWeight: 700 }}>
            문서 관리 - 매개변수 : {doc.docnm || ''}
          </span>
        </div>
        <button className="icon-btn" onClick={() => navigate(`/master/docs?docid=${docid}`)} title="뒤로가기">
          <img src="/icons/back.svg" className="icon-img config-icon" alt="뒤로가기" />
        </button>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
      ) : (
        <>
          {/* 2D 테이블 */}
          <div style={{ overflowX: 'auto', marginBottom: 16 }}>
            <table className="dataset-table" style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#f5f5f5' }}>
                  <th style={th}>데이터명</th>
                  {dataparams.map((p) => (
                    <th key={p.paramuid} style={th}>{p.paramnm}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {datas.length === 0 ? (
                  <tr><td colSpan={dataparams.length + 1} style={{ textAlign: 'center', padding: 16, color: '#888' }}>
                    프로젝트에 등록된 데이터가 없습니다.
                  </td></tr>
                ) : datas.map((d) => (
                  <tr key={d.datauid} style={{ borderBottom: '1px solid #eee' }}>
                    <td style={td}>{d.datanm}</td>
                    {dataparams.map((p) => {
                      const cols = colMap[d.datauid] || []
                      const val = selections[`${d.datauid}__${p.paramuid}`] || ''
                      return (
                        <td key={p.paramuid} style={td}>
                          <select
                            value={val}
                            onChange={(e) => handleSelect(d.datauid, p.paramuid, e.target.value)}
                            style={{ width: 200, padding: '2px 4px', border: '1px solid #d9d9d9', borderRadius: 4, fontSize: 13 }}
                          >
                            <option value="">선택</option>
                            {cols.map((col) => (
                              <option key={col.querycolnm} value={col.querycolnm}>
                                {col.dispcolnm}
                              </option>
                            ))}
                          </select>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* 버튼 영역 */}
          <div className="button-group" style={{ display: 'flex', gap: 8 }}>
            <button className="icon-btn" onClick={handleReset} title="신규(초기화)">
              <div className="icon-wrapper">
                <img src="/icons/new.svg" className="icon-img new-icon" alt="신규" />
                <span className="icon-label">신규</span>
              </div>
            </button>
            <button className="icon-btn" onClick={handleSave} disabled={saveMutation.isPending} title="저장">
              <div className="icon-wrapper">
                <img src="/icons/save.svg" className="icon-img save-icon" alt="저장" />
                <span className="icon-label">저장</span>
              </div>
            </button>
            <Popconfirm
              title="모든 데이터-매개변수 매핑을 삭제하시겠습니까?"
              onConfirm={handleDelete}
              okText="삭제" cancelText="취소" okButtonProps={{ danger: true }}
            >
              <button className="icon-btn" title="삭제">
                <div className="icon-wrapper">
                  <img src="/icons/delete.svg" className="icon-img del-icon" alt="삭제" />
                  <span className="icon-label">삭제</span>
                </div>
              </button>
            </Popconfirm>
          </div>
        </>
      )}
    </div>
  )
}

const th = { padding: '6px 10px', border: '1px solid #ddd', fontWeight: 600, whiteSpace: 'nowrap', textAlign: 'left' }
const td = { padding: '5px 8px', border: '1px solid #eee', verticalAlign: 'middle' }
