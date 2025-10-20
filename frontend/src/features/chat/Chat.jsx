import React, { useState, useRef, useEffect } from 'react'
import { apiFetch } from '../../services/api'

const DEFAULT_PAYLOADS = {
  generate_bar_chart: JSON.stringify({
    data: [
      { category: 'Catégorie A', value: 12 },
      { category: 'Catégorie B', value: 18 },
      { category: 'Catégorie C', value: 9 }
    ],
    title: 'Comparaison par catégorie',
    axisXTitle: 'Catégorie',
    axisYTitle: 'Valeur'
  }, null, 2),
  generate_line_chart: JSON.stringify({
    data: [
      { time: '2025-01', value: 10 },
      { time: '2025-02', value: 15 },
      { time: '2025-03', value: 8 }
    ],
    title: 'Tendance mensuelle',
    axisXTitle: 'Période',
    axisYTitle: 'Valeur'
  }, null, 2),
  generate_pie_chart: JSON.stringify({
    data: [
      { category: 'Segment A', value: 35 },
      { category: 'Segment B', value: 42 },
      { category: 'Segment C', value: 23 }
    ],
    title: 'Répartition par segment'
  }, null, 2)
}

export default function Chat() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Bonjour, comment puis-je vous aider ?' }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [chartMode, setChartMode] = useState(false)
  const [chartTool, setChartTool] = useState('generate_bar_chart')
  const [chartPayload, setChartPayload] = useState(DEFAULT_PAYLOADS.generate_bar_chart)
  const [chartResult, setChartResult] = useState(null)
  const [chartError, setChartError] = useState('')
  const [chartLoading, setChartLoading] = useState(false)

  const listRef = useRef(null)

  useEffect(() => {
    if (!listRef.current) return
    listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages, loading])

  function onToggleChartMode(e) {
    const next = Boolean(e.target.checked)
    setChartMode(next)
    setChartResult(null)
    setChartError('')
    if (next) {
      setChartPayload(DEFAULT_PAYLOADS[chartTool] || DEFAULT_PAYLOADS.generate_bar_chart)
    }
  }

  function onSelectTool(e) {
    const nextTool = e.target.value
    setChartTool(nextTool)
    setChartPayload(DEFAULT_PAYLOADS[nextTool] || DEFAULT_PAYLOADS.generate_bar_chart)
  }

  async function onGenerateChart(event) {
    event.preventDefault()
    setChartError('')
    setChartResult(null)
    setChartLoading(true)
    let parsed
    try {
      parsed = JSON.parse(chartPayload)
      if (typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('Le JSON doit décrire un objet (ex: { "data": [...] }).')
      }
    } catch (err) {
      setChartLoading(false)
      setChartError(err?.message || 'Le JSON fourni est invalide.')
      return
    }

    try {
      const res = await apiFetch('/mcp/charts', {
        method: 'POST',
        body: JSON.stringify({ tool: chartTool, arguments: parsed })
      })
      setChartResult(res)
    } catch (err) {
      console.error(err)
      setChartError(err?.message || 'Impossible de générer le graphique.')
    } finally {
      setChartLoading(false)
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
    } catch (err) {
      console.error(err)
      setError(err?.message || 'Erreur inconnue')
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
          <span>Mode graphique MCP</span>
        </label>
      </div>

      {chartMode && (
        <form onSubmit={onGenerateChart} style={styles.chartForm}>
          <div style={styles.chartRow}>
            <label style={styles.chartLabel}>
              Type de graphique
              <select value={chartTool} onChange={onSelectTool} style={styles.select}>
                <option value="generate_bar_chart">Barres</option>
                <option value="generate_line_chart">Courbe</option>
                <option value="generate_pie_chart">Camembert</option>
              </select>
            </label>
            <button
              type="submit"
              disabled={chartLoading}
              style={styles.buttonPrimary}
            >
              {chartLoading ? 'Génération…' : 'Générer'}
            </button>
          </div>
          <label style={styles.chartLabel}>
            Paramètres (JSON)
            <textarea
              value={chartPayload}
              onChange={e => setChartPayload(e.target.value)}
              rows={10}
              style={styles.textarea}
            />
          </label>
          <div style={styles.help}>
            Fourissez un objet JSON conforme au schéma de l’outil AntV sélectionné.
            Exemple pour un graphique en barres:
            {` { "data": [{ "category": "A", "value": 10 }, ...] } `}
          </div>
          {chartError && <div style={styles.error}>{chartError}</div>}
          {chartResult && (
            <div style={styles.chartResult}>
              <div style={styles.chartMeta}>
                <div style={styles.chartTitle}>{chartResult?.spec?.title || 'Graphique généré'}</div>
                <a href={chartResult.chart_url} target="_blank" rel="noreferrer" style={styles.chartLink}>
                  Ouvrir dans un nouvel onglet
                </a>
              </div>
              <img
                src={chartResult.chart_url}
                alt={chartResult?.spec?.title || 'Graphique MCP'}
                style={styles.chartImage}
              />
            </div>
          )}
        </form>
      )}

      <div style={styles.container}>
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
    marginBottom: 12
  },
  toggle: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    fontSize: 14,
    color: '#111827'
  },
  chartForm: {
    border: '1px solid #e5e7eb',
    borderRadius: 8,
    padding: 16,
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
    marginBottom: 12,
    background: '#f9fafb'
  },
  chartRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12
  },
  chartLabel: {
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
    fontSize: 14,
    color: '#111827',
    flex: 1
  },
  select: {
    padding: '6px 8px',
    borderRadius: 6,
    border: '1px solid #d1d5db'
  },
  help: {
    fontSize: 12,
    color: '#6b7280'
  },
  chartResult: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    border: '1px solid #d1d5db',
    borderRadius: 8,
    padding: 12,
    background: '#fff'
  },
  chartMeta: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  chartTitle: {
    fontSize: 15,
    fontWeight: 600,
    color: '#111827'
  },
  chartLink: {
    fontSize: 13,
    color: '#2563eb',
    textDecoration: 'none'
  },
  chartImage: {
    width: '100%',
    height: 'auto',
    borderRadius: 6,
    border: '1px solid #e5e7eb'
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
  }
}
