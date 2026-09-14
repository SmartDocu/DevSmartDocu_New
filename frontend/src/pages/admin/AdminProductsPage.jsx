import { useEffect, useState } from 'react'
import { App, Select, DatePicker, Pagination } from 'antd'
import { PlusOutlined, SaveOutlined, DeleteOutlined, CheckCircleFilled } from '@ant-design/icons'
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
import { getErrorMessage } from '@/utils/apiError'

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

const PAGE_SIZE = 14

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
      message.error(getErrorMessage(err, 'msg.save.error'))
    }
  }

  const handleDelete = () => {
    if (!selectedProductcd) return
    modal.confirm({
      content: t('msg.confirm.delete'),
      onOk: () => {
        deleteProduct.mutate(selectedProductcd, {
          onSuccess: () => { message.success(t('msg.delete.success')); handleNew() },
          onError: (err) => { message.error(getErrorMessage(err, 'msg.delete.error')) },
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

  const [page, setPage] = useState(1)
  useEffect(() => { setPage(1) }, [searchText, filterServicecd])
  const pagedProducts = filteredProducts.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const previewTax = priceInput !== '' ? Math.round(Number(priceInput) * 0.1) : null
  const previewUnitPrice = priceInput !== '' ? Math.round(Number(priceInput) - (previewTax || 0)) : null

  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{
            display: 'block', width: 6, height: 28, marginRight: 10, flexShrink: 0,
            borderRadius: 4, background: 'linear-gradient(180deg, var(--primary-600) 0%, var(--primary-800) 100%)',
          }} />
          <div>{t('ttl.system.products')}</div>
        </div>
      </div>

      {/* 필터 */}
      <div className="panel-section" style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
        <div className="filter-item">
          <label style={{ fontWeight: 'bold' }}>{t('lbl.servicecd')}</label>
          <div className="segmented" style={{ height: 32 }}>
            {[['all', t('cod.filter_all')], ...serviceCodes.map((c) => [c.codevalue, t(c.term_key) || c.default_name])].map(([v, lbl]) => (
              <button
                key={v}
                type="button"
                className={`segmented-item${filterServicecd === v ? ' active' : ''}`}
                style={{ padding: '0 14px', display: 'flex', alignItems: 'center' }}
                onClick={() => setFilterServicecd(v)}
              >
                {lbl}
              </button>
            ))}
          </div>
        </div>
        <div className="filter-item" style={{ marginLeft: 24 }}>
          <label style={{ fontWeight: 'bold' }}>{t('lbl.productcd')}</label>
          <input
            type="text"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ height: 32, width: 200 }}
          />
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
        {/* 좌측: 상품 목록 */}
        <div className="panel-section" style={{ flex: 2, height: 'calc(100vh - 306px)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', height: 60, flexShrink: 0,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h3 style={{ margin: 0, lineHeight: 1 }}>{t('ttl.list')}</h3>
              <span style={{
                display: 'inline-flex', alignItems: 'center', lineHeight: 1,
                font: '500 11px monospace', color: '#8d9199', background: '#f2efe9',
                borderRadius: 6, padding: '5px 8px 4px',
              }}>
                {t('lbl.count.docs').replace('{n}', filteredProducts.length)}
              </span>
            </div>
            <button className="btn btn-primary" type="button" onClick={handleNew}>
              <PlusOutlined style={{ marginRight: 6 }} />{t('btn.new')}
            </button>
          </div>
          <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
            <table className="table table-bordered table-sm" style={{ cursor: 'pointer', tableLayout: 'fixed', width: '100%' }}>
              <thead>
                <tr>
                  <th style={{ width: '20%' }}>{t('lbl.productcd')}</th>
                  <th style={{ width: '24%' }}>{t('lbl.productnm')}</th>
                  <th style={{ width: '7%' }}>{t('lbl.service_name_lbl')}</th>
                  <th style={{ width: '8%' }}>{t('lbl.plan')}</th>
                  <th style={{ width: '12%' }}>{t('lbl.price')}</th>
                  <th style={{ width: '5%', textAlign: 'center' }}>{t('lbl.useyn_lbl')}</th>
                  <th style={{ width: '5%', textAlign: 'center' }}>{t('lbl.is_sales')}</th>
                  <th style={{ width: '10%' }}>{t('lbl.effectivefromdt')}</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={8} style={{ textAlign: 'center' }}>{t('msg.loading')}</td></tr>
                ) : filteredProducts.length === 0 ? (
                  <tr><td colSpan={8} style={{ textAlign: 'center', color: '#888' }}>{t('msg.no.data')}</td></tr>
                ) : pagedProducts.map((p) => (
                  <tr
                    key={p.productcd}
                    className={selectedProductcd === p.productcd ? 'selected-row' : ''}
                    onClick={() => handleSelect(p)}
                  >
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={p.productcd}>{p.productcd}</td>
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={p.productnm}>{p.productnm}</td>
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.servicecd ? codeLabel(serviceCodes, p.servicecd) : '-'}</td>
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.plancd ? codeLabel(planCodes, p.plancd) : '-'}</td>
                    <td style={{ textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.price != null ? `${Number(p.price).toLocaleString()} ${p.currencycd}` : '-'}</td>
                    <td style={{ textAlign: 'center' }}>{p.useyn && <CheckCircleFilled style={{ color: '#2f7d4f' }} title={t('lbl.useyn_lbl')} />}</td>
                    <td style={{ textAlign: 'center' }}>{p.is_sales && <CheckCircleFilled style={{ color: '#2f7d4f' }} title={t('lbl.is_sales')} />}</td>
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.effectivefromdt || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filteredProducts.length > PAGE_SIZE && (
            <div style={{ marginTop: 'auto', paddingTop: 12, display: 'flex', justifyContent: 'center' }}>
              <Pagination
                current={page}
                pageSize={PAGE_SIZE}
                total={filteredProducts.length}
                showSizeChanger={false}
                onChange={setPage}
              />
            </div>
          )}
        </div>

        {/* 우측: 상세 폼 */}
        <div className="panel-section" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: 'calc(100vh - 306px)' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, height: 60,
            margin: '-16px -18px 16px', padding: '16px 18px 12px',
            borderBottom: '1px solid var(--border-color, #e3e6eb)',
          }}>
            <h3 style={{ margin: 0 }}>{t('ttl.detail')}</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button className="btn btn-primary" type="button" onClick={handleSave} disabled={saveProduct.isPending || savePrice.isPending || deleteProduct.isPending}>
                <SaveOutlined style={{ marginRight: 6 }} />{t('btn.save')}
              </button>
              {!isNew && (
                <button
                  className="btn btn-danger"
                  type="button"
                  onClick={handleDelete}
                  disabled={deleteProduct.isPending}
                  title={t('btn.delete')}
                  style={{ width: 38, height: 38, padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                >
                  <DeleteOutlined />
                </button>
              )}
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>

          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.productcd')}:</label>
            {isNew ? (
              <input type="text" value={form.productcd} style={{ height: 38 }} onChange={(e) => setForm((f) => ({ ...f, productcd: e.target.value }))} />
            ) : (
              <span style={{ padding: '6px 4px', fontWeight: 600 }}>{form.productcd}</span>
            )}
          </div>

          <div className="form-group">
            <label><span style={{ color: 'red', marginRight: 2 }}>*</span>{t('lbl.productnm')}:</label>
            <input type="text" value={form.productnm} style={{ height: 38 }} onChange={(e) => setForm((f) => ({ ...f, productnm: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.service_name_lbl')}:</label>
            <Select
              allowClear
              style={{ width: '100%', height: 38 }}
              value={form.servicecd}
              onChange={(v) => setForm((f) => ({ ...f, servicecd: v ?? null }))}
              options={serviceCodes.map((c) => ({ value: c.codevalue, label: t(c.term_key) || c.default_name }))}
            />
          </div>

          <div className="form-group">
            <label>{t('lbl.plan')}:</label>
            <Select
              allowClear
              style={{ width: '100%', height: 38 }}
              value={form.plancd}
              onChange={(v) => setForm((f) => ({ ...f, plancd: v ?? null }))}
              options={planCodes.map((c) => ({ value: c.codevalue, label: t(c.term_key) || c.default_name }))}
            />
          </div>

          <div className="form-group">
            <label>{t('thd.producttype_thd')}:</label>
            <Select
              allowClear
              style={{ width: '100%', height: 38 }}
              value={form.producttype}
              onChange={(v) => setForm((f) => ({ ...f, producttype: v ?? null }))}
              options={producttypeCodes.map((c) => ({ value: c.codevalue, label: t(c.term_key) || c.default_name }))}
            />
          </div>

          <div className="form-group">
            <label>{t('lbl.billingtermcd')}:</label>
            <Select
              allowClear
              style={{ width: '100%', height: 38 }}
              value={form.billingtermcd}
              onChange={(v) => setForm((f) => ({ ...f, billingtermcd: v ?? null }))}
              options={billingtermCodes.map((c) => ({ value: c.codevalue, label: t(c.term_key) || c.default_name }))}
            />
          </div>

          <div className="form-group">
            <label>{t('lbl.users')}:</label>
            <input type="number" value={form.users} style={{ height: 38 }} onChange={(e) => setForm((f) => ({ ...f, users: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.credit')}:</label>
            <input type="number" value={form.credit} style={{ height: 38 }} onChange={(e) => setForm((f) => ({ ...f, credit: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.expiremonths')}:</label>
            <input type="number" value={form.expiremonths} style={{ height: 38 }} onChange={(e) => setForm((f) => ({ ...f, expiremonths: e.target.value }))} />
          </div>

          <div className="form-group">
            <label>{t('lbl.orderno_lbl')}:</label>
            <input type="number" value={form.orderno} style={{ height: 38 }} onChange={(e) => setForm((f) => ({ ...f, orderno: e.target.value }))} />
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
              <input type="number" value={priceInput} style={{ height: 38 }} onChange={(e) => setPriceInput(e.target.value)} />
            </div>
            <div className="form-group">
              <label>{t('lbl.effectivefromdt')}:</label>
              <DatePicker
                style={{ width: '100%', height: 38 }}
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
              <div className="table-container" style={{ height: 'auto', overflowY: 'visible' }}>
                <table className="table table-bordered table-sm">
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
    </div>
  )
}
