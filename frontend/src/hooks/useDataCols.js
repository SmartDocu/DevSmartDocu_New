import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'

export function useDataColDatas() {
  return useQuery({
    queryKey: ['data-col-datas'],
    queryFn: () => apiClient.get('/data-cols/datas').then((r) => r.data.datas),
  })
}

export function useDataCols(datauid) {
  return useQuery({
    queryKey: ['data-cols', datauid],
    queryFn: () => apiClient.get('/data-cols/datacols', { params: { datauid } }).then((r) => r.data.cols),
    enabled: !!datauid,
  })
}

export function useSaveColAliases() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (cols) => apiClient.post('/data-cols/datacols/aliases', cols).then((r) => r.data),
    onSuccess: (_, cols) => {
      if (cols.length > 0) qc.invalidateQueries({ queryKey: ['data-cols', cols[0].datauid] })
      qc.invalidateQueries({ queryKey: ['data-col-datas'] })
    },
  })
}

export function useDataColValues(datauid, querycolnm) {
  return useQuery({
    queryKey: ['data-col-values', datauid, querycolnm],
    queryFn: () =>
      apiClient.get('/data-cols/values', { params: { datauid, querycolnm } }).then((r) => r.data.values),
    enabled: !!datauid && !!querycolnm,
  })
}

export function useSaveColValue() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/data-cols/values', body).then((r) => r.data),
    onSuccess: (_, body) => {
      qc.invalidateQueries({ queryKey: ['data-col-values', body.datauid, body.querycolnm] })
      qc.invalidateQueries({ queryKey: ['data-col-datas'] })
    },
  })
}

export function useDeleteColValue() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ datauid, querycolnm, value }) =>
      apiClient.delete('/data-cols/values', { params: { datauid, querycolnm, value } }).then((r) => r.data),
    onSuccess: (_, { datauid, querycolnm }) => {
      qc.invalidateQueries({ queryKey: ['data-col-values', datauid, querycolnm] })
      qc.invalidateQueries({ queryKey: ['data-col-datas'] })
    },
  })
}
