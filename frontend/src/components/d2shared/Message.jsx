import chatbotBot   from '@/assets/icons/chatbot_bot.svg'
import chatbotHuman from '@/assets/icons/chatbot_human.svg'

/**
 * d2chat · d2insight 공통 말풍선 컴포넌트
 *
 * Props
 *   role             : 'user' | 'assistant'
 *   content          : 텍스트 내용
 *   visualization    : Base64 PNG 문자열(chart) 또는 HTML 문자열(table)
 *   visualizationType: 'chart' | 'table' | 'none' | null
 *   starButton       : 즐겨찾기 버튼 ReactNode (MessageList에서 주입)
 *   showIcon         : 아이콘 표시 여부 — d2chat: true(기본), d2insight: false
 *   reportSlot       : 보고서 카드 ReactNode — d2insight 전용 (ReportCard 등)
 */
export default function Message({
  role,
  content,
  visualization,
  visualizationType,
  starButton,
  showIcon = true,
  reportSlot,
}) {
  return (
    <div className={`message ${role}`}>
      {showIcon && role === 'assistant' && (
        <img src={chatbotBot} className="assistant-icon" alt="bot" />
      )}

      {role === 'user' && starButton}

      <div className="message-content">
        {content}

        {visualization && (
          <div className="visualization-container">
            {visualizationType === 'table'
              ? <div dangerouslySetInnerHTML={{ __html: visualization }} />
              : <img src={`data:image/png;base64,${visualization}`} alt="차트" />
            }
          </div>
        )}

        {reportSlot}
      </div>

      {showIcon && role === 'user' && (
        <img src={chatbotHuman} className="user-icon" alt="user" />
      )}
    </div>
  )
}
