import { useState } from 'react'
import { App, Select, DatePicker } from 'antd'
import dayjs from 'dayjs'
import { useLangStore, t } from '@/stores/langStore'
import { useMenuCodes } from '@/hooks/useMenus'
import {
  useAdminProducts,
  useSaveAdminProduct,
  useDeleteAdminProduct,
  useSaveAdminProductPrice,
  useAdminProductPriceHistory,
} from '@/hooks/useProducts'

const EMPTY_PRODUCT = {
  productcd: '',
  productnm: '',
  servicecd: null,
  plancd: null,
  producttype: null,
  billingtermcd: null,
  users: '',
  credit: '',
  expiremonths: '',
  orderno: '',
  useyn: true,
  is_sales: true,
  is_customeraikey: false,
}

function getErrorMessage(err, fallback) {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => d?.msg || JSON.stringify(d)).join(', ')
  return fallback
}

export default function AdminProductsPage() {
  const { message, modal } = App.useApp()
  useLangStore((s) => s.translations)

  const { data = {}, isLoading } = useAdminProducts()
  const products = data.products || []

  const { data: serviceCodes = [] } = useMenuCodes('servicecd')
  const { data: planCodes = [] } = useMenuCodes('plancd')
  const { data: producttypeCodes = [] } = useMenuCodes('producttype')
  const { data: billingtermCodes = [] } = useMenuCodes('billingtermcd')

  const [selectedProductcd, setSelectedProductcd] = useState(null)
  const [isNew, setIsNew] = useState(true)
  const [form, setForm] = useState(EMPTY_PRODUCT)
  const [priceInput, setPriceInput] = useState('')
  const [priceEffectiveFrom, setPriceEffectiveFrom] = useState(dayjs())
  const [searchText, setSearchText] = useState('')
  const [filterServicecd, setFilterServicecd] = useState('all')

  const saveProduct = useSaveAdminProduct()
  const deleteProduct = useDeleteAdminProduct()
  const savePrice = useSaveAdminProductPrice()
  const { data: priceHistoryData = {} } = useAdminProductPriceHistory(!isNew ? selectedProductcd : null)
  const priceHistory = priceHistoryData.history || []

  const codeLabel = (codes, cd) => {
    const found = codes.find((c) => c.codevalue === cd)
    return found ? (t(found.term_key) || found.default_name) : cd
  }

  const handleNew = () => {
    setSelectedProductcd(null)
    setIsNew(true)
    setForm(EMPTY_PRODUCT)
    setPriceInput('')
    setPriceEffectiveFrom(dayjs())
  }

  const handleSelect = (p) => {
    setSelectedProductcd(p.productcd)
    setIsNew(false)
    setForm({
      productcd: p.productcd,
      productnm: p.productnm || '',
      servicecd: p.servicecd || null,
      plancd: p.plancd || null,
      producttype: p.producttype || null,
      billingtermcd: p.billingtermcd || null,
      users: p.users ?? '',
      credit: p.credit ?? '',
      expiremonths: p.expiremonths ?? '',
      orderno: p.orderno ?? '',
      useyn: p.useyn ?? true,
      is_sales: p.is_sales ?? true,
      is_customeraikey: p.is_customeraikey ?? false,
    })
    setPriceInput(p.price != null ? String(p.price) : '')
    setPriceEffectiveFrom(dayjs())
  }

  const handleSave = async () => {
    if (!form.productcd.trim()) { message.warning(t('msg.product.productcd.required')); return }
    if (!form.productnm.trim()) { message.warning(t('msg.product.productnm.required')); return }

    const body = {
      productnm: form.productnm,
      servicecd: form.servicecd || null,
      plancd: form.plancd || null,
      producttype: form.producttype || null,
      billingtermcd: form.billingtermcd || null,
      users: form.users === '' ? null : Number(form.users),
      credit: form.credit === '' ? null : Number(form.credit),
      expiremonths: form.expiremonths === '' ? null : Number(form.expiremonths),
      orderno: form.orderno === '' ? null : Number(form.orderno),
      useyn: form.useyn,
      is_sales: form.is_sales,
      is_customeraikey: form.is_customeraikey,
    }

    try {
      await saveProduct.mutateAsync({ isNew, productcd: form.productcd, ...body })
      if (priceInput !== '' && form.billingtermcd) {
        await savePrice.mutateAsync({
          productcd: form.productcd,
          price: Number(priceInput),
          effectivefromdt: priceEffectiveFrom.format('YYYY-MM-DD'),
        })
      }
      message.success(t('msg.save.success'))
      setIsNew(false)
      setSelectedProductcd(form.productcd)
    } catch (err) {
      message.error(getErrorMessage(err, t('msg.save.error')))
    }
  }

  const handleDelete = () => {
    if (!selectedProductcd) return
    modal.confirm({
      content: t('msg.confirm.delete'),
      onOk: () => {
        deleteProduct.mutate(selectedProductcd, {
          onSuccess: () => { message.success(t('msg.delete.success')); handleNew() },
          onError: (err) => { message.error(getErrorMessage(err, t('msg.delete.error'))) },
        })
      },
    })
  }

  const filteredProducts = products.filter((p) => {
    if (filterServicecd !== 'all' && p.servicecd !== filterServicecd) return false
    const q = searchText.trim().toLowerCase()
    if (!q) return true
    return p.productcd?.toLowerCase().includes(q) || p.productnm?.toLowerCase().includes(q)
  })

  const previewTax = priceInput !== '' ? Math.round(Number(priceInput) * 0.1) : null
  const previewUnitPrice = priceInput !== '' ? Math.round(Number(priceInput) - (previewTax || 0)) : null

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>{t('ttl.system.products')}</div>
        </div>
      </div>

      {/* 필터 */}
      <div className="form-filter-group">
        <div className="filter-item">
          <label style={{ width: 'auto', marginRight: 16 }}>{t('lbl.servicecd')}:</label>
          {[['all', t('cod.filter_all')], ...serviceCodes.map((c) => [c.codevalue, t(c.term_key) || c.default_name])].map(([v, lbl]) => (
            <span key={v} style={{ marginRight: 16 }}>
              <input type="radio" id={`svcfilter_${v}`} name="serviceFilter" value={v}
                checked={filterServicecd === v} onChange={() => setFilterServicecd(v)} />
              <label className="radio-label" htmlFor={`svcfilter_${v}`} style={{ width: 'auto', marginRight: 0 }}>{lbl}</label>
            </span>
          ))}
        </div>
      </div>

      {/* 270px = 표준 224px + 필터 행 높이(44px) + 여유 2px */}
      <div style={{ display: 'flex', gap: 20, paddingRight: 10 }}>
        {/* 좌측: 상품 목록 */}
        <div style={{ flex: 6 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.list')}</h3>
            <button className="btn btn-primary" type="button" onClick={handleNew}>{t('btn.new')}</button>
          </div>
          <input
            type="text"
            placeholder={t('lbl.productcd')}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: '100%', marginBottom: 8, boxSizing: 'border-box' }}
          />
          {/* 350px = 270px + 목록 헤더 행(40px) + 검색창(40px) — 테이블 내부에서만 스크롤되게 함 */}
          <div className="table-container" style={{ overflowY: 'auto', maxHeight: 'calc(100vh - 350px)' }}>
            <table>
              <thead>
                <tr>
                  <th>{t('lbl.productcd')}</th>
                  <th>{t('lbl.productnm')}</th>
                  <th>{t('lbl.service_name_lbl')}</th>
                  <th>{t('lbl.plan')}</th>
                  <th>{t('lbl.price')}</th>
                  <th style={{ textAlign: 'center' }}>{t('lbl.useyn_lbl')}</th>
                  <th style={{ textAlign: 'center' }}>{t('lbl.is_sales')}</th>
                  <th>{t('lbl.effectivefromdt')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={8} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : filteredProducts.length === 0 ? (
                  <tr><td colSpan={8} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : filteredProducts.map((p) => (
                  <tr
                    key={p.productcd}
                    className={selectedProductcd === p.productcd ? 'selected-row' : ''}
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleSelect(p)}
                  >
                    <td>{p.productcd}</td>
                    <td>{p.productnm}</td>
                    <td>{p.servicecd ? codeLabel(serviceCodes, p.servicecd) : '-'}</td>
                    <td>{p.plancd ? codeLabel(planCodes, p.plancd) : '-'}</td>
                    <td style={{ textAlign: 'right' }}>{p.price != null ? `${Number(p.price).toLocaleString()} ${p.currencycd}` : '-'}</td>
                    <td style={{ textAlign: 'center' }}>{p.useyn ? '✔' : ''}</td>
                    <td style={{ textAlign: 'center' }}>{p.is_sales ? '✔' : ''}</td>
                    <td>{p.effectivefromdt || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 우측: 상세 폼 */}
        <div style={{ flex: 4, padding: '0 10px', overflowY: 'auto', maxHeight: 'calc(100vh - 270px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 32, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveProduct.isPending || savePrice.isPending}>
                {t('btn.save')}
              </button>
              <button className="btn btn-danger" type="button" onClick={handleDelete} disabled={deleteProduct.isPending || isNew}>
                {t('btn.delete')}
              </button>
            </div>
          </div>

          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.productcd')}:</label>
            {isNew ? (
              <input type="text" value={form.productcd} onChange={(e) => setForm((f) => ({ ...f, productcd: e.target.value }))} />
            ) : (
              <span style={{ padding: '6px 4px', fontWeight: 600 }}>{form.productcd}</span>
            )}
          </div>

          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.productnm')}:</label>
            <input type="text" value={form.productnm} onChange={(e) => setForm((f) => ({ ...f, productnm: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.service_name_lbl')}:</label>
            <Select
              allowClear
              style={{ width: '100%' }}
              value={form.servicecd}
              onChange={(v) => setForm((f) => ({ ...f, servicecd: v ?? null }))}
              options={serviceCodes.map((c) => ({ value: c.codevalue, label: t(c.term_key) || c.default_name }))}
            />
          </div>

          <div className="form-group">
            <label>{t('lbl.plan')}:</label>
            <Select
              allowClear
              style={{ width: '100%' }}
              value={form.plancd}
              onChange={(v) => setForm((f) => ({ ...f, plancd: v ?? null }))}
              options={planCodes.map((c) => ({ value: c.codevalue, label: t(c.term_key) || c.default_name }))}
            />
          </div>

          <div className="form-group">
            <label>{t('thd.producttype_thd')}:</label>
            <Select
              allowClear
              style={{ width: '100%' }}
              value={form.producttype}
              onChange={(v) => setForm((f) => ({ ...f, producttype: v ?? null }))}
              options={producttypeCodes.map((c) => ({ value: c.codevalue, label: t(c.term_key) || c.default_name }))}
            />
          </div>

          <div className="form-group">
            <label>{t('lbl.billingtermcd')}:</label>
            <Select
              allowClear
              style={{ width: '100%' }}
              value={form.billingtermcd}
              onChange={(v) => setForm((f) => ({ ...f, billingtermcd: v ?? null }))}
              options={billingtermCodes.map((c) => ({ value: c.codevalue, label: t(c.term_key) || c.default_name }))}
            />
          </div>

          <div className="form-group">
            <label>{t('lbl.users')}:</label>
            <input type="number" value={form.users} onChange={(e) => setForm((f) => ({ ...f, users: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.credit')}:</label>
            <input type="number" value={form.credit} onChange={(e) => setForm((f) => ({ ...f, credit: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.expiremonths')}:</label>
            <input type="number" value={form.expiremonths} onChange={(e) => setForm((f) => ({ ...f, expiremonths: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.orderno_lbl')}:</label>
            <input type="number" value={form.orderno} onChange={(e) => setForm((f) => ({ ...f, orderno: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.useyn_lbl')}:</label>
            <div style={{ paddingLeft: 60 }}>
              <input type="checkbox" checked={!!form.useyn} onChange={(e) => setForm((f) => ({ ...f, useyn: e.target.checked }))} />
            </div>
          </div>

          <div className="form-group">
            <label>{t('lbl.is_sales')}:</label>
            <div style={{ paddingLeft: 60 }}>
              <input type="checkbox" checked={!!form.is_sales} onChange={(e) => setForm((f) => ({ ...f, is_sales: e.target.checked }))} />
            </div>
          </div>

          <div className="form-group">
            <label>{t('lbl.is_customeraikey')}:</label>
            <div style={{ paddingLeft: 60 }}>
              <input type="checkbox" checked={!!form.is_customeraikey} onChange={(e) => setForm((f) => ({ ...f, is_customeraikey: e.target.checked }))} />
            </div>
          </div>

          <div style={{ border: '1px solid #eee', borderRadius: 6, padding: 12, marginTop: 12 }}>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>{t('lbl.price')} (KRW)</div>
            <div className="form-group">
              <label>{t('lbl.price')}:</label>
              <input type="number" value={priceInput} onChange={(e) => setPriceInput(e.target.value)} />
            </div>
            <div className="form-group">
              <label>{t('lbl.effectivefromdt')}:</label>
              <DatePicker
                style={{ width: '100%' }}
                value={priceEffectiveFrom}
                onChange={(d) => setPriceEffectiveFrom(d || dayjs())}
                allowClear={false}
              />
            </div>
            {priceInput !== '' && (
              <div style={{ fontSize: 12, color: '#888' }}>
                {t('lbl.unit_price')}: {previewUnitPrice?.toLocaleString()} · {t('lbl.unit_tax')}: {previewTax?.toLocaleString()}
              </div>
            )}
          </div>

          {!isNew && (
            <div style={{ marginTop: 16 }}>
              <h3 style={{ margin: '0 0 8px 0', fontSize: 15 }}>{t('ttl.price.history')}</h3>
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>{t('lbl.billingtermcd')}</th>
                      <th>{t('lbl.price')}</th>
                      <th>{t('lbl.effectivefromdt')}</th>
                      <th>{t('lbl.effectivetodt')}</th>
                      <th>{t('lbl.status')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {priceHistory.length === 0 ? (
                      <tr><td colSpan={5} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                    ) : priceHistory.map((h) => {
                      const today = dayjs().format('YYYY-MM-DD')
                      const status = h.effectivefromdt > today
                        ? t('lbl.price.scheduled')
                        : (h.effectivetodt && h.effectivetodt < today)
                          ? t('lbl.price.expired')
                          : t('lbl.price.current')
                      return (
                        <tr key={`${h.currencycd}-${h.billingtermcd}-${h.effectivefromdt}`}>
                          <td>{h.billingtermcd}</td>
                          <td style={{ textAlign: 'right' }}>{Number(h.price).toLocaleString()} {h.currencycd}</td>
                          <td>{h.effectivefromdt}</td>
                          <td>{h.effectivetodt || '-'}</td>
                          <td>{status}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
