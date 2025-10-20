import React, { useState, useRef, useEffect } from 'react'
import { apiFetch } from '../../services/api'

export default function Chat() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Bonjour, comment puis-je vous aider ?' }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [chartMode, setChartMode] = useState(false)
  const listRef = useRef(null)

  useEffect(() => {
    if (!listRef.current) return
    listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages, loading])

  function onToggleChartMode(e) {
    setChartMode(Boolean(e.target.checked))
    setError('')
  }

  async function onSend() {
    const text = input.trim()
    if (!text || loading) return

    setError('')
    const userMessage = { role: 'user', content: text }
    const nextMessages = [...messages, userMessage]
    setMessages(nextMessages)
    setInput('')
    setLoading(true)

    try {
      if (chartMode) {
        const res = await apiFetch('/mcp/chart', {
          method: 'POST',
          body: JSON.stringify({ prompt: text })
        })
        const chartUrl = typeof res?.chart_url === 'string' ? res.chart_url : ''
        const assistantMessage = chartUrl
          ? {
              role: 'assistant',
              content: chartUrl,
              chartUrl,
              chartTitle: res?.chart_title || '',
              chartDescription: res?.chart_description || '',
              chartTool: res?.tool_name || ''
            }
          : {
              role: 'assistant',
              content: "Impossible de générer un graphique."
            }
        setMessages(prev => [...prev, assistantMessage])
      } else {
        const res = await apiFetch('/chat/completions', {
          method: 'POST',
          body: JSON.stringify({ messages: nextMessages })
        })
        const reply = res?.reply ?? ''
        setMessages(prev => [...prev, { role: 'assistant', content: reply }])
      }
    } catch (e) {
      console.error(e)
      setError(e?.message || 'Erreur inconnue')
    } finally {
      setLoading(false)
    }
  }

  function onKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
    }
  }

  function onReset() {
    setMessages([{ role: 'assistant', content: 'Conversation réinitialisée. Que puis-je faire ?' }])
    setError('')
  }

  return (
    <section>
      <div style={styles.header}>
        <h2>Chat</h2>
        <label style={styles.toggle}>
          <input
            type="checkbox"
            checked={chartMode}
            onChange={onToggleChartMode}
          />
          <span>Activer MCP Chart</span>
        </label>
      </div>
      <div style={styles.container}>
        <div ref={listRef} style={styles.list}>
          {messages.map((m, i) => (
            <Message
              key={i}
              role={m.role}
              content={m.content}
              chartUrl={m.chartUrl}
              chartTitle={m.chartTitle}
              chartDescription={m.chartDescription}
              chartTool={m.chartTool}
            />
          ))}
          {loading && <div style={styles.loading}>Le modèle écrit…</div>}
        </div>

        {error && (
          <div style={styles.error}>
            {error}
          </div>
        )}

        <div style={styles.inputBox}>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Écrivez votre message…"
            rows={3}
            style={styles.textarea}
          />
          <div style={styles.actions}>
            <button onClick={onSend} disabled={loading || !input.trim()} style={styles.buttonPrimary}>
              Envoyer
            </button>
            <button onClick={onReset} disabled={loading} style={styles.buttonSecondary}>
              Réinitialiser
            </button>
          </div>
        </div>
      </div>
    </section>
  )
}

function Message({ role, content, chartUrl, chartTitle, chartDescription, chartTool }) {
  const isUser = role === 'user'
  const containerStyle = {
    ...styles.msg,
    ...(isUser ? styles.msgUser : styles.msgAssistant)
  }

  return (
    <div style={containerStyle}>
      <div style={styles.msgHeader}>{isUser ? 'Vous' : 'Assistant'}</div>
      {!isUser && chartUrl ? (
        <div style={styles.chartWrapper}>
          {chartTitle && <div style={styles.chartTitle}>{chartTitle}</div>}
          <a href={chartUrl} target="_blank" rel="noreferrer" style={styles.chartLink}>{chartUrl}</a>
          <img
            src={chartUrl}
            alt={chartTitle || 'Graphique MCP'}
            style={styles.chartImage}
          />
          {chartDescription && <div style={styles.chartDescription}>{chartDescription}</div>}
          {chartTool && <div style={styles.chartMeta}>Outil&nbsp;: {chartTool}</div>}
        </div>
      ) : (
        <div>{content}</div>
      )}
    </div>
  )
}

const styles = {
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8
  },
  toggle: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    fontSize: 14,
    color: '#111827'
  },
  container: {
    border: '1px solid #e5e7eb',
    borderRadius: 8,
    padding: 12,
    display: 'flex',
    flexDirection: 'column',
    gap: 8
  },
  list: {
    height: 320,
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    paddingRight: 4
  },
  msg: {
    borderRadius: 6,
    padding: '8px 10px',
    maxWidth: '75%'
  },
  msgUser: {
    alignSelf: 'flex-end',
    background: '#eef2ff',
    border: '1px solid #c7d2fe'
  },
  msgAssistant: {
    alignSelf: 'flex-start',
    background: '#f9fafb',
    border: '1px solid #e5e7eb'
  },
  msgHeader: {
    fontSize: 12,
    color: '#6b7280',
    marginBottom: 4
  },
  inputBox: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8
  },
  textarea: {
    width: '100%',
    resize: 'vertical',
    border: '1px solid #e5e7eb',
    borderRadius: 6,
    padding: 8,
    fontFamily: 'inherit',
    fontSize: 14
  },
  actions: {
    display: 'flex',
    gap: 8,
    justifyContent: 'flex-end'
  },
  buttonPrimary: {
    padding: '8px 12px',
    background: '#111827',
    color: 'white',
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer'
  },
  buttonSecondary: {
    padding: '8px 12px',
    background: 'white',
    color: '#111827',
    border: '1px solid #e5e7eb',
    borderRadius: 6,
    cursor: 'pointer'
  },
  loading: {
    alignSelf: 'center',
    color: '#6b7280',
    fontSize: 14
  },
  error: {
    background: '#fef2f2',
    color: '#991b1b',
    border: '1px solid #fecaca',
    borderRadius: 6,
    padding: 8
  },
  chartWrapper: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8
  },
  chartLink: {
    fontSize: 13,
    color: '#1f2937',
    wordBreak: 'break-all'
  },
  chartTitle: {
    fontSize: 14,
    fontWeight: 600,
    color: '#111827'
  },
  chartDescription: {
    fontSize: 12,
    color: '#374151'
  },
  chartMeta: {
    fontSize: 12,
    color: '#6b7280'
  },
  chartImage: {
    width: '100%',
    height: 'auto',
    borderRadius: 6,
    border: '1px solid #e5e7eb'
  }
}
