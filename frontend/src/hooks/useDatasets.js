import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import apiClient from '@/api/client'
import { t } from '@/stores/langStore'

export function useDatasets() {
  return useQuery({
    queryKey: ['datasets'],
    queryFn: () => apiClient.get('/datasets').then((r) => r.data.datasets),
  })
}

export function useSaveDataset() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (body) => apiClient.post('/datasets', body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['datasets'] })
    },
    onError: (err) => {
      message.error(t(err.response?.data?.detail) || t('msg.save.error'))
    },
  })
}

export function useDeleteDataset() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (datasetuid) => apiClient.delete(`/datasets/${datasetuid}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['datasets'] })
    },
    onError: (err) => {
      message.error(t(err.response?.data?.detail) || t('msg.delete.error'))
    },
  })
}

export function useDatasetMembers(datasetuid) {
  return useQuery({
    queryKey: ['dataset-members', datasetuid],
    queryFn: () => apiClient.get(`/datasets/${datasetuid}/members`).then((r) => r.data),
    enabled: !!datasetuid,
  })
}

export function useSaveDatasetMembers(datasetuid) {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (body) => apiClient.post(`/datasets/${datasetuid}/members`, body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['dataset-members', datasetuid] })
    },
    onError: (err) => {
      message.error(t(err.response?.data?.detail) || t('msg.save.error'))
    },
  })
}

export function useDatasetProjects(datasetuid) {
  return useQuery({
    queryKey: ['dataset-projects', datasetuid],
    queryFn: () => apiClient.get(`/datasets/${datasetuid}/projects`).then((r) => r.data),
    enabled: !!datasetuid,
  })
}

export function useSaveDatasetProjects(datasetuid) {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (body) => apiClient.post(`/datasets/${datasetuid}/projects`, body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['dataset-projects', datasetuid] })
    },
    onError: (err) => {
      message.error(t(err.response?.data?.detail) || t('msg.save.error'))
    },
  })
}

function useAvailableDatas() {
  return useQuery({
    queryKey: ['datasets-available-datas'],
    queryFn: () => apiClient.get('/datasets/available-datas').then((r) => r.data.datas),
  })
}

function useAvailableProjects() {
  return useQuery({
    queryKey: ['datasets-available-projects'],
    queryFn: () => apiClient.get('/datasets/available-projects').then((r) => r.data.projects),
  })
}

export function useDatasetMembersState(datasetuid) {
  const { data: memberData } = useDatasetMembers(datasetuid)
  const { data: availDatas = [] } = useAvailableDatas()

  const datas = datasetuid ? (memberData?.datas || []) : availDatas
  const [checkedDatauids, setCheckedDatauids] = useState([])

  useEffect(() => {
    setCheckedDatauids(memberData?.member_datauids || [])
  }, [memberData])

  const toggle = (uid) =>
    setCheckedDatauids((prev) =>
      prev.includes(uid) ? prev.filter((id) => id !== uid) : [...prev, uid]
    )

  return { datas, checkedDatauids, toggle, setCheckedDatauids }
}

export function useSaveDatasetAll() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (body) => apiClient.post('/datasets/save-all', body).then((r) => r.data),
    onSuccess: (data) => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['datasets'] })
      if (data?.datasetuid) {
        qc.invalidateQueries({ queryKey: ['dataset-members', data.datasetuid] })
        qc.invalidateQueries({ queryKey: ['dataset-projects', data.datasetuid] })
      }
    },
    onError: (err) => {
      message.error(t(err.response?.data?.detail) || t('msg.save.error'))
    },
  })
}

export function useDatasetProjectsState(datasetuid) {
  const { data: projectData } = useDatasetProjects(datasetuid)
  const { data: availProjects = [] } = useAvailableProjects()

  const projects = datasetuid ? (projectData?.projects || []) : availProjects
  const [checkedProjectids, setCheckedProjectids] = useState([])

  useEffect(() => {
    setCheckedProjectids(projectData?.mapped_projectids || [])
  }, [projectData])

  const toggle = (pid) =>
    setCheckedProjectids((prev) =>
      prev.includes(pid) ? prev.filter((id) => id !== pid) : [...prev, pid]
    )

  return { projects, checkedProjectids, toggle, setCheckedProjectids }
}
