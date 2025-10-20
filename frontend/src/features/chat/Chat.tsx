import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import { apiFetch } from '@/services/api'
import { Button, Textarea, Loader } from '@/components/ui'
import type { Message, ChatCompletionRequest, ChatCompletionResponse } from '@/types/chat'
import { HiPaperAirplane, HiArrowPath } from 'react-icons/hi2'
import clsx from 'clsx'

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!listRef.current) return
    listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages, loading])

  async function onSend() {
    const text = input.trim()
    if (!text || loading) return
    setError('')
    const next = [...messages, { role: 'user' as const, content: text }]
    setMessages(next)
    setInput('')
    setLoading(true)
    try {
      const res = await apiFetch<ChatCompletionResponse>('/chat/completions', {
        method: 'POST',
        body: JSON.stringify({ messages: next } as ChatCompletionRequest)
      })
      const reply = res?.reply ?? ''
      setMessages(prev => [...prev, { role: 'assistant', content: reply }])
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
              {messages.map((m, i) => (
                <MessageBubble key={i} role={m.role} content={m.content} />
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
  role: 'user' | 'assistant'
  content: string
}

function MessageBubble({ role, content }: MessageBubbleProps) {
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
          'animate-slide-up',
          isUser ? 'max-w-[75%] rounded-lg px-4 py-3 shadow-sm bg-primary-950 text-white' : 'max-w-full'
        )}
      >
        {isUser && (
          <div className="text-xs font-medium mb-1.5 text-primary-200">
            Vous
          </div>
        )}
        <div className={clsx(
          'text-sm whitespace-pre-wrap leading-relaxed',
          isUser ? '' : 'text-primary-950'
        )}>
          {content}
        </div>
      </div>
    </div>
  )
}
