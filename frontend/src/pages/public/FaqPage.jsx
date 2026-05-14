import { Spin, Collapse } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useLangStore, t } from '@/stores/langStore'
import apiClient from '@/api/client'

export default function FaqPage() {
  useLangStore((s) => s.translations)

  const { data, isLoading } = useQuery({
    queryKey: ['faqs'],
    queryFn: () => apiClient.get('/misc/faqs').then((r) => r.data.faqs),
  })
  const faqs = data || []


  return (
    <div>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="gradient-bar" />
          <div>FAQ</div>
        </div>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
      ) : faqs.length === 0 ? (
        <div style={{ padding: 24, color: '#888', textAlign: 'center' }}>{t('msg.no.data')}</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {faqs.map((promptkey) => (
            <Collapse
              key={promptkey}
              items={[{
                key: promptkey,
                label: t(`faq.${promptkey}_title`),
                children: (
                  <div>
                    {t(`faq.${promptkey}_text1`) !== `faq.${promptkey}_text1` && (
                      <div style={{ marginBottom: 8 }}>
                        <strong>{t('lbl.question')}:</strong> {t(`faq.${promptkey}_text1`)}
                      </div>
                    )}
                    <div>
                      <strong>{t('lbl.answer')}:</strong>{' '}
                      <span dangerouslySetInnerHTML={{ __html: t(`faq.${promptkey}_text2`) }} />
                    </div>
                  </div>
                ),
              }]}
            />
          ))}
        </div>
      )}
    </div>
  )
}
