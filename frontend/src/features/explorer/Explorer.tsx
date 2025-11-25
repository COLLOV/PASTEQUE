import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Bar, Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  BarElement,
  CategoryScale,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
  Legend,
  type ChartData,
  type ChartOptions,
} from 'chart.js'
import { Card, Loader, Button } from '@/components/ui'
import { apiFetch } from '@/services/api'
import type { DataOverviewResponse, DataSourceOverview, FieldBreakdown, ValueCount } from '@/types/data'
import {
  HiChartBar,
  HiOutlineGlobeAlt,
  HiOutlineSquares2X2,
  HiAdjustmentsHorizontal,
  HiEye,
  HiEyeSlash,
} from 'react-icons/hi2'

type HiddenFieldsState = Record<string, string[]>

ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, Tooltip, Legend)

function formatNumber(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '0'
  return value.toLocaleString('fr-FR')
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('fr-FR')
}

export default function Explorer() {
  const [overview, setOverview] = useState<DataOverviewResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [hiddenFields, setHiddenFields] = useState<HiddenFieldsState>({})

  useEffect(() => {
    async function load() {
      setLoading(true)
      setError('')
      try {
        const res = await apiFetch<DataOverviewResponse>('/data/overview')
        setOverview(res ?? { generated_at: '', sources: [] })
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Chargement impossible.')
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [])

  const sources = overview?.sources ?? []

  const totalRecords = useMemo(
    () => sources.reduce((acc, src) => acc + (src.total_rows ?? 0), 0),
    [sources]
  )

  const totalFields = useMemo(
    () => sources.reduce((acc, src) => acc + (src.fields?.length ?? 0), 0),
    [sources]
  )

  const totalVisibleFields = useMemo(
    () =>
      sources.reduce((acc, src) => {
        const hidden = new Set(hiddenFields[src.source] ?? [])
        const visibleCount = (src.fields ?? []).filter(field => !hidden.has(field.field)).length
        return acc + visibleCount
      }, 0),
    [sources, hiddenFields]
  )

  const toggleFieldVisibility = (source: string, field: string, visible: boolean) => {
    setHiddenFields(prev => {
      const current = new Set(prev[source] ?? [])
      if (visible) {
        current.delete(field)
      } else {
        current.add(field)
      }
      if (current.size === 0) {
        const next = { ...prev }
        delete next[source]
        return next
      }
      return { ...prev, [source]: Array.from(current) }
    })
  }

  const showAllFields = (source: string) => {
    setHiddenFields(prev => {
      const next = { ...prev }
      delete next[source]
      return next
    })
  }

  const hideAllFields = (source: string, fields: FieldBreakdown[]) => {
    setHiddenFields(prev => ({
      ...prev,
      [source]: fields.map(field => field.field),
    }))
  }

  return (
    <div className="max-w-7xl mx-auto animate-fade-in space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-1">
          <h2 className="text-2xl font-bold text-primary-950">Explorer</h2>
          <p className="text-primary-600 max-w-3xl">
            Vision transverse des sources avec découverte automatique des colonnes. Masquez les
            champs inutiles pour focaliser l’analyse sur ce qui compte.
          </p>
        </div>
        {overview?.generated_at ? (
          <div className="text-xs text-primary-500">
            Mis à jour : <span className="font-semibold text-primary-700">{formatDate(overview.generated_at)}</span>
          </div>
        ) : null}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryCard
          icon={<HiOutlineGlobeAlt className="w-5 h-5" />}
          title="Sources couvertes"
          value={formatNumber(sources.length)}
          subtitle="Tables autorisées pour votre compte"
        />
        <SummaryCard
          icon={<HiChartBar className="w-5 h-5" />}
          title="Données totales"
          value={formatNumber(totalRecords)}
          subtitle="Lignes agrégées toutes sources"
        />
        <SummaryCard
          icon={<HiOutlineSquares2X2 className="w-5 h-5" />}
          title="Colonnes détectées"
          value={formatNumber(totalFields)}
          subtitle="Découverte automatique par table"
        />
        <SummaryCard
          icon={<HiAdjustmentsHorizontal className="w-5 h-5" />}
          title="Colonnes affichées"
          value={formatNumber(totalVisibleFields)}
          subtitle="Après masquage éventuel"
        />
      </div>

      {loading ? (
        <Card variant="elevated" className="py-12 flex justify-center">
          <Loader text="Chargement de l’explorateur…" />
        </Card>
      ) : error ? (
        <Card variant="elevated" className="py-6 px-4 text-sm text-red-600">
          {error}
        </Card>
      ) : sources.length === 0 ? (
        <Card variant="elevated" className="py-10 px-4 text-center text-primary-600">
          Aucune source disponible avec vos droits actuels.
        </Card>
      ) : (
        <div className="space-y-4">
          {sources.map(source => (
            <SourceCard
              key={source.source}
              source={source}
              hiddenFields={hiddenFields[source.source] ?? []}
              onToggleField={(field, visible) => toggleFieldVisibility(source.source, field, visible)}
              onHideAll={() => hideAllFields(source.source, source.fields ?? [])}
              onShowAll={() => showAllFields(source.source)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function SummaryCard({
  icon,
  title,
  value,
  subtitle,
}: {
  icon: ReactNode
  title: string
  value: string
  subtitle: string
}) {
  return (
    <Card variant="elevated" className="flex items-center gap-3">
      <div className="p-3 bg-primary-950 rounded-md text-white flex items-center justify-center">
        {icon}
      </div>
      <div className="flex-1">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary-500">{title}</p>
        <p className="text-2xl font-bold text-primary-950 mt-1">{value}</p>
        <p className="text-xs text-primary-500 mt-1">{subtitle}</p>
      </div>
    </Card>
  )
}

function SourceCard({
  source,
  hiddenFields,
  onToggleField,
  onHideAll,
  onShowAll,
}: {
  source: DataSourceOverview
  hiddenFields: string[]
  onToggleField: (field: string, visible: boolean) => void
  onHideAll: () => void
  onShowAll: () => void
}) {
  const hiddenSet = useMemo(() => new Set(hiddenFields), [hiddenFields])
  const visibleFields = source.fields?.filter(field => !hiddenSet.has(field.field)) ?? []

  return (
    <Card variant="elevated" className="p-5 space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-wide text-primary-500">{source.source}</p>
          <h3 className="text-xl font-semibold text-primary-950">{source.title}</h3>
          <p className="text-xs text-primary-500">
            {visibleFields.length} / {source.fields.length} colonnes affichées
          </p>
        </div>
        <div className="text-right">
          <p className="text-sm text-primary-500">Total données</p>
          <p className="text-2xl font-bold text-primary-950">{formatNumber(source.total_rows)}</p>
        </div>
      </div>

      <FieldVisibilitySelector
        fields={source.fields}
        hiddenSet={hiddenSet}
        onToggle={onToggleField}
        onHideAll={onHideAll}
        onShowAll={onShowAll}
      />

      {visibleFields.length === 0 ? (
        <Card padding="sm" className="bg-primary-50">
          <p className="text-sm font-semibold text-primary-800 mb-1">Aucune colonne affichée</p>
          <p className="text-xs text-primary-500">Sélectionnez au moins un champ pour voir les statistiques.</p>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {visibleFields.map(field => (
            <FieldSection key={field.field} field={field} />
          ))}
        </div>
      )}
    </Card>
  )
}

function FieldVisibilitySelector({
  fields,
  hiddenSet,
  onToggle,
  onHideAll,
  onShowAll,
}: {
  fields: FieldBreakdown[]
  hiddenSet: Set<string>
  onToggle: (field: string, visible: boolean) => void
  onHideAll: () => void
  onShowAll: () => void
}) {
  const [open, setOpen] = useState(false)
  const visibleCount = fields.length - hiddenSet.size

  return (
    <div className="border border-primary-100 rounded-lg bg-primary-50/60 p-3 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-primary-800">Gestion des colonnes</p>
          <p className="text-xs text-primary-500">
            {visibleCount} / {fields.length} affichées
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          className="flex items-center gap-2"
          onClick={() => setOpen(prev => !prev)}
        >
          <HiAdjustmentsHorizontal className="w-4 h-4" />
          {open ? 'Fermer' : 'Choisir'}
        </Button>
      </div>

      {open && (
        <>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 max-h-48 overflow-y-auto pr-1">
            {fields.map(field => {
              const isVisible = !hiddenSet.has(field.field)
              return (
                <label
                  key={field.field}
                  className="flex items-center gap-2 text-xs text-primary-700 border border-primary-100 rounded-md bg-white px-2 py-1.5"
                >
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-primary-300 text-primary-950 focus:ring-primary-600"
                    checked={isVisible}
                    onChange={e => onToggle(field.field, e.target.checked)}
                  />
                  <span className="truncate" title={field.label}>
                    {field.label}
                  </span>
                  <span className="text-[10px] text-primary-500">({formatNumber(field.unique_values)} valeurs)</span>
                </label>
              )
            })}
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" size="xs" className="flex items-center gap-1" onClick={onHideAll}>
              <HiEyeSlash className="w-4 h-4" />
              Tout masquer
            </Button>
            <Button variant="secondary" size="xs" className="flex items-center gap-1" onClick={onShowAll}>
              <HiEye className="w-4 h-4" />
              Tout afficher
            </Button>
          </div>
        </>
      )}
    </div>
  )
}

function FieldSection({ field }: { field: FieldBreakdown }) {
  const counts = field.counts ?? []
  if (!counts || counts.length === 0) {
    return (
      <Card padding="sm" className="h-full bg-primary-50">
        <p className="text-sm font-semibold text-primary-800 mb-1">{field.label}</p>
        <p className="text-xs text-primary-500">
          Aucune valeur renseignée ({field.missing_values} ligne(s) manquante(s)).
        </p>
      </Card>
    )
  }

  const limit = field.kind === 'date' ? 18 : 10
  const slice = field.kind === 'date' ? counts.slice(-limit) : counts.slice(0, limit)
  const hasMore = field.truncated || counts.length > slice.length

  return (
    <Card padding="sm" className="h-full">
      <div className="flex items-start justify-between mb-2 gap-2">
        <div className="flex-1">
          <p className="text-sm font-semibold text-primary-800">{field.label}</p>
          <p className="text-[11px] text-primary-500">Champ : {field.field}</p>
        </div>
        <span className="text-[11px] text-primary-500">
          {formatNumber(field.unique_values)} valeurs uniques
        </span>
      </div>

      <div className="text-[11px] text-primary-500 mb-2">
        {field.kind === 'date' ? 'Chronologie par date détectée' : 'Répartition des occurrences'}
      </div>

      {field.kind === 'date' ? <DateTimeline counts={slice} /> : <BarList counts={slice} />}

      {hasMore ? (
        <p className="text-[11px] text-primary-500 mt-2">
          Affichage limité à {slice.length} valeurs (top / dernières selon le type).
        </p>
      ) : null}
    </Card>
  )
}

function DateTimeline({ counts }: { counts: ValueCount[] }) {
  const chartData = useMemo<ChartData<'line'>>(
    () => ({
      labels: counts.map(item => item.label),
      datasets: [
        {
          label: 'Occurrences',
          data: counts.map(item => item.count),
          borderColor: '#0f172a',
          backgroundColor: '#0f172a',
          borderWidth: 2,
          pointRadius: 3,
          pointHoverRadius: 4,
          pointBackgroundColor: '#0f172a',
          tension: 0.25,
        },
      ],
    }),
    [counts]
  )

  const options = useMemo<ChartOptions<'line'>>(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: context => {
              const value = typeof context.raw === 'number' ? context.raw : Number(context.raw ?? 0)
              return `${value.toLocaleString('fr-FR')} enregistrements`
            },
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#52525b', maxRotation: 45, minRotation: 45 },
        },
        y: {
          beginAtZero: true,
          grid: { color: '#e5e7eb' },
          ticks: {
            color: '#52525b',
            callback: value => Number(value).toLocaleString('fr-FR'),
          },
        },
      },
    }),
    []
  )

  return (
    <div className="h-48">
      <Line data={chartData} options={options} />
    </div>
  )
}

function BarList({ counts }: { counts: ValueCount[] }) {
  const chartData = useMemo<ChartData<'bar'>>(
    () => ({
      labels: counts.map(item => item.label),
      datasets: [
        {
          label: 'Occurrences',
          data: counts.map(item => item.count),
          backgroundColor: '#0f172a',
          borderRadius: 8,
          barThickness: 18,
          maxBarThickness: 24,
        },
      ],
    }),
    [counts]
  )

  const options = useMemo<ChartOptions<'bar'>>(
    () => ({
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: context => {
              const value = typeof context.raw === 'number' ? context.raw : Number(context.raw ?? 0)
              return `${value.toLocaleString('fr-FR')} enregistrements`
            },
          },
        },
      },
      scales: {
        x: {
          beginAtZero: true,
          grid: { color: '#e5e7eb' },
          ticks: {
            color: '#52525b',
            callback: value => Number(value).toLocaleString('fr-FR'),
          },
        },
        y: {
          grid: { display: false },
          ticks: {
            color: '#52525b',
            autoSkip: false,
          },
        },
      },
      layout: { padding: { top: 4, right: 8, bottom: 4, left: 0 } },
    }),
    []
  )

  const dynamicHeight = Math.max(140, counts.length * 28)

  return (
    <div style={{ height: `${dynamicHeight}px` }}>
      <Bar data={chartData} options={options} />
    </div>
  )
}
