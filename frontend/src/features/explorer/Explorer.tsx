import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Card, Loader } from '@/components/ui'
import { apiFetch } from '@/services/api'
import type {
  DataOverviewResponse,
  DataSourceOverview,
  DimensionBreakdown,
  DimensionCount,
} from '@/types/data'
import {
  HiChartBar,
  HiOutlineGlobeAlt,
  HiOutlineClock,
  HiOutlineSquares2X2,
} from 'react-icons/hi2'

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
  const sourcesWithDimensions = useMemo(
    () =>
      sources.reduce((acc, src) => {
        const dims = Array.isArray(src.columns) ? src.columns.length : 0
        return acc + dims
      }, 0),
    [sources]
  )

  return (
    <div className="max-w-7xl mx-auto animate-fade-in space-y-6">
      <div className="flex flex-col gap-2">
        <h2 className="text-2xl font-bold text-primary-950">Explorer</h2>
        <p className="text-primary-600 max-w-3xl">
          Vision transverse des sources de données : volume global, répartition temporelle et découpage
          par département, campagne et domaine lorsqu’ils sont disponibles.
        </p>
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
          title="Dimensions actives"
          value={formatNumber(sourcesWithDimensions)}
          subtitle="Dates, départements, campagnes, domaines"
        />
        <SummaryCard
          icon={<HiOutlineClock className="w-5 h-5" />}
          title="Généré le"
          value={formatDate(overview?.generated_at)}
          subtitle="Heure locale"
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
            <SourceCard key={source.source} source={source} />
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

function SourceCard({ source }: { source: DataSourceOverview }) {
  const dimensions: DimensionBreakdown[] = Array.isArray(source.columns) ? source.columns : []

  return (
    <Card variant="elevated" className="p-5 space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-wide text-primary-500">{source.source}</p>
          <h3 className="text-xl font-semibold text-primary-950">{source.title}</h3>
        </div>
        <div className="text-right">
          <p className="text-sm text-primary-500">Total données</p>
          <p className="text-2xl font-bold text-primary-950">{formatNumber(source.total_rows)}</p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {dimensions.map(dimension => (
          <DimensionSection
            key={dimension.field}
            title={dimension.label}
            dimension={dimension}
          />
        ))}
      </div>
    </Card>
  )
}

function DimensionSection({
  title,
  dimension,
}: {
  title: string
  dimension: DimensionBreakdown | null | undefined
}) {
  if (!dimension) {
    return (
      <Card padding="sm" className="h-full bg-primary-50">
        <p className="text-sm font-semibold text-primary-800 mb-1">{title}</p>
        <p className="text-xs text-primary-500">Donnée non disponible pour cette source.</p>
      </Card>
    )
  }

  const counts = dimension.counts
  if (!counts || counts.length === 0) {
    return (
      <Card padding="sm" className="h-full bg-primary-50">
        <p className="text-sm font-semibold text-primary-800 mb-1">{title}</p>
        <p className="text-xs text-primary-500">Aucune valeur renseignée.</p>
      </Card>
    )
  }

  const limit = dimension.field === 'creation_date' || dimension.field.includes('date') ? 12 : 6
  const isDateDimension = dimension.field.includes('date')
  const sliced = isDateDimension ? counts.slice(-limit) : counts.slice(0, limit)

  return (
    <Card padding="sm" className="h-full">
      <div className="flex items-center justify-between mb-2">
        <div>
          <p className="text-sm font-semibold text-primary-800">{title}</p>
          <p className="text-xs text-primary-500">Champ : {dimension.label}</p>
        </div>
        <span className="text-[11px] text-primary-500">{counts.length} valeurs</span>
      </div>

      {isDateDimension ? (
        <DateTimeline counts={sliced} />
      ) : (
        <BarList counts={sliced} />
      )}
    </Card>
  )
}

function DateTimeline({ counts }: { counts: DimensionCount[] }) {
  const max = counts.reduce((acc, item) => Math.max(acc, item.count), 0) || 1
  return (
    <div className="flex items-end gap-1 h-28">
      {counts.map(item => {
        const height = Math.max((item.count / max) * 100, 6)
        return (
          <div key={item.label} className="flex-1 flex flex-col items-center gap-1">
            <div className="w-full bg-primary-100 rounded-sm overflow-hidden h-20 flex items-end">
              <div
                className="w-full bg-primary-950"
                style={{ height: `${height}%` }}
                aria-label={`${item.label}: ${item.count}`}
              />
            </div>
            <span className="text-[10px] text-primary-500">{item.label}</span>
          </div>
        )
      })}
    </div>
  )
}

function BarList({ counts }: { counts: DimensionCount[] }) {
  const max = counts.reduce((acc, item) => Math.max(acc, item.count), 0) || 1
  return (
    <div className="space-y-2">
      {counts.map(item => {
        const width = Math.max((item.count / max) * 100, 6)
        return (
          <div key={item.label} className="flex items-center gap-2">
            <span
              className="w-32 text-xs text-primary-600 truncate"
              title={item.label}
            >
              {item.label}
            </span>
            <div className="flex-1 h-2 rounded-full bg-primary-100 overflow-hidden">
              <div
                className="h-full bg-primary-950"
                style={{ width: `${width}%` }}
                aria-label={`${item.label}: ${item.count}`}
              />
            </div>
            <span className="w-10 text-right text-xs font-semibold text-primary-900">
              {item.count.toLocaleString('fr-FR')}
            </span>
          </div>
        )
      })}
    </div>
  )
}
