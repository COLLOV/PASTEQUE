import { useState, useRef, useEffect, KeyboardEvent, ChangeEvent } from 'react'
import { apiFetch } from '@/services/api'
import { Button, Textarea, Loader } from '@/components/ui'
import type {
  Message,
  ChatCompletionRequest,
  ChatCompletionResponse,
  ChartGenerationResponse
} from '@/types/chat'
import { HiPaperAirplane, HiArrowPath } from 'react-icons/hi2'
import clsx from 'clsx'

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [chartMode, setChartMode] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!listRef.current) return
    listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages, loading])

  function onToggleChartMode(e: ChangeEvent<HTMLInputElement>) {
    setChartMode(e.target.checked)
    setError('')
  }

  async function onSend() {
    const text = input.trim()
    if (!text || loading) return
    setError('')
    const userMessage: Message = { role: 'user', content: text }
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
              role: 'assistant',
              content: chartUrl,
              chartUrl,
              chartTitle: res?.chart_title,
              chartDescription: res?.chart_description,
              chartTool: res?.tool_name
            }
          : {
              role: 'assistant',
              content: "Impossible de générer un graphique."
            }
        setMessages(prev => [...prev, assistantMessage])
      } else {
        const res = await apiFetch<ChatCompletionResponse>('/chat/completions', {
          method: 'POST',
          body: JSON.stringify({ messages: next } as ChatCompletionRequest)
        })
        const reply = res?.reply ?? ''
        setMessages(prev => [...prev, { role: 'assistant', content: reply }])
      }
    } catch (e) {
      console.error(e)
      setError(e instanceof Error ? e.message : 'Erreur inconnue')
    } finally {
      setLoading(false)
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
    }
  }

  function onReset() {
    setMessages([])
    setError('')
  }

  return (
    <div className="max-w-5xl mx-auto h-[calc(100vh-12rem)] flex flex-col animate-fade-in">
      <div className="px-4 py-3 border-b border-primary-100 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold text-primary-900">Chat</h2>
          <p className="text-xs text-primary-500">
            Activez MCP Chart pour générer un graphique avec les CSV locaux.
          </p>
        </div>
        <label className="inline-flex items-center gap-2 text-sm text-primary-700 cursor-pointer">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-primary-400 text-primary-600 focus:ring-primary-500"
            checked={chartMode}
            onChange={onToggleChartMode}
          />
          <span>Activer MCP Chart</span>
        </label>
      </div>

      <div
        ref={listRef}
        className="flex-1 overflow-y-auto p-4 space-y-4"
      >
        {messages.length === 0 && !loading ? (
          <div className="flex items-center justify-center h-full">
            <h2 className="text-3xl font-light text-primary-400 animate-fade-in">
              Discutez avec vos données
            </h2>
          </div>
        ) : (
          <>
            {messages.map((message, index) => (
              <MessageBubble key={index} message={message} />
            ))}
            {loading && (
              <div className="flex justify-center py-4">
                <Loader text="Le modèle écrit…" />
              </div>
            )}
          </>
        )}
      </div>

      {error && (
        <div className="mx-4 mb-4 bg-red-50 border-2 border-red-200 rounded-lg p-3 animate-fade-in">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      <div className="p-4 bg-primary-50">
        <div className="space-y-3">
          <Textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Écrivez votre message… (Entrée pour envoyer, Maj+Entrée pour nouvelle ligne)"
            rows={3}
            fullWidth
            className="resize-none"
          />
          <div className="flex gap-2 justify-end">
            <Button
              variant="secondary"
              onClick={onReset}
              disabled={loading}
              size="sm"
            >
              <HiArrowPath className="w-4 h-4 mr-2" />
              Réinitialiser
            </Button>
            <Button
              onClick={onSend}
              disabled={loading || !input.trim()}
              size="sm"
            >
              <HiPaperAirplane className="w-4 h-4 mr-2" />
              Envoyer
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

interface MessageBubbleProps {
  message: Message
}

function MessageBubble({ message }: MessageBubbleProps) {
  const { role, content, chartUrl, chartTitle, chartDescription, chartTool } = message
  const isUser = role === 'user'
  return (
    <div
      className={clsx(
        'flex',
        isUser ? 'justify-end' : 'justify-start'
      )}
    >
      <div
        className={clsx(
          'animate-slide-up rounded-lg px-4 py-3 shadow-sm',
          isUser ? 'max-w-[75%] bg-primary-950 text-white' : 'max-w-full bg-white border border-primary-100'
        )}
      >
        <div className="flex items-center gap-2 text-xs font-medium mb-1.5 text-primary-300">
          {isUser ? 'Vous' : 'Assistant'}
        </div>
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
          </div>
        ) : (
          <div className={clsx(
            'text-sm whitespace-pre-wrap leading-relaxed',
            isUser ? '' : 'text-primary-950'
          )}>
            {content}
          </div>
        )}
      </div>
    </div>
  )
}
