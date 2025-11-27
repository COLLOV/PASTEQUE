import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '@/services/api'
import { Button, Card, Loader } from '@/components/ui'
import type { AdminFeedbackEntry } from '@/types/chat'
import { HiArrowPath, HiHandThumbDown, HiHandThumbUp } from 'react-icons/hi2'
import clsx from 'clsx'

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function truncate(value: string, max = 160): string {
  if (!value) return ''
  if (value.length <= max) return value
  return `${value.slice(0, Math.max(0, max - 3))}...`
}

export default function FeedbackAdmin() {
  const [items, setItems] = useState<AdminFeedbackEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [archiving, setArchiving] = useState<Set<number>>(() => new Set())
  const navigate = useNavigate()

  const loadFeedback = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await apiFetch<AdminFeedbackEntry[]>('/feedback/admin')
      setItems(res ?? [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Chargement des feedbacks impossible.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadFeedback()
  }, [loadFeedback])

  const openConversation = (conversationId: number, messageId: number) => {
    const params = new URLSearchParams({
      conversation_id: String(conversationId),
      message_id: String(messageId),
    })
    navigate(`/chat?${params.toString()}`)
  }

  async function archive(id: number) {
    setArchiving(prev => new Set(prev).add(id))
    try {
      const res = await apiFetch<AdminFeedbackEntry>(`/feedback/${id}/archive`, { method: 'POST' })
      setItems(prev => prev.filter(it => it.id !== id && !it.is_archived))
      if (res && res.is_archived) {
        // optionally keep archived list? spec: hide once seen
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Archivage impossible.')
    } finally {
      setArchiving(prev => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }

  return (
    <div className="max-w-5xl mx-auto animate-fade-in space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-primary-950 mb-1">Feedback</h2>
          <p className="text-sm text-primary-600">
            Pouces laissés sur les réponses du LLM. Cliquez pour rouvrir la conversation.
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => { void loadFeedback() }}
          disabled={loading}
          className="!rounded-full"
        >
          {loading ? 'Actualisation...' : (
            <span className="inline-flex items-center gap-2">
              <HiArrowPath className="w-4 h-4" />
              Rafraichir
            </span>
          )}
        </Button>
      </div>

      <Card variant="elevated">
        {loading ? (
          <div className="py-12 flex justify-center">
            <Loader text="Chargement des feedbacks..." />
          </div>
        ) : error ? (
          <div className="text-sm text-red-600 py-4">{error}</div>
        ) : items.length === 0 ? (
          <div className="text-sm text-primary-600 py-4">Aucun feedback pour le moment.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full border border-primary-100 rounded-lg overflow-hidden">
              <thead className="bg-primary-50">
                <tr>
                  <th className="text-left text-xs font-semibold uppercase tracking-wide text-primary-600 px-4 py-3 border-b border-primary-100">
                    Vote
                  </th>
                  <th className="text-left text-xs font-semibold uppercase tracking-wide text-primary-600 px-4 py-3 border-b border-primary-100">
                    Message
                  </th>
                  <th className="text-left text-xs font-semibold uppercase tracking-wide text-primary-600 px-4 py-3 border-b border-primary-100">
                    Conversation
                  </th>
                  <th className="text-left text-xs font-semibold uppercase tracking-wide text-primary-600 px-4 py-3 border-b border-primary-100">
                    Auteur
                  </th>
                  <th className="text-left text-xs font-semibold uppercase tracking-wide text-primary-600 px-4 py-3 border-b border-primary-100">
                    Date
                  </th>
                  <th className="text-right text-xs font-semibold uppercase tracking-wide text-primary-600 px-4 py-3 border-b border-primary-100">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map(entry => {
                  const isUp = entry.value === 'up'
                  return (
                    <tr key={entry.id} className="odd:bg-white even:bg-primary-25">
                      <td className="px-4 py-3 border-b border-primary-100">
                        <span
                          className={clsx(
                            'inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold border',
                            isUp
                              ? 'bg-green-50 text-green-700 border-green-200'
                              : 'bg-red-50 text-red-700 border-red-200'
                          )}
                        >
                          {isUp ? <HiHandThumbUp className="w-4 h-4" /> : <HiHandThumbDown className="w-4 h-4" />}
                          {isUp ? 'Pouce en haut' : 'Pouce en bas'}
                        </span>
                      </td>
                      <td className="px-4 py-3 border-b border-primary-100 align-top">
                        <div className="text-sm font-medium text-primary-900 break-words">
                          {truncate(entry.message_content, 180)}
                        </div>
                        <div className="text-[11px] text-primary-500 mt-1">
                          Réponse du {formatDate(entry.message_created_at)}
                        </div>
                      </td>
                      <td className="px-4 py-3 border-b border-primary-100 align-top">
                        <div className="text-sm font-medium text-primary-900">
                          {entry.conversation_title || `Conversation #${entry.conversation_id}`}
                        </div>
                        <div className="text-[11px] text-primary-500 mt-1">
                          ID {entry.conversation_id}
                        </div>
                      </td>
                      <td className="px-4 py-3 border-b border-primary-100 align-top">
                        <div className="text-sm text-primary-900">
                          {entry.author_username}
                        </div>
                        {entry.owner_username && entry.owner_username !== entry.author_username && (
                          <div className="text-[11px] text-primary-500">
                            Conversation de {entry.owner_username}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 border-b border-primary-100 align-top text-sm text-primary-700">
                        {formatDate(entry.created_at)}
                      </td>
                      <td className="px-4 py-3 border-b border-primary-100 align-top text-right">
                        <div className="flex items-center justify-end gap-2">
                          <Button
                            size="xs"
                            variant="secondary"
                            onClick={() => openConversation(entry.conversation_id, entry.message_id)}
                            className="!rounded-full"
                          >
                            Ouvrir
                          </Button>
                          <Button
                            size="xs"
                            variant="ghost"
                            onClick={() => archive(entry.id)}
                            disabled={archiving.has(entry.id)}
                            className="!rounded-full"
                          >
                            {archiving.has(entry.id) ? 'Archivage…' : 'Archiver'}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
