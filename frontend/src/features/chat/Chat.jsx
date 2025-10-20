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
  const [charts, setCharts] = useState([])
  const [chartsLoading, setChartsLoading] = useState(false)
  const [chartsError, setChartsError] = useState('')
  const listRef = useRef(null)

  useEffect(() => {
    if (!listRef.current) return
    listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages, loading])

  async function fetchCharts() {
    setChartsError('')
    setChartsLoading(true)
    try {
      const res = await apiFetch('/mcp/charts')
      const items = Array.isArray(res?.charts) ? res.charts : []
      setCharts(items)
    } catch (e) {
      console.error(e)
      setChartsError(e?.message || 'Impossible de générer les graphiques')
    } finally {
      setChartsLoading(false)
    }
  }

  function onToggleChartMode(e) {
    const next = Boolean(e.target.checked)
    setChartMode(next)
    setCharts([])
    setChartsError('')
    if (next) {
      fetchCharts()
    }
  }

  async function onSend() {
    const text = input.trim()
    if (!text || loading) return
    setError('')
    const next = [...messages, { role: 'user', content: text }]
    setMessages(next)
    setInput('')
    setLoading(true)
    try {
      const res = await apiFetch('/chat/completions', {
        method: 'POST',
        body: JSON.stringify({ messages: next })
      })
      const reply = res?.reply ?? ''
      setMessages(prev => [...prev, { role: 'assistant', content: reply }])
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
        {chartMode && (
          <div style={styles.chartsSection}>
            <div style={styles.chartsHeader}>
              <div style={styles.chartsTitle}>Visualisations depuis MCP Chart</div>
              <button
                onClick={fetchCharts}
                disabled={chartsLoading}
                style={styles.buttonSecondary}
              >
                Actualiser
              </button>
            </div>
            {chartsLoading && <div style={styles.loading}>Génération des graphiques…</div>}
            {chartsError && (
              <div style={styles.error}>
                {chartsError}
              </div>
            )}
            {!chartsLoading && !chartsError && charts.length === 0 && (
              <div style={styles.emptyCharts}>Aucune visualisation disponible.</div>
            )}
            {!chartsLoading && !chartsError && charts.length > 0 && (
              <div style={styles.chartsGrid}>
                {charts.map(chart => (
                  <div key={chart.key} style={styles.chartCard}>
                    <div style={styles.chartMeta}>
                      <div style={styles.chartTitle}>{chart.title}</div>
                      <div style={styles.chartDataset}>{chart.dataset}</div>
                      {chart.description && (
                        <div style={styles.chartDescription}>{chart.description}</div>
                      )}
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
        )}

        <div ref={listRef} style={styles.list}>
          {messages.map((m, i) => (
            <Message key={i} role={m.role} content={m.content} />
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

function Message({ role, content }) {
  const isUser = role === 'user'
  return (
    <div style={{
      ...styles.msg,
      ...(isUser ? styles.msgUser : styles.msgAssistant)
    }}>
      <div style={styles.msgHeader}>{isUser ? 'Vous' : 'Assistant'}</div>
      <div>{content}</div>
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
  chartsSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
    marginBottom: 12
  },
  chartsHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  chartsTitle: {
    fontSize: 16,
    fontWeight: 600,
    color: '#111827'
  },
  chartsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
    gap: 12
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
  emptyCharts: {
    fontSize: 13,
    color: '#6b7280'
  }
}
