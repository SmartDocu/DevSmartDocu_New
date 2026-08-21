import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'

export function useAdminProducts() {
  return useQuery({
    queryKey: ['admin-products'],
    queryFn: () => apiClient.get('/admin/products').then((r) => r.data),
  })
}

export function useSaveAdminProduct() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ isNew, productcd, ...body }) =>
      isNew
        ? apiClient.post('/admin/products', { productcd, ...body }).then((r) => r.data)
        : apiClient.put(`/admin/products/${productcd}`, { productcd, ...body }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-products'] })
    },
  })
}

export function useDeleteAdminProduct() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (productcd) => apiClient.delete(`/admin/products/${productcd}`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-products'] })
    },
  })
}

export function useSaveAdminProductPrice() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ productcd, price, currencycd = 'KRW', effectivefromdt }) =>
      apiClient.post(`/admin/products/${productcd}/price`, { price, currencycd, effectivefromdt }).then((r) => r.data),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: ['admin-products'] })
      qc.invalidateQueries({ queryKey: ['admin-product-price-history', variables.productcd] })
    },
  })
}

export function useAdminProductPriceHistory(productcd) {
  return useQuery({
    queryKey: ['admin-product-price-history', productcd],
    queryFn: () => apiClient.get(`/admin/products/${productcd}/price-history`).then((r) => r.data),
    enabled: !!productcd,
  })
}
