import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import { t } from '@/stores/langStore'
import apiClient from '@/api/client'

export function useGendocs(startDate, endDate, docid, searchBy, docgroupid) {
  return useQuery({
    queryKey: ['gendocs', startDate, endDate, docid, searchBy, docgroupid],
    queryFn: () =>
      apiClient.get('/gendocs', { params: { start_date: startDate, end_date: endDate, docid, search_by: searchBy, docgroupid: docgroupid || undefined } }).then((r) => r.data),
    // DocGroup 검색 모드인데 아직 그룹을 선택하지 않았으면(docgroupid 없음) 조회하지 않는다 —
    // docgroupid 없이 search_by=DocGroup으로 조회하면 백엔드가 응답을 못 주고 스피너가 멈추지 않는 문제가 있었음.
    enabled: !!docid && (searchBy !== 'DocGroup' || !!docgroupid),
    // 조회(재조회) 중 이전 데이터를 유지 — 없으면 refetch 동안 listData가 잠깐 {}가 되어
    // 페이지 타이틀이 "선택된 문서 없음"으로, 목록이 빈 화면으로 깜빡였다.
    placeholderData: (prev) => prev,
    // 브라우저 탭을 잠깐 안 보다가 다시 포커스했을 때 조용히 갱신되던 게 아니라
    // 전체 화면 로딩 오버레이(isFetching 연동)가 떠서 매번 "로딩"처럼 보였다 — 자동 refetch를 끈다.
    // 조회 버튼(생성 기간 변경)은 쿼리 키 자체가 바뀌므로 이 옵션과 무관하게 그대로 재조회된다.
    refetchOnWindowFocus: false,
  })
}

export function useDataparams() {
  return useQuery({
    queryKey: ['gendocs-dataparams'],
    queryFn: () => apiClient.get('/gendocs/dataparams').then((r) => r.data),
  })
}

export function useGendocStatus(gendocuid) {
  return useQuery({
    queryKey: ['gendoc-status', gendocuid],
    queryFn: () => apiClient.get(`/gendocs/${gendocuid}/status`).then((r) => r.data),
    enabled: !!gendocuid,
  })
}

export function useGenchapters(gendocuid) {
  return useQuery({
    queryKey: ['genchapters', gendocuid],
    queryFn: () => apiClient.get(`/gendocs/${gendocuid}/chapters`).then((r) => r.data),
    enabled: !!gendocuid,
    refetchInterval: (data) => {
      // Auto-refetch if chapters are still generating
      const chapters = data?.chapters || []
      const pending = chapters.some((c) => !c.createfiledts)
      return pending ? 3000 : false
    },
  })
}

export function useCreateGendoc() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (body) => apiClient.post('/gendocs', body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['gendocs'] })
    },
    onError: (err) => {
      const detail = err.response?.data?.detail
      message.error(detail ? t(detail) : t('msg.save.error'))
    },
  })
}

export function useDeleteGendoc() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (gendocuid) => apiClient.delete(`/gendocs/${gendocuid}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['gendocs'] })
    },
    onError: (err) => {
      const detail = err.response?.data?.detail
      message.error(detail ? t(detail) : t('msg.delete.error'))
    },
  })
}

export function useUpdateGendocParams() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (body) => apiClient.post('/gendocs/params/update', body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['gendocs'] })
    },
    onError: (err) => {
      const detail = err.response?.data?.detail
      message.error(detail ? t(detail) : t('msg.save.error'))
    },
  })
}

export function useCloseGendoc() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (gendocuid) => apiClient.post(`/gendocs/${gendocuid}/close`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.gendoc.closed'))
      qc.invalidateQueries({ queryKey: ['gendocs'] })
    },
    onError: (err) => {
      const detail = err.response?.data?.detail
      message.error(detail ? t(detail) : t('msg.save.error'))
    },
  })
}

export function useOpenGendoc() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (gendocuid) => apiClient.post(`/gendocs/${gendocuid}/open`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.gendoc.opened'))
      qc.invalidateQueries({ queryKey: ['gendocs'] })
    },
    onError: (err) => {
      const detail = err.response?.data?.detail
      message.error(detail ? t(detail) : t('msg.save.error'))
    },
  })
}
