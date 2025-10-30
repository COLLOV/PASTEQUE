import { useState, useRef, useEffect, useMemo, KeyboardEvent as ReactKeyboardEvent } from 'react'
import { useSearchParams, useLocation } from 'react-router-dom'
import { apiFetch, streamSSE } from '@/services/api'
import { Button, Textarea, Loader } from '@/components/ui'
import type {
  Message,
  ChatCompletionRequest,
  ChartDatasetPayload,
  ChartGenerationRequest,
  ChartGenerationResponse,
  ChatStreamMeta,
  ChatStreamDelta,
  ChatStreamDone,
  SavedChartResponse,
  EvidenceSpec,
  EvidenceRowsPayload
} from '@/types/chat'
import { HiPaperAirplane, HiChartBar, HiBookmark, HiCheckCircle, HiXMark } from 'react-icons/hi2'
import clsx from 'clsx'

//

function normaliseRows(columns: string[] = [], rows: any[] = []): Record<string, unknown>[] {
  const headings = columns.length > 0 ? columns : ['value']
  return rows.map(row => {
    if (Array.isArray(row)) {
      const obj: Record<string, unknown> = {}
      headings.forEach((col, idx) => {
        obj[col] = row[idx] ?? null
      })
      return obj
    }
    if (row && typeof row === 'object') {
      const obj: Record<string, unknown> = {}
      headings.forEach(col => {
        obj[col] = (row as Record<string, unknown>)[col]
      })
      return obj
    }
    return { [headings[0]]: row }
  })
}

function createMessageId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export default function Chat() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { search } = useLocation()
  const [messages, setMessages] = useState<Message[]>([])
  const [conversationId, setConversationId] = useState<number | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [history, setHistory] = useState<Array<{ id: number; title: string; updated_at: string }>>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [chartMode, setChartMode] = useState(false)
  const [sqlMode, setSqlMode] = useState(true)
  const [evidenceSpec, setEvidenceSpec] = useState<EvidenceSpec | null>(null)
  const [evidenceData, setEvidenceData] = useState<EvidenceRowsPayload | null>(null)
  const [showTicketsSheet, setShowTicketsSheet] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    // Auto‑scroll the internal messages list container instead of the window
    const el = listRef.current
    if (!el) return
    try {
      const top = el.scrollHeight
      if (typeof el.scrollTo === 'function') {
        el.scrollTo({ top, behavior: 'smooth' })
      } else {
        el.scrollTop = top
      }
    } catch {
      /* noop */
    }
  }, [messages, loading])

  // Sync history modal visibility with URL `?history=1` (derive from location.search)
  useEffect(() => {
    const sp = new URLSearchParams(search)
    const wantOpen = sp.has('history') && sp.get('history') !== '0'
    setHistoryOpen(prev => (prev === wantOpen ? prev : wantOpen))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search])

  // Trigger a fresh session when URL has `?new=1`, then clean the URL (based on location.search)
  useEffect(() => {
    const sp = new URLSearchParams(search)
    const wantNew = sp.has('new') && sp.get('new') !== '0'
    if (wantNew) {
      onNewChat()
      sp.delete('new')
      setSearchParams(sp, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search])

  useEffect(() => {
    const sp = new URLSearchParams(search)
    const currentlyHas = sp.has('history')
    if (historyOpen && !currentlyHas) {
      sp.set('history', '1')
      setSearchParams(sp, { replace: true })
    } else if (!historyOpen && currentlyHas) {
      sp.delete('history')
      setSearchParams(sp, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyOpen, search])

  // Fermer la sheet Tickets avec la touche Escape
  useEffect(() => {
    if (!showTicketsSheet) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setShowTicketsSheet(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [showTicketsSheet])

  async function refreshHistory() {
    try {
      const items = await apiFetch<Array<{ id: number; title: string; created_at: string; updated_at: string }>>('/conversations')
      setHistory(items || [])
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    refreshHistory()
  }, [])

  function onToggleChartModeClick() {
    setChartMode(v => {
      const next = !v
      setSqlMode(!next) // SQL actif par défaut hors mode graphique
      return next
    })
    setError('')
  }

  async function onSend() {
    const text = input.trim()
    if (!text || loading) return
    setError('')
    const userMessage: Message = { id: createMessageId(), role: 'user', content: text }
    const next = [...messages, userMessage]
    setMessages(next)
    setInput('')
    setLoading(true)
    // Reset uniquement l'état d'affichage du chat et du panneau Tickets
    setEvidenceSpec(null)
    setEvidenceData(null)

    const isChartMode = chartMode
    const sqlByStep = new Map<string, { sql: string; purpose?: string }>()
    let latestDataset: ChartDatasetPayload | null = null
    let finalAnswer = ''

    try {
      const controller = new AbortController()
      abortRef.current = controller
      setMessages(prev => [...prev, { role: 'assistant', content: '', ephemeral: true }])

      // Force NL→SQL when SQL toggle or Chart mode is active
      const baseMeta: Record<string, unknown> = {}
      if (sqlMode || isChartMode) baseMeta.nl2sql = true
      if (conversationId) baseMeta.conversation_id = conversationId
      const payload: ChatCompletionRequest = { messages: next, metadata: baseMeta }

      await streamSSE('/chat/stream', payload, (type, data) => {
        if (type === 'meta') {
          const meta = data as ChatStreamMeta
          if (typeof meta?.conversation_id === 'number') {
            setConversationId(meta.conversation_id)
          }
          setMessages(prev => {
            const copy = [...prev]
            const idx = copy.findIndex(m => m.ephemeral)
            if (idx >= 0) {
              copy[idx] = {
                ...copy[idx],
                details: {
                  ...(copy[idx].details || {}),
                  requestId: meta.request_id,
                  provider: meta.provider,
                  model: meta.model,
                }
              }
            }
            return copy
          })
          // Capture la spec pour alimenter les tickets à gauche (si fournie)
          const spec = meta?.evidence_spec as EvidenceSpec | undefined
          if (spec && typeof spec === 'object' && spec.entity_label && spec.pk) {
            setEvidenceSpec(spec)
          }
        } else if (type === 'plan') {
          setMessages(prev => {
            const copy = [...prev]
            const idx = copy.findIndex(m => m.ephemeral)
            if (idx >= 0) {
              copy[idx] = {
                ...copy[idx],
                details: { ...(copy[idx].details || {}), plan: data }
              }
            }
            return copy
          })
        } else if (type === 'sql') {
          const stepKey = typeof data?.step !== 'undefined' ? String(data.step) : 'default'
          const sqlText = String(data?.sql || '')
          const entry = { sql: sqlText, purpose: data?.purpose ? String(data.purpose) : undefined }
          sqlByStep.set(stepKey, entry)
          sqlByStep.set('latest', entry)
          const step = { step: data?.step, purpose: data?.purpose, sql: data?.sql }
          setMessages(prev => {
            const copy = [...prev]
            const idx = copy.findIndex(m => m.ephemeral)
            const target = idx >= 0 ? idx : copy.length - 1
            const interimText = sqlText
            copy[target] = {
              ...copy[target],
              content: interimText,
              interimSql: interimText,
              details: {
                ...(copy[target].details || {}),
                steps: [ ...((copy[target].details?.steps) || []), step ]
              }
            }
            return copy
          })
        } else if (type === 'rows') {
          const purpose: string | undefined = typeof (data?.purpose) === 'string' ? String(data.purpose) : undefined
          const columns = Array.isArray(data?.columns)
            ? (data.columns as unknown[]).filter((col): col is string => typeof col === 'string')
            : []
          const rows = Array.isArray(data?.rows) ? data.rows : []
          const normalizedRows = normaliseRows(columns, rows)

          if (purpose === 'evidence') {
            const evid: EvidenceRowsPayload = {
              columns,
              rows: normalizedRows,
              row_count: typeof data?.row_count === 'number' ? data.row_count : normalizedRows.length,
              step: typeof data?.step === 'number' ? data.step : undefined,
              purpose
            }
            setEvidenceData(evid)
          } else {
            // Regular NL→SQL samples for charting/debug
            const sample = { step: data?.step, columns: data?.columns, row_count: data?.row_count }
            setMessages(prev => {
              const copy = [...prev]
              const idx = copy.findIndex(m => m.ephemeral)
              if (idx >= 0) {
                copy[idx] = {
                  ...copy[idx],
                  details: {
                    ...(copy[idx].details || {}),
                    samples: [ ...((copy[idx].details?.samples) || []), sample ]
                  }
                }
              }
              return copy
            })
            const stepKey = typeof data?.step !== 'undefined' ? String(data.step) : 'default'
            const sqlInfo = sqlByStep.get(stepKey) ?? sqlByStep.get('latest') ?? { sql: '' }
            const rowCount = typeof data?.row_count === 'number' ? data.row_count : normalizedRows.length
            latestDataset = {
              sql: sqlInfo.sql,
              columns,
              rows: normalizedRows,
              row_count: rowCount,
              step: typeof data?.step === 'number' ? data.step : undefined,
              description: sqlInfo.purpose,
            }
          }
        } else if (type === 'delta') {
          const delta = data as ChatStreamDelta
          setMessages(prev => {
            const copy = [...prev]
            const idx = copy.findIndex(m => m.ephemeral)
            const target = idx >= 0 ? idx : copy.length - 1
            const wasInterim = Boolean(copy[target].interimSql)
            copy[target] = {
              ...copy[target],
              content: wasInterim ? (delta.content || '') : ((copy[target].content || '') + (delta.content || '')),
              interimSql: undefined,
              ephemeral: true,
            }
            return copy
          })
        } else if (type === 'done') {
          const done = data as ChatStreamDone
          finalAnswer = done.content_full || ''
          setMessages(prev => {
            const copy = [...prev]
            const idx = copy.findIndex(m => m.ephemeral)
            if (idx >= 0) {
              copy[idx] = {
                id: createMessageId(),
                role: 'assistant',
                content: done.content_full,
                // Attach latest NL→SQL dataset (if any) to allow on-demand charting
                ...(latestDataset ? { chartDataset: latestDataset } : {}),
                details: {
                  ...(copy[idx].details || {}),
                  elapsed: done.elapsed_s
                }
              }
            } else {
              copy.push({ id: createMessageId(), role: 'assistant', content: done.content_full, ...(latestDataset ? { chartDataset: latestDataset } : {}) })
            }
            return copy
          })
          // Fin du streaming: message final fixé
          // Refresh history list after message persisted
          refreshHistory()
        } else if (type === 'error') {
          setError(data?.message || 'Erreur streaming')
        }
      }, { signal: controller.signal })

      abortRef.current = null

      if (isChartMode) {
        if (!latestDataset) {
          setMessages(prev => [
            ...prev,
            {
              id: createMessageId(),
              role: 'assistant',
              content: "Aucun résultat SQL exploitable pour générer un graphique."
            }
          ])
          return
        }

        const dataset = latestDataset as ChartDatasetPayload
        if (!dataset.sql || dataset.columns.length === 0 || dataset.rows.length === 0) {
          setMessages(prev => [
            ...prev,
            {
              id: createMessageId(),
              role: 'assistant',
              content: "Aucun résultat SQL exploitable pour générer un graphique."
            }
          ])
          return
        }

        const chartPayload: ChartGenerationRequest = {
          prompt: text,
          answer: finalAnswer || undefined,
          dataset: latestDataset
        }

        try {
          const res = await apiFetch<ChartGenerationResponse>('/mcp/chart', {
            method: 'POST',
            body: JSON.stringify(chartPayload)
          })
          const chartUrl = typeof res?.chart_url === 'string' ? res.chart_url : ''
          const assistantMessage: Message = chartUrl
            ? {
                id: createMessageId(),
                role: 'assistant',
                content: chartUrl,
                chartUrl,
                chartTitle: res?.chart_title,
                chartDescription: res?.chart_description,
                chartTool: res?.tool_name,
                chartPrompt: text,
                chartSpec: res?.chart_spec
              }
            : {
                id: createMessageId(),
                role: 'assistant',
                content: "Impossible de générer un graphique."
              }
          setMessages(prev => [...prev, assistantMessage])
        } catch (chartErr) {
          console.error(chartErr)
          setMessages(prev => [
            ...prev,
            {
              id: createMessageId(),
              role: 'assistant',
              content: "Erreur lors de la génération du graphique."
            }
          ])
          if (chartErr instanceof Error) {
            setError(chartErr.message)
          }
        }
      }
    } catch (e) {
      console.error(e)
      setError(e instanceof Error ? e.message : 'Erreur inconnue')
    } finally {
      setLoading(false)
      abortRef.current = null
    }
  }

  async function loadConversation(id: number) {
    try {
      const data = await apiFetch<{
        id: number
        title: string
        messages: Array<{
          role: 'user' | 'assistant'
          content: string
          created_at: string
          details?: {
            plan?: any
            steps?: Array<{ step?: number; purpose?: string; sql?: string }>
          }
        }>
        evidence_spec?: EvidenceSpec
        evidence_rows?: EvidenceRowsPayload
      }>(`/conversations/${id}`)
      setConversationId(data.id)
      setMessages(
        (data.messages || []).map(m => ({
          id: createMessageId(),
          role: m.role,
          content: m.content,
          details: m.details,
          ...(m as any).chart_url ? {
            chartUrl: (m as any).chart_url,
            chartTitle: (m as any).chart_title,
            chartDescription: (m as any).chart_description,
            chartTool: (m as any).chart_tool,
            chartSpec: (m as any).chart_spec,
          } : {}
        }))
      )
      setEvidenceSpec(data?.evidence_spec ?? null)
      // Defensive normalization: history may contain array-rows; convert to objects
      const ev = data?.evidence_rows
      if (ev && Array.isArray(ev.rows)) {
        const cols = Array.isArray(ev.columns)
          ? (ev.columns as unknown[]).filter((c): c is string => typeof c === 'string')
          : []
        const rowsNorm = normaliseRows(cols, ev.rows as any[])
        setEvidenceData({
          columns: cols,
          rows: rowsNorm,
          row_count: typeof ev.row_count === 'number' ? ev.row_count : rowsNorm.length,
          step: typeof ev.step === 'number' ? ev.step : undefined,
          purpose: ev.purpose
        })
      } else {
        setEvidenceData(ev ?? null)
      }
      setHistoryOpen(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Chargement impossible')
    }
  }

  function onNewChat() {
    if (loading && abortRef.current) {
      abortRef.current.abort()
    }
    setConversationId(null)
    setMessages([])
    setEvidenceSpec(null)
    setEvidenceData(null)
    setError('')
    setHistoryOpen(false)
  }

  async function onGenerateChart(messageId: string) {
    const index = messages.findIndex(m => m.id === messageId)
    if (index < 0) return
    const msg = messages[index]
    // Prevent duplicate clicks while in-flight
    if (msg.chartSaving) return
    let dataset = msg.chartDataset
    // If dataset missing (typical when loaded from history), try to hydrate from backend
    if (!dataset && conversationId != null) {
      try {
        setMessages(prev => {
          const copy = [...prev]
          const i = copy.findIndex(m => m.id === messageId)
          if (i >= 0) copy[i] = { ...copy[i], chartSaving: true }
          return copy
        })
        const res = await apiFetch<{ dataset: ChartDatasetPayload }>(`/conversations/${conversationId}/dataset?message_index=${index}`)
        if (res?.dataset && res.dataset.sql && (res.dataset.columns?.length ?? 0) > 0 && (res.dataset.rows?.length ?? 0) > 0) {
          dataset = res.dataset
          setMessages(prev => {
            const copy = [...prev]
            const i = copy.findIndex(m => m.id === messageId)
            if (i >= 0) copy[i] = { ...copy[i], chartDataset: dataset, chartSaving: false }
            return copy
          })
        } else {
          setMessages(prev => prev.map(m => (m.id === messageId ? { ...m, chartSaving: false } : m)))
          setError("Impossible de reconstruire un jeu de données pour ce message.")
          return
        }
      } catch (err) {
        setMessages(prev => prev.map(m => (m.id === messageId ? { ...m, chartSaving: false } : m)))
        setError(err instanceof Error ? err.message : 'Hydratation du dataset échouée')
        return
      }
    }
    if (!dataset || !dataset.sql || (dataset.columns?.length ?? 0) === 0 || (dataset.rows?.length ?? 0) === 0) {
      setError("Aucune donnée SQL exploitable pour ce message.")
      return
    }
    // Derive prompt from the closest preceding user message
    let prompt = ''
    for (let i = index - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        prompt = messages[i].content || ''
        break
      }
    }
    // Mark generating on the source message
    setMessages(prev => {
      const copy = [...prev]
      const i = copy.findIndex(m => m.id === messageId)
      if (i >= 0) copy[i] = { ...copy[i], chartSaving: true }
      return copy
    })
    try {
      const payload: ChartGenerationRequest = { prompt: prompt || 'Générer un graphique', answer: msg.content, dataset }
      const res = await apiFetch<ChartGenerationResponse>('/mcp/chart', { method: 'POST', body: JSON.stringify(payload) })
      const chartUrl = typeof res?.chart_url === 'string' ? res.chart_url : ''
      const assistantMessage: Message = chartUrl
        ? {
            id: createMessageId(),
            role: 'assistant',
            content: chartUrl,
            chartUrl,
            chartTitle: res?.chart_title,
            chartDescription: res?.chart_description,
            chartTool: res?.tool_name,
            chartPrompt: prompt || undefined,
            chartSpec: res?.chart_spec
          }
        : {
            id: createMessageId(),
            role: 'assistant',
            content: 'Impossible de générer un graphique.'
          }
      setMessages(prev => {
        const copy = [...prev]
        // Clear generating flag on the source message and append the chart message
        const i = copy.findIndex(m => m.id === messageId)
        if (i >= 0) copy[i] = { ...copy[i], chartSaving: false }
        copy.push(assistantMessage)
        return copy
      })
      // Persist as conversation event so chart reappears in history
      if (chartUrl && conversationId) {
        try {
          await apiFetch(`/conversations/${conversationId}/chart`, {
            method: 'POST',
            body: JSON.stringify({
              chart_url: chartUrl,
              tool_name: res?.tool_name,
              chart_title: res?.chart_title,
              chart_description: res?.chart_description,
              chart_spec: res?.chart_spec,
            })
          })
        } catch {
          // non-bloquant
        }
      }
    } catch (err) {
      console.error(err)
      setMessages(prev => {
        const copy = [...prev]
        const i = copy.findIndex(m => m.id === messageId)
        if (i >= 0) copy[i] = { ...copy[i], chartSaving: false }
        return copy
      })
      setError(err instanceof Error ? err.message : 'Erreur lors de la génération du graphique')
    }
  }

  async function onSaveChart(messageId: string) {
    const target = messages.find(m => m.id === messageId)
    if (!target || !target.chartUrl) {
      return
    }
    let prompt = target.chartPrompt || ''
    if (!prompt) {
      const targetIndex = messages.findIndex(m => m.id === messageId)
      for (let i = targetIndex - 1; i >= 0; i -= 1) {
        if (messages[i]?.role === 'user') {
          prompt = messages[i].content
          break
        }
      }
    }
    const payload = {
      prompt,
      chart_url: target.chartUrl,
      tool_name: target.chartTool,
      chart_title: target.chartTitle,
      chart_description: target.chartDescription,
      chart_spec: target.chartSpec
    }
    setMessages(prev =>
      prev.map(msg =>
        msg.id === messageId
          ? { ...msg, chartSaving: true, chartSaveError: undefined }
          : msg
      )
    )
    try {
      const saved = await apiFetch<SavedChartResponse>('/charts', {
        method: 'POST',
        body: JSON.stringify(payload)
      })
      setMessages(prev =>
        prev.map(msg =>
          msg.id === messageId
            ? {
                ...msg,
                chartSaving: false,
                chartSaved: true,
                chartRecordId: saved?.id ?? msg.chartRecordId,
                chartSaveError: undefined
              }
            : msg
        )
      )
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Sauvegarde impossible'
      setMessages(prev =>
        prev.map(msg =>
          msg.id === messageId
            ? { ...msg, chartSaving: false, chartSaveError: message }
            : msg
        )
      )
    }
  }

  function onKeyDown(e: ReactKeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
    }
  }

  // reset supprimé

  function onCancel() {
    if (abortRef.current) {
      abortRef.current.abort()
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 md:gap-5">
      {/* Colonne gauche: Ticket exploration */}
      <aside className="hidden lg:block lg:col-span-5 xl:col-span-5 2xl:col-span-5">
        <div className="border rounded-lg bg-white shadow-sm p-3 sticky top-20 max-h-[calc(100vh-120px)] overflow-auto">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold text-primary-900">{evidenceSpec?.entity_label ?? 'Exploration'}</h2>
          </div>
          <TicketPanel spec={evidenceSpec} data={evidenceData} />
        </div>
      </aside>

      {/* Colonne droite: Chat */}
      <section className="lg:col-span-7 xl:col-span-7 2xl:col-span-7">
        <div className="border rounded-lg bg-white shadow-sm p-0 flex flex-col min-h-[calc(100vh-120px)]">
          {/* Messages */}
          <div ref={listRef} className="flex-1 p-4 space-y-4 overflow-auto">
            {/* Mobile toolbar (Exploration uniquement) */}
            <div className="sticky top-0 z-10 -mt-4 -mx-4 mb-2 px-4 pt-3 pb-2 bg-white/95 backdrop-blur border-b lg:hidden">
              <div className="flex items-center justify-between gap-2">
                <div className="text-xs text-primary-500">{conversationId ? `Discussion #${conversationId}` : 'Nouvelle discussion'}</div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setShowTicketsSheet(true)}
                    className="inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs bg-white text-primary-700 border-primary-300 hover:bg-primary-50"
                  >
                    <HiBookmark className="w-4 h-4" />
                    Exploration
                    {(() => {
                      const c = evidenceData?.row_count ?? evidenceData?.rows?.length ?? 0
                      return c > 0 ? (
                        <span className="ml-1 inline-flex items-center justify-center min-w-[18px] h-[18px] rounded-full text-[10px] px-1 bg-primary-600 text-white">{c}</span>
                      ) : null
                    })()}
                  </button>
                </div>
              </div>
            </div>
            {/* Desktop toolbar (sans boutons Historique/Nouveau chat pour éviter doublons avec le header) */}
            <div className="hidden lg:flex items-center justify-between mb-2">
              <div className="text-xs text-primary-500">{conversationId ? `Discussion #${conversationId}` : 'Nouvelle discussion'}</div>
              <div />
            </div>
            {messages.map((message, index) => (
              <MessageBubble
                key={message.id ?? index}
                message={message}
                onSaveChart={onSaveChart}
                onGenerateChart={onGenerateChart}
              />
            ))}
            {messages.length === 0 && loading && (
              <div className="flex justify-center py-2"><Loader text="Streaming…" /></div>
            )}
            {error && (
              <div className="mt-2 bg-red-50 border-2 border-red-200 rounded-lg p-3">
                <p className="text-sm text-red-700">{error}</p>
              </div>
            )}
          </div>

          {/* Composer */}
          <div className="p-3">
            <div className="relative">
              <Textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Posez votre question"
                rows={1}
                fullWidth
                className={clsx(
                  'pl-14 pr-14 h-12 min-h-[48px] resize-none overflow-x-auto overflow-y-hidden scrollbar-none no-focus-ring !rounded-2xl',
                  'focus:!border-primary-200 focus:!ring-0 focus:!ring-transparent focus:!ring-offset-0 focus:!outline-none',
                  'focus-visible:!border-primary-200 focus-visible:!ring-0 focus-visible:!ring-transparent focus-visible:!ring-offset-0 focus-visible:!outline-none',
                  'leading-[48px] placeholder:text-primary-400',
                  'text-left whitespace-nowrap'
                )}
              />
              {/* Toggle Graph */}
              <button
                type="button"
                onClick={onToggleChartModeClick}
                aria-pressed={chartMode}
                title="Activer MCP Chart"
                className={clsx(
                  'absolute left-2 top-1/2 -translate-y-1/2 transform inline-flex items-center justify-center h-10 w-10 rounded-full transition-colors focus:outline-none',
                  chartMode
                    ? 'bg-primary-600 text-white hover:bg-primary-700 border-2 border-primary-600'
                    : 'bg-white text-primary-700 border-2 border-primary-200 hover:bg-primary-50'
                )}
              >
                <HiChartBar className="w-5 h-5" />
              </button>
              {/* Envoyer/Annuler */}
              <button
                type="button"
                onClick={loading ? onCancel : onSend}
                disabled={loading ? false : !input.trim()}
                className="absolute right-2 top-1/2 -translate-y-1/2 transform inline-flex items-center justify-center h-10 w-10 rounded-full bg-primary-600 text-white disabled:opacity-40 disabled:cursor-not-allowed hover:bg-primary-700 transition-colors"
                aria-label={loading ? 'Annuler' : 'Envoyer le message'}
                title={loading ? 'Annuler' : 'Envoyer'}
              >
                {loading ? (
                  <HiXMark className="w-5 h-5" />
                ) : (
                  <HiPaperAirplane className="w-5 h-5" />
                )}
              </button>
            </div>
            {null}
          </div>
        </div>
      </section>

      {/* Bottom sheet (mobile) for tickets */}
      {showTicketsSheet && (
        <div className="lg:hidden fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/30" onClick={() => setShowTicketsSheet(false)} />
          <div className="absolute left-0 right-0 bottom-0 max-h-[70vh] bg-white rounded-t-2xl border-t shadow-lg p-3 overflow-auto">
            <div className="flex items-center justify-between mb-2">
              <div>
                <div className="text-sm font-semibold text-primary-900">{evidenceSpec?.entity_label ?? 'Exploration'}</div>
                {evidenceSpec?.period && (
                  <div className="text-[11px] text-primary-500">
                    {typeof evidenceSpec.period === 'string' ? evidenceSpec.period : `${evidenceSpec.period.from ?? ''}${evidenceSpec.period.to ? ` → ${evidenceSpec.period.to}` : ''}`}
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={() => setShowTicketsSheet(false)}
                className="h-7 w-7 inline-flex items-center justify-center rounded-full border border-primary-200 hover:bg-primary-50"
                aria-label="Fermer"
                title="Fermer"
              >
                <HiXMark className="w-4 h-4" />
              </button>
            </div>
            <TicketPanel spec={evidenceSpec} data={evidenceData} />
          </div>
        </div>
      )}

      {/* History modal */}
      {historyOpen && (
        <div className="fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/30" onClick={() => setHistoryOpen(false)} />
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-lg border shadow-lg w-[90vw] max-w-xl max-h-[80vh] overflow-auto">
            <div className="p-3 border-b flex items-center justify-between">
              <div className="text-sm font-semibold">Conversations</div>
              <button className="text-xs underline" onClick={refreshHistory}>Rafraîchir</button>
            </div>
            <div className="p-3">
              {history.length === 0 && (
                <div className="text-sm text-primary-500">Aucune conversation</div>
              )}
              <ul className="divide-y">
                {history.map(item => (
                  <li key={item.id} className="py-2 flex items-center justify-between">
                    <button
                      className="text-left text-sm text-primary-900 hover:underline"
                      onClick={() => loadConversation(item.id)}
                    >
                      <div className="font-medium truncate max-w-[42ch]">{item.title || `Discussion #${item.id}`}</div>
                      <div className="text-xs text-primary-500">{new Date(item.updated_at).toLocaleString()}</div>
                    </button>
                    <button
                      className="text-xs border rounded-full px-2 py-1 hover:bg-primary-50"
                      onClick={() => loadConversation(item.id)}
                    >Ouvrir</button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

interface MessageBubbleProps {
  message: Message
  onSaveChart?: (messageId: string) => void
  onGenerateChart?: (messageId: string) => void
}

// -------- Left panel: Tickets from evidence --------
type TicketPanelProps = {
  spec: EvidenceSpec | null
  data: EvidenceRowsPayload | null
}

function TicketPanel({ spec, data }: TicketPanelProps) {
  const count = data?.row_count ?? data?.rows?.length ?? 0
  const limit = spec?.limit ?? 100
  const allRows: Record<string, unknown>[] = data?.rows ?? []
  const rows = allRows.slice(0, limit)
  const extra = Math.max((count || 0) - rows.length, 0)
  const columns: string[] = spec?.columns && spec.columns.length > 0 ? spec.columns : (data?.columns ?? [])
  const createdAtKey = spec?.display?.created_at
  const titleKey = spec?.display?.title
  const statusKey = spec?.display?.status
  const pkKey = spec?.pk
  const linkTpl = spec?.display?.link_template

  const sorted = useMemo(() => {
    if (!createdAtKey) return rows
    const key = createdAtKey
    return [...rows].sort((a, b) => {
      const va = a[key]
      const vb = b[key]
      const da = va ? new Date(String(va)) : null
      const db = vb ? new Date(String(vb)) : null
      const ta = da && !isNaN(da.getTime()) ? da.getTime() : 0
      const tb = db && !isNaN(db.getTime()) ? db.getTime() : 0
      return tb - ta
    })
  }, [rows, createdAtKey])

  function buildLink(tpl: string | undefined, row: Record<string, unknown>) {
    if (!tpl) return undefined
    try {
      // Encode dynamic values to prevent injection into path/query
      const replaced = tpl.replace(/\{(\w+)\}/g, (_, k) => encodeURIComponent(String(row[k] ?? '')))
      // Build URL against current origin to validate protocol and normalize
      const url = new URL(replaced, window.location.origin)
      const allowed = ['http:', 'https:']
      if (!allowed.includes(url.protocol)) return undefined
      // Return relative path when template intended a relative URL
      if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(replaced)) {
        return url.pathname + url.search + url.hash
      }
      return url.href
    } catch {
      return undefined
    }
  }

  if (!spec || !data || (count ?? 0) === 0) {
    return (
      <div className="text-sm text-primary-500">
        Aucun ticket détecté. Posez une question pour afficher les éléments concernés.
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {sorted.map((row, idx) => {
        const title = titleKey ? row[titleKey] : undefined
        const status = statusKey ? row[statusKey] : undefined
        const created = createdAtKey ? row[createdAtKey] : undefined
        const pk = pkKey ? row[pkKey] : undefined
        const link = buildLink(linkTpl, row)
        const uniqueKey = pk != null ? String(pk) : `row-${idx}`
        return (
          <div key={uniqueKey} className="border border-primary-100 rounded-md p-2">
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm font-medium text-primary-900 truncate">
                {String(title ?? (pk ?? `#${idx + 1}`))}
              </div>
              {status != null ? (
                <span className="text-[11px] rounded-full border px-2 py-[2px] text-primary-600 border-primary-200">{String(status)}</span>
              ) : null}
            </div>
            <div className="mt-1 text-xs text-primary-500">
              {created ? new Date(String(created)).toLocaleString() : null}
            </div>
            {link && (
              <div className="mt-1 text-xs">
                <a href={link} target="_blank" rel="noopener noreferrer" className="underline text-primary-600 break-all">{link}</a>
              </div>
            )}
            {columns && columns.length > 0 && (
              <div className="mt-2 overflow-auto">
                <table className="min-w-full text-[11px]">
                  <tbody>
                    {columns.map((c) => (
                      <tr key={c} className="border-t border-primary-100">
                        <td className="pr-2 py-1 text-primary-400 whitespace-nowrap">{c}</td>
                        <td className="py-1 text-primary-800 break-all">{String(row[c] ?? '')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )
      })}
      {extra > 0 && (
        <div className="text-[11px] text-primary-500">+{extra} supplémentaires non affichés</div>
      )}
    </div>
  )
}

function MessageBubble({ message, onSaveChart, onGenerateChart }: MessageBubbleProps) {
  const {
    id,
    role,
    content,
    chartUrl,
    chartTitle,
    chartDescription,
    chartTool,
    chartSaved,
    chartSaving,
    chartSaveError
  } = message
  const isUser = role === 'user'
  const [showDetails, setShowDetails] = useState(false)
  return (
    <div
      className={clsx(
        'flex',
        isUser ? 'justify-end' : 'justify-start'
      )}
    >
      <div
        className={clsx(
          'animate-slide-up',
          isUser
            ? 'max-w-[75%] rounded-lg px-4 py-3 bg-primary-950 text-white shadow-sm'
            : clsx(
                'max-w-full bg-transparent p-0 rounded-none shadow-none',
                message.ephemeral && 'opacity-70'
              )
        )}
      >
        {/* Label d'auteur supprimé (Vous/Assistant) pour une UI plus épurée */}
        {chartUrl && !isUser ? (
          <div className="space-y-3">
            {chartTitle && (
              <div className="text-sm font-semibold text-primary-900">
                {chartTitle}
              </div>
            )}
            <a
              href={chartUrl}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-primary-600 break-all underline"
            >
              {chartUrl}
            </a>
            <img
              src={chartUrl}
              alt={chartTitle || 'Graphique MCP'}
              className="w-full rounded-md border border-primary-100"
            />
            {chartDescription && (
              <p className="text-xs text-primary-700 whitespace-pre-wrap">
                {chartDescription}
              </p>
            )}
            {chartTool && (
              <p className="text-[11px] uppercase tracking-wide text-primary-400">
                Outil : {chartTool}
              </p>
            )}
            {!chartSaved && onSaveChart && (
              <div className="pt-2">
                <Button
                  size="sm"
                  onClick={() => id && onSaveChart(id)}
                  disabled={chartSaving || !id}
                >
                  <HiBookmark className="w-4 h-4 mr-2" />
                  {chartSaving ? 'Enregistrement…' : 'Enregistrer dans le dashboard'}
                </Button>
              </div>
            )}
            {chartSaved && (
              <div className="flex items-center gap-2 text-xs text-primary-600 pt-2">
                <HiCheckCircle className="w-4 h-4" />
                <span>Graphique enregistré</span>
              </div>
            )}
            {chartSaveError && (
              <p className="text-xs text-red-600 pt-2">
                {chartSaveError}
              </p>
            )}
          </div>
        ) : (
          <div className={clsx(
            'text-sm whitespace-pre-wrap leading-relaxed',
            isUser ? '' : 'text-primary-950'
          )}>
            {content}
            {/* Actions: Graphique + Détails (affichés uniquement quand le message est finalisé) */}
            {!isUser && !chartUrl && !message.ephemeral && (
              <div className="mt-2 flex items-center gap-2">
                <Button
                  size="xs"
                  variant="secondary"
                  onClick={() => message.id && onGenerateChart && onGenerateChart(message.id)}
                  disabled={
                    !message.id || Boolean(message.chartSaving) ||
                    !(
                      (message.chartDataset && message.chartDataset.sql &&
                        (message.chartDataset.columns?.length ?? 0) > 0 &&
                        (message.chartDataset.rows?.length ?? 0) > 0) ||
                      (message.details && Array.isArray(message.details.steps) && message.details.steps.some(s => typeof s?.sql === 'string' && s.sql))
                    )
                  }
                  title={
                    message.chartDataset && (message.chartDataset.columns?.length ?? 0) > 0 && (message.chartDataset.rows?.length ?? 0) > 0
                      ? 'Générer un graphique à partir du jeu de données'
                      : 'Aucun jeu de données exploitable pour le graphique'
                  }
                >
                  <HiChartBar className="w-4 h-4 mr-2" />
                  {message.chartSaving ? 'Génération…' : 'Graphique'}
                </Button>
                <Button
                  size="xs"
                  variant="secondary"
                  onClick={() => setShowDetails(v => !v)}
                >
                  {showDetails ? 'Masquer' : 'Détails'}
                </Button>
              </div>
            )}
          </div>
        )}
        {/* Détails n'apparaissent que lorsque le message est finalisé */}
        {!isUser && !message.ephemeral && message.details && (message.details.steps?.length || message.details.plan) ? (
          <div className="mt-2 text-xs">
            {showDetails && (
              <div className="mt-1 space-y-2 text-primary-700">
                {/* Métadonnées masquées (request_id/provider/model/elapsed) pour alléger l'affichage */}
                {message.details.steps && message.details.steps.length > 0 && (
                  <div className="text-[11px]">
                    <div className="uppercase tracking-wide text-primary-500 mb-1">SQL exécuté</div>
                    <ul className="list-disc ml-5 space-y-1 max-h-40 overflow-auto">
                      {message.details.steps.map((s, i) => (
                        <li key={i} className="break-all">
                          {s.step ? `#${s.step} ` : ''}{s.purpose ? `[${s.purpose}] ` : ''}{s.sql}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {message.details.samples && message.details.samples.length > 0 && (
                  <div className="text-[11px]">
                    <div className="uppercase tracking-wide text-primary-500 mb-1">Échantillons</div>
                    <ul className="grid grid-cols-2 gap-2">
                      {message.details.samples.map((s, i) => (
                        <li key={i} className="truncate">
                          {s.step ? `#${s.step}: ` : ''}{s.columns?.slice(0,3)?.join(', ') || '—'} ({s.row_count ?? 0} lignes)
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  )
}

// Evidence UI supprimée (panneau remplacé par Ticket exploration à gauche)
