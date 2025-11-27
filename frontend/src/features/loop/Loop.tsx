import { useEffect, useState, useCallback } from 'react'
import { Card, Button, Loader } from '@/components/ui'
import { apiFetch } from '@/services/api'
import { getAuth } from '@/services/auth'
import type { LoopOverview, LoopSummary } from '@/types/loop'
import { HiArrowPath, HiClock, HiOutlineDocumentText } from 'react-icons/hi2'
import { marked, Renderer } from 'marked'

function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

const escapeHtml = (text: string) =>
  text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

const renderer = new Renderer()
renderer.heading = (text) => `<p class="text-primary-900 font-semibold text-base mt-2">${text}</p>`
renderer.paragraph = (text) => `<p class="text-primary-800 text-sm leading-relaxed">${text}</p>`
renderer.list = (body) =>
  `<ul class="list-disc pl-5 space-y-1 text-primary-800 text-sm">${body}</ul>`
renderer.listitem = (text) => `<li>${text}</li>`
renderer.hr = () => `<hr class="border-primary-200 my-2" />`

marked.use({ renderer, mangle: false, headerIds: false, breaks: true, gfm: true })

function renderMarkdown(content: string) {
  const safe = escapeHtml(content || '')
  const html = marked.parse(safe) as string
  return (
    <div
      className="space-y-2"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

function SummaryList({ title, summaries }: { title: string; summaries: LoopSummary[] }) {
  if (summaries.length === 0) {
    return (
      <Card variant="elevated" className="p-6">
        <p className="text-primary-600 text-sm">Aucun résumé disponible.</p>
      </Card>
    )
  }

  return (
    <div className="space-y-3 max-w-6xl w-full">
      <div className="flex items-center gap-2">
        <HiOutlineDocumentText className="w-5 h-5 text-primary-500" />
        <h3 className="text-lg font-semibold text-primary-900">{title}</h3>
      </div>
      <div className="flex flex-col gap-4">
        {summaries.map(item => (
          <Card
            key={`${item.kind}-${item.id}`}
            variant="elevated"
            className="flex flex-col gap-3 w-full"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-wide text-primary-500">{item.kind === 'weekly' ? 'Hebdomadaire' : 'Mensuel'}</p>
                <h4 className="text-xl font-semibold text-primary-950">{item.period_label}</h4>
                <p className="text-sm text-primary-600">
                  {formatDate(item.period_start)} → {formatDate(item.period_end)}
                </p>
              </div>
              <div className="text-right text-sm text-primary-600">
                <p className="font-medium text-primary-900">{item.ticket_count} tickets</p>
                <p className="flex items-center justify-end gap-1 text-xs text-primary-500">
                  <HiClock className="w-4 h-4" />
                  Généré le {formatDate(item.created_at)}
                </p>
              </div>
            </div>
            {renderMarkdown(item.content)}
          </Card>
        ))}
      </div>
    </div>
  )
}

export default function Loop() {
  const [overview, setOverview] = useState<LoopOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const auth = getAuth()
  const isAdmin = Boolean(auth?.isAdmin)

  const fetchOverview = useCallback(async () => {
    setError('')
    setRefreshing(true)
    try {
      const data = await apiFetch<LoopOverview>('/loop/overview')
      setOverview(data ?? null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Chargement impossible')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    void fetchOverview()
  }, [fetchOverview])

  const config = overview?.config ?? null

  return (
    <div className="max-w-7xl mx-auto animate-fade-in space-y-6">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div>
          <p className="text-sm uppercase tracking-wide text-primary-500">Loop</p>
          <h2 className="text-2xl font-bold text-primary-950">Résumés hebdo & mensuels</h2>
          <p className="text-primary-600">
            Synthèse des tickets par semaine et par mois, avec points majeurs et plan d'action.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={fetchOverview}
            disabled={refreshing}
            className="inline-flex items-center gap-2"
          >
            <HiArrowPath className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            Actualiser
          </Button>
        </div>
      </div>

      {loading ? (
        <Card variant="elevated" className="py-12 flex justify-center">
          <Loader text="Chargement des résumés Loop…" />
        </Card>
      ) : error ? (
        <Card variant="elevated" className="py-6 px-4 border border-red-200 bg-red-50 text-red-700">
          <p className="text-sm">{error}</p>
        </Card>
      ) : (
        <>
          <Card variant="elevated" className="p-5 flex flex-col gap-2">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
              <div>
                <p className="text-sm text-primary-500">Configuration actuelle</p>
                {config ? (
                  <div className="text-primary-900">
                    <p className="font-semibold">{config.table_name}</p>
                    <p className="text-sm text-primary-600">
                      Colonne texte : <span className="font-medium">{config.text_column}</span> — Colonne date :{' '}
                      <span className="font-medium">{config.date_column}</span>
                    </p>
                  </div>
                ) : (
                  <p className="text-primary-700">
                    Aucune configuration définie. {isAdmin ? 'Renseignez les colonnes dans la vue Admin.' : 'Demandez à un administrateur de configurer les colonnes.'}
                  </p>
                )}
              </div>
              <div className="text-sm text-primary-600">
                Dernière génération : <span className="font-medium text-primary-900">{formatDate(overview?.last_generated_at)}</span>
              </div>
            </div>
          </Card>

          {!config ? (
            <Card variant="elevated" className="p-6">
              <p className="text-primary-700 text-sm">
                Les résumés seront disponibles dès qu&apos;un administrateur aura choisi les colonnes de texte et de date dans la section
                Admin &gt; Loop.
              </p>
            </Card>
          ) : (
            <div className="space-y-6">
              <SummaryList title="Vue mensuelle" summaries={(overview?.monthly ?? []).slice(0, 1)} />
              <SummaryList title="Vue hebdomadaire" summaries={(overview?.weekly ?? []).slice(0, 1)} />
            </div>
          )}
        </>
      )}
    </div>
  )
}
