import { useLangStore, t } from '@/stores/langStore'
import BillingHistoryPanel from '@/components/payment/BillingHistoryPanel'

export default function BillingHistoryPage() {
  useLangStore((s) => s.translations)

  return <BillingHistoryPanel pageTitle={t('ttl.tenant.manage.billing_history')} />
}
