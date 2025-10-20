import React, { useState, useRef, useEffect } from 'react'
import { apiFetch } from '../../services/api'

export default function Chat() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Bonjour, comment puis-je vous aider ?', metadata: null }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const listRef = useRef(null)

  useEffect(() => {
    if (!listRef.current) return
    listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages, loading])

  async function onSend() {
    const text = input.trim()
    if (!text || loading) return
    setError('')
    const nextMessages = [...messages, { role: 'user', content: text, metadata: null }]
    setMessages(nextMessages)
    setInput('')
    setLoading(true)
    try {
      const res = await apiFetch('/chat/completions', {
        method: 'POST',
        body: JSON.stringify({
          messages: nextMessages.map(m => ({ role: m.role, content: m.content }))
        })
      })
      const reply = res?.reply ?? ''
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: reply, metadata: res?.metadata ?? null }
      ])
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
    setMessages([{ role: 'assistant', content: 'Conversation réinitialisée. Que puis-je faire ?', metadata: null }])
    setError('')
  }

  return (
    <section>
      <div style={styles.header}>
        <h2>Chat</h2>
        <div style={styles.hint}>Commandes : `/sql`, `/chart list`, `/chart nps`, `/chart support`, …</div>
      </div>
      <div style={styles.container}>
        <div ref={listRef} style={styles.list}>
          {messages.map((m, i) => (
            <Message key={i} role={m.role} content={m.content} metadata={m.metadata} />
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

function Message({ role, content, metadata }) {
  const isUser = role === 'user'
  const chartItems = Array.isArray(metadata?.charts)
    ? metadata.charts.filter(chart => chart?.chart_url)
    : []
  return (
    <div style={{
      ...styles.msg,
      ...(isUser ? styles.msgUser : styles.msgAssistant)
    }}>
      <div style={styles.msgHeader}>{isUser ? 'Vous' : 'Assistant'}</div>
      <div style={styles.msgContent}>{content}</div>
      {chartItems.length > 0 && (
        <div style={styles.chartGrid}>
          {chartItems.map(chart => (
            <div key={chart.key} style={styles.chartCard}>
              <div style={styles.chartMeta}>
                <div style={styles.chartTitle}>{chart.title}</div>
                <div style={styles.chartDataset}>{chart.dataset}</div>
                {chart.description && (
                  <div style={styles.chartDescription}>{chart.description}</div>
                )}
                <a href={chart.chart_url} target="_blank" rel="noreferrer" style={styles.chartLink}>
                  Ouvrir dans un nouvel onglet
                </a>
              </div>
              <img
                src={chart.chart_url}
                alt={chart.title}
                style={styles.chartImage}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const styles = {
  header: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    marginBottom: 8
  },
  hint: {
    fontSize: 12,
    color: '#6b7280'
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
  msgContent: {
    whiteSpace: 'pre-wrap',
    lineHeight: 1.4,
    fontSize: 14,
    color: '#111827'
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
  chartGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
    gap: 12,
    marginTop: 12
  },
  chartCard: {
    border: '1px solid #e5e7eb',
    borderRadius: 8,
    overflow: 'hidden',
    background: '#ffffff',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    padding: 12
  },
  chartMeta: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4
  },
  chartTitle: {
    fontSize: 14,
    fontWeight: 600,
    color: '#111827'
  },
  chartDataset: {
    fontSize: 12,
    color: '#6b7280'
  },
  chartDescription: {
    fontSize: 12,
    color: '#374151'
  },
  chartImage: {
    width: '100%',
    height: 'auto',
    borderRadius: 6,
    border: '1px solid #e5e7eb'
  },
  chartLink: {
    fontSize: 12,
    color: '#2563eb',
    textDecoration: 'none'
  }
}
