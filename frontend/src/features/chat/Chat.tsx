import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import { apiFetch, streamSSE } from '@/services/api'
import { Button, Textarea, Loader } from '@/components/ui'
import type {
  Message,
  ChatCompletionRequest,
  ChartGenerationResponse,
  ChatStreamMeta,
  ChatStreamDelta,
  ChatStreamDone,
  SavedChartResponse
} from '@/types/chat'
import { HiPaperAirplane, HiChartBar, HiBookmark, HiCheckCircle, HiXMark } from 'react-icons/hi2'
import clsx from 'clsx'

function createMessageId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [chartMode, setChartMode] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.requestAnimationFrame(() => {
        const doc = document.documentElement
        window.scrollTo({ top: doc.scrollHeight, behavior: 'smooth' })
      })
    }
  }, [messages, loading])

  function onToggleChartModeClick() {
    setChartMode(v => !v)
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
    try {
      if (chartMode) {
        const res = await apiFetch<ChartGenerationResponse>('/mcp/chart', {
          method: 'POST',
          body: JSON.stringify({ prompt: text })
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
      } else {
        // Streaming via SSE over POST
        const controller = new AbortController()
        abortRef.current = controller
        // Insert ephemeral assistant message placeholder
        setMessages(prev => [...prev, { role: 'assistant', content: '', ephemeral: true }])

        const payload: ChatCompletionRequest = { messages: next }
        await streamSSE('/chat/stream', payload, (type, data) => {
          if (type === 'meta') {
            const meta = data as ChatStreamMeta
            // Attach meta onto the ephemeral assistant message details
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
            const step = { step: data?.step, purpose: data?.purpose, sql: data?.sql }
            // Show SQL as interim content in the ephemeral bubble (grayed)
            setMessages(prev => {
              const copy = [...prev]
              const idx = copy.findIndex(m => m.ephemeral)
              const target = idx >= 0 ? idx : copy.length - 1
              const interimText = String(data?.sql || '')
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
            // Replace ephemeral with final
            setMessages(prev => {
              const copy = [...prev]
              const idx = copy.findIndex(m => m.ephemeral)
              if (idx >= 0) {
                copy[idx] = {
                  role: 'assistant',
                  content: done.content_full,
                  details: {
                    ...(copy[idx].details || {}),
                    elapsed: done.elapsed_s
                  }
                }
              } else {
                copy.push({ role: 'assistant', content: done.content_full })
              }
              return copy
            })
          } else if (type === 'error') {
            setError(data?.message || 'Erreur streaming')
          }
        }, { signal: controller.signal })
      }
    } catch (e) {
      console.error(e)
      setError(e instanceof Error ? e.message : 'Erreur inconnue')
    } finally {
      setLoading(false)
      abortRef.current = null
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

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
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
    <div className="max-w-3xl mx-auto flex flex-col animate-fade-in">
      {/* Bandeau d'entête/inspecteur supprimé pour alléger l'UI — les détails restent disponibles dans les bulles. */}

      {messages.length === 0 ? (
        // État vide: contenu figé au centre de l'écran, sans scroll
        <div className="fixed inset-0 z-0 flex items-center justify-center pointer-events-none">
          {loading ? (
            <div className="flex justify-center py-2">
              <Loader text="Streaming…" />
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2 animate-fade-in">
              <img
                src={`${import.meta.env.BASE_URL}insight.svg`}
                alt="Logo FoyerInsight"
                className="h-12 w-12 md:h-16 md:w-16 opacity-80"
              />
              <h2 className="text-2xl md:text-3xl font-semibold tracking-tight text-primary-900 opacity-80">
                Discutez avec vos données
              </h2>
            </div>
          )}
        </div>
      ) : (
        <div ref={listRef} className="p-4 space-y-4 pb-32">
          <>
            {messages.map((message, index) => (
              <MessageBubble
                key={message.id ?? index}
                message={message}
                onSaveChart={onSaveChart}
              />
            ))}
            {loading && (
              <div className="flex justify-center py-2">
                <Loader text="Streaming…" />
              </div>
            )}
          </>
        </div>
      )}

      {error && (
        <div className="mx-4 mb-4 bg-red-50 border-2 border-red-200 rounded-lg p-3 animate-fade-in">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Barre de composition fixe en bas de page (container transparent) */}
      <div className="fixed bottom-0 left-0 right-0 z-40 bg-transparent">
        <div className="max-w-3xl mx-auto px-4 py-2">
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
                // Neutralise toute variation visuelle au focus
                'focus:!border-primary-200 focus:!ring-0 focus:!ring-transparent focus:!ring-offset-0 focus:!outline-none',
                'focus-visible:!border-primary-200 focus-visible:!ring-0 focus-visible:!ring-transparent focus-visible:!ring-offset-0 focus-visible:!outline-none',
                // Centre verticalement le texte saisi comme le placeholder
                'leading-[48px] placeholder:text-primary-400',
                'text-left whitespace-nowrap'
              )}
            />
            {/* Toggle MCP Chart intégré dans la zone de saisie */}
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
            {/* Bouton contextuel (même taille/emplacement): Envoyer ↔ Annuler */}
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
          {/* Bouton Annuler séparé supprimé: l'icône de droite devient Annuler pendant le streaming */}
        </div>
      </div>
    </div>
  )
}

interface MessageBubbleProps {
  message: Message
  onSaveChart?: (messageId: string) => void
}

function MessageBubble({ message, onSaveChart }: MessageBubbleProps) {
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
          </div>
        )}
        {!isUser && message.details && (message.details.steps?.length || message.details.plan) ? (
          <div className="mt-2 text-xs">
            <button
              className="underline text-primary-600"
              onClick={() => setShowDetails(v => !v)}
            >
              {showDetails ? 'Masquer' : 'Afficher'} les détails de la requête
            </button>
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
