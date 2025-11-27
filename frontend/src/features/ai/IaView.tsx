import { useEffect, useMemo, useRef, useState } from 'react'
import { Card, Loader, Button } from '@/components/ui'
import { apiFetch } from '@/services/api'
import type {
  CategorySubCategoryCount,
  DataOverviewResponse,
  DataSourceOverview,
  TableExplorePreview,
  TableRow,
} from '@/types/data'
import { HiChevronRight, HiSparkles, HiOutlineTableCells } from 'react-icons/hi2'

type CategoryNode = {
  name: string
  total: number
  subCategories: { name: string; count: number }[]
}

type Selection = {
  source: string
  category: string
  subCategory: string
}

const PAGE_SIZE = 25

function buildCategoryNodes(breakdown?: CategorySubCategoryCount[]): CategoryNode[] {
  if (!breakdown?.length) return []

  const categoryMap = new Map<string, Map<string, number>>()
  const totals = new Map<string, number>()

  for (const item of breakdown) {
    const category = item.category?.trim()
    const subCategory = item.sub_category?.trim()
    if (!category || !subCategory) continue

    if (!categoryMap.has(category)) {
      categoryMap.set(category, new Map())
    }
    const subMap = categoryMap.get(category)!
    subMap.set(subCategory, (subMap.get(subCategory) ?? 0) + item.count)
    totals.set(category, (totals.get(category) ?? 0) + item.count)
  }

  return Array.from(categoryMap.entries())
    .map(([category, subMap]) => ({
      name: category,
      total: totals.get(category) ?? 0,
      subCategories: Array.from(subMap.entries())
        .map(([name, count]) => ({ name, count }))
        .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name)),
    }))
    .sort((a, b) => b.total - a.total || a.name.localeCompare(b.name))
}

export default function IaView() {
  const [overview, setOverview] = useState<DataOverviewResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [selection, setSelection] = useState<Selection | null>(null)
  const [preview, setPreview] = useState<TableExplorePreview | null>(null)
  const [previewError, setPreviewError] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)
  const [page, setPage] = useState(0)
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc')
  const [matchingRows, setMatchingRows] = useState(0)
  const [dateBounds, setDateBounds] = useState<{ min?: string; max?: string }>({})
  const [pendingRange, setPendingRange] = useState<{ from?: string; to?: string } | null>(null)
  const [appliedRange, setAppliedRange] = useState<{ from?: string; to?: string } | null>(null)
  const selectionKeyRef = useRef<string | null>(null)
  const requestRef = useRef(0)

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

  const sourcesWithCategories = useMemo(
    () => (overview?.sources ?? []).filter(src => (src.category_breakdown?.length ?? 0) > 0),
    [overview]
  )
  const hasDateDomain = Boolean(dateBounds.min && dateBounds.max)

  const totalCategoryPairs = useMemo(
    () =>
      sourcesWithCategories.reduce(
        (acc, src) => acc + (src.category_breakdown?.length ?? 0),
        0
      ),
    [sourcesWithCategories]
  )

  const fetchPreview = (
    sel: Selection,
    pageIndex: number,
    direction: 'asc' | 'desc',
    range: { from?: string; to?: string } | null = appliedRange
  ) => {
    const offset = pageIndex * PAGE_SIZE
    setPreview(null)
    setPreviewError('')
    setPreviewLoading(true)
    const requestId = requestRef.current + 1
    requestRef.current = requestId

    const params = new URLSearchParams({
      category: sel.category,
      sub_category: sel.subCategory,
      limit: String(PAGE_SIZE),
      offset: String(offset),
    })
    if (range?.from && hasDateDomain) {
      params.set('date_from', range.from)
    }
    if (range?.to && hasDateDomain) {
      params.set('date_to', range.to)
    }
    if (hasDateDomain) {
      params.set('sort_date', direction)
    }

    void (async () => {
      try {
        const res = await apiFetch<TableExplorePreview>(
          `/data/explore/${encodeURIComponent(sel.source)}?${params.toString()}`
        )
        if (requestRef.current !== requestId) return
        setPreview(res ?? null)
        setMatchingRows(res?.matching_rows ?? 0)
        if (range) {
          setAppliedRange(range)
        }
        if (res?.date_min && res?.date_max) {
          setDateBounds({ min: res.date_min, max: res.date_max })
          if (!pendingRange) {
            setPendingRange({ from: res.date_min, to: res.date_max })
          }
        }
      } catch (err) {
        if (requestRef.current !== requestId) return
        setPreviewError(
          err instanceof Error
            ? err.message
            : "Impossible de charger les données pour cette sélection."
        )
        setMatchingRows(0)
      } finally {
        if (requestRef.current === requestId) {
          setPreviewLoading(false)
        }
      }
    })()
  }

  const handleSelect = (source: string, category: string, subCategory: string) => {
    const nextSelection: Selection = { source, category, subCategory }
    setSelection(nextSelection)
    setPage(0)
    setMatchingRows(0)
    setDateBounds({})
    setPendingRange(null)
    setAppliedRange(null)
    selectionKeyRef.current = `${source}::${category}::${subCategory}`
    fetchPreview(nextSelection, 0, sortDirection, null)
  }

  const handlePageChange = (nextPage: number) => {
    if (!selection) return
    if (nextPage < 0) return
    const total = matchingRows || preview?.matching_rows || 0
    const maxPage = total ? Math.max(Math.ceil(total / PAGE_SIZE) - 1, 0) : 0
    const target = Math.min(nextPage, maxPage)
    setPage(target)
    fetchPreview(selection, target, sortDirection, appliedRange)
  }

  const handleToggleSort = () => {
    if (!selection) return
    if (!hasDateDomain) return
    const nextDirection = sortDirection === 'desc' ? 'asc' : 'desc'
    setSortDirection(nextDirection)
    setPage(0)
    fetchPreview(selection, 0, nextDirection, appliedRange)
  }

  const handleApplyRange = () => {
    if (!selection || !pendingRange || !hasDateDomain) return
    setPage(0)
    fetchPreview(selection, 0, sortDirection, pendingRange)
  }

  const handleResetRange = () => {
    if (!selection || !hasDateDomain || !dateBounds.min || !dateBounds.max) return
    const fullRange = { from: dateBounds.min, to: dateBounds.max }
    setPendingRange(fullRange)
    setPage(0)
    fetchPreview(selection, 0, sortDirection, fullRange)
  }

  useEffect(() => {
    if (!selection) {
      setDateBounds({})
      setPendingRange(null)
      setAppliedRange(null)
      return
    }
    if (preview?.date_min && preview?.date_max) {
      setDateBounds({ min: preview.date_min, max: preview.date_max })
      const selectionKey = `${selection.source}::${selection.category}::${selection.subCategory}`
      if (!pendingRange || selectionKeyRef.current !== selectionKey) {
        setPendingRange({ from: preview.date_min, to: preview.date_max })
      }
      selectionKeyRef.current = selectionKey
    }
  }, [selection, preview?.date_min, preview?.date_max, pendingRange])

  return (
    <div className="max-w-7xl mx-auto space-y-6 animate-fade-in">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary-900 text-white rounded-lg">
            <HiSparkles className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-primary-950">Vue IA</h2>
            <p className="text-primary-600">
              Naviguez par Category / Sub Category pour inspecter les données cliquables.
            </p>
          </div>
        </div>
        <div className="text-right text-sm text-primary-600">
          {overview?.generated_at ? (
            <span className="font-semibold text-primary-900">
              Snapshot : {new Date(overview.generated_at).toLocaleString('fr-FR')}
            </span>
          ) : (
            'Chargement…'
          )}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card variant="elevated" className="flex items-center gap-3">
          <div className="p-3 bg-primary-900 rounded-md text-white flex items-center justify-center">
            <HiOutlineTableCells className="w-5 h-5" />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-primary-500">
              Sources avec Category
            </p>
            <p className="text-2xl font-bold text-primary-950">{sourcesWithCategories.length}</p>
            <p className="text-xs text-primary-500">Colonnes Category + Sub Category détectées</p>
          </div>
        </Card>
        <Card variant="elevated" className="flex items-center gap-3">
          <div className="p-3 bg-primary-900 rounded-md text-white flex items-center justify-center">
            <HiChevronRight className="w-5 h-5" />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-primary-500">
              Couples Category / Sub
            </p>
            <p className="text-2xl font-bold text-primary-950">{totalCategoryPairs}</p>
            <p className="text-xs text-primary-500">Répartitions exploitables</p>
          </div>
        </Card>
        {selection ? (
          <Card variant="elevated" className="flex items-center gap-3">
            <div className="p-3 bg-primary-900 rounded-md text-white flex items-center justify-center">
              <HiSparkles className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-wide text-primary-500">
                Sélection active
              </p>
              <p className="text-sm font-semibold text-primary-950 truncate">
                {selection.source} – {selection.category} / {selection.subCategory}
              </p>
              <p className="text-xs text-primary-500">
                Cliquez sur une sous-catégorie pour rafraîchir l’aperçu.
              </p>
            </div>
          </Card>
        ) : (
          <Card variant="elevated" className="flex items-center gap-3">
            <div className="p-3 bg-primary-200 rounded-md text-primary-900 flex items-center justify-center">
              <HiSparkles className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-primary-500">
                Sélection
              </p>
              <p className="text-sm font-semibold text-primary-950">
                Choisissez une catégorie pour voir les lignes
              </p>
              <p className="text-xs text-primary-500">
                Les aperçus sont paginés par blocs de 25 lignes pour rester réactifs.
              </p>
            </div>
          </Card>
        )}
      </div>

      <SelectionPreview
        selection={selection}
        preview={preview}
        loading={previewLoading}
        error={previewError}
        limit={PAGE_SIZE}
        page={page}
        matchingRows={matchingRows || preview?.matching_rows || 0}
        sortDirection={sortDirection}
        onPageChange={handlePageChange}
        onToggleSort={handleToggleSort}
        hasDateDomain={hasDateDomain}
        dateBounds={dateBounds}
        pendingRange={pendingRange}
        onRangeChange={setPendingRange}
        onApplyRange={handleApplyRange}
        onResetRange={handleResetRange}
      />

      {loading ? (
        <Card variant="elevated" className="py-12 flex justify-center">
          <Loader text="Chargement des répartitions Category / Sub Category…" />
        </Card>
      ) : error ? (
        <Card variant="elevated" className="py-6 px-4 text-sm text-red-600">{error}</Card>
      ) : sourcesWithCategories.length === 0 ? (
        <Card variant="elevated" className="py-10 px-4 text-center text-primary-600">
          Aucune source ne contient les colonnes « Category » et « Sub Category » avec des valeurs
          exploitables.
        </Card>
      ) : (
        <div className="space-y-4">
          {sourcesWithCategories.map(source => (
            <SourceCategoryCard key={source.source} source={source} onSelect={handleSelect} />
          ))}
        </div>
      )}
    </div>
  )
}

function SourceCategoryCard({
  source,
  onSelect,
}: {
  source: DataSourceOverview
  onSelect: (source: string, category: string, subCategory: string) => void
}) {
  const categoryNodes = useMemo(
    () => buildCategoryNodes(source.category_breakdown),
    [source.category_breakdown]
  )

  if (!categoryNodes.length) {
    return (
      <Card padding="sm" className="bg-primary-50">
        <div className="flex items-center justify-between gap-2">
          <div>
            <p className="text-sm font-semibold text-primary-900">{source.title}</p>
            <p className="text-xs text-primary-600">{source.source}</p>
          </div>
          <span className="text-xs text-primary-600">Aucune répartition Category/Sub Category</span>
        </div>
      </Card>
    )
  }

  return (
    <Card variant="elevated" padding="md" className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-primary-500">{source.source}</p>
          <h3 className="text-lg font-semibold text-primary-950">{source.title}</h3>
          <p className="text-xs text-primary-500">
            {source.total_rows.toLocaleString('fr-FR')} lignes ·{' '}
            {categoryNodes.length.toLocaleString('fr-FR')} catégories
          </p>
        </div>
        <div className="text-right">
          <p className="text-[11px] text-primary-500">Couples Category/Sub</p>
          <p className="text-lg font-bold text-primary-950">
            {source.category_breakdown?.length.toLocaleString('fr-FR') ?? 0}
          </p>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {categoryNodes.map(node => (
          <div
            key={node.name}
            className="overflow-hidden border border-primary-200 rounded-xl bg-white shadow-sm"
          >
            <div className="flex items-start justify-between px-3 py-2 bg-primary-900 text-white">
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-wide text-primary-100">Catégorie</p>
                <p className="text-sm font-semibold truncate">{node.name}</p>
                <p className="text-[11px] text-primary-100/80">
                  {node.total.toLocaleString('fr-FR')} lignes
                </p>
              </div>
              <span className="text-[11px] font-semibold">
                {node.subCategories.length.toLocaleString('fr-FR')} sous-catégories
              </span>
            </div>
            <div className="flex flex-col divide-y divide-primary-100">
              {node.subCategories.map(sub => (
                <button
                  key={sub.name}
                  type="button"
                  className="flex items-center justify-between px-3 py-2 text-left hover:bg-primary-50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400 border-l-4 border-primary-200"
                  onClick={() => onSelect(source.source, node.name, sub.name)}
                >
                  <div className="min-w-0">
                    <p className="text-[11px] uppercase tracking-wide text-primary-500">
                      Sous-catégorie
                    </p>
                    <p className="text-sm font-semibold text-primary-900 truncate">{sub.name}</p>
                  </div>
                  <span className="text-xs font-semibold text-primary-700">
                    {sub.count.toLocaleString('fr-FR')}
                  </span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

function SelectionPreview({
  selection,
  preview,
  loading,
  error,
  limit,
  page,
  matchingRows,
  sortDirection,
  onPageChange,
  onToggleSort,
  hasDateDomain,
  dateBounds,
  pendingRange,
  onRangeChange,
  onApplyRange,
  onResetRange,
}: {
  selection: Selection | null
  preview: TableExplorePreview | null
  loading: boolean
  error: string
  limit: number
  page: number
  matchingRows: number
  sortDirection: 'asc' | 'desc'
  onPageChange: (nextPage: number) => void
  onToggleSort: () => void
  hasDateDomain: boolean
  dateBounds: { min?: string; max?: string }
  pendingRange: { from?: string; to?: string } | null
  onRangeChange: (range: { from?: string; to?: string } | null) => void
  onApplyRange: () => void
  onResetRange: () => void
}) {
  if (!selection) return null

  const columns = preview?.preview_columns ?? []
  const rows = preview?.preview_rows ?? []
  const totalRows = matchingRows || preview?.matching_rows || 0
  const totalPages = totalRows ? Math.max(1, Math.ceil(totalRows / limit)) : 1
  const currentPage = Math.min(page, totalPages - 1)
  const hasPrev = currentPage > 0
  const hasNext = currentPage < totalPages - 1

  const toTimestamp = (date?: string) => {
    if (!date) return undefined
    const ts = Date.parse(`${date}T00:00:00Z`)
    return Number.isNaN(ts) ? undefined : ts
  }

  const minTs = toTimestamp(dateBounds.min)
  const maxTs = toTimestamp(dateBounds.max)
  const startTs =
    pendingRange?.from && minTs !== undefined
      ? Math.max(minTs, toTimestamp(pendingRange.from) ?? minTs)
      : minTs
  const endTs =
    pendingRange?.to && maxTs !== undefined
      ? Math.min(maxTs, toTimestamp(pendingRange.to) ?? maxTs)
      : maxTs

  const clampAndIso = (value: number | undefined, fallback: number | undefined) => {
    if (value === undefined && fallback === undefined) return undefined
    const target = value ?? fallback ?? 0
    return new Date(target).toISOString().slice(0, 10)
  }

  const handleStartChange = (value: number) => {
    if (minTs === undefined || maxTs === undefined || endTs === undefined) return
    const clamped = Math.min(Math.max(value, minTs), endTs)
    onRangeChange({ from: clampAndIso(clamped, minTs), to: clampAndIso(endTs, maxTs) })
  }

  const handleEndChange = (value: number) => {
    if (minTs === undefined || maxTs === undefined || startTs === undefined) return
    const clamped = Math.max(Math.min(value, maxTs), startTs)
    onRangeChange({ from: clampAndIso(startTs, minTs), to: clampAndIso(clamped, maxTs) })
  }

  const formatDate = (value?: string) => {
    if (!value) return '—'
    const date = new Date(`${value}T00:00:00Z`)
    if (Number.isNaN(date.getTime())) return value
    return date.toLocaleDateString('fr-FR')
  }
  const startValue = startTs ?? minTs ?? 0
  const endValue = endTs ?? maxTs ?? 0

  return (
    <Card variant="outlined" className="space-y-3">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div className="text-sm text-primary-700">
          <span className="font-semibold text-primary-900">{selection.source}</span> ·{' '}
          <span className="font-semibold text-primary-900">{selection.category}</span> /{' '}
          <span className="font-semibold text-primary-900">{selection.subCategory}</span>
        </div>
        {preview ? (
          <div className="text-[11px] text-primary-500">
            {preview.matching_rows.toLocaleString('fr-FR')} lignes correspondantes ·{' '}
            {rows.length.toLocaleString('fr-FR')} affichées sur {limit} par page
          </div>
        ) : null}
      </div>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={onToggleSort}
            disabled={loading || !hasDateDomain}
            className="!rounded-full"
          >
            Tri date {sortDirection === 'desc' ? '↓' : '↑'}
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onPageChange(currentPage - 1)}
            disabled={!hasPrev || loading}
          >
            Précédent
          </Button>
          <span className="text-[11px] text-primary-600">
            Page {currentPage + 1} / {totalPages} · {limit} lignes/page
          </span>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onPageChange(currentPage + 1)}
            disabled={!hasNext || loading}
          >
            Suivant
          </Button>
        </div>
      </div>

      {hasDateDomain && minTs !== undefined && maxTs !== undefined ? (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-[11px] text-primary-600">
            <span>
              De <span className="font-semibold text-primary-900">{formatDate(pendingRange?.from)}</span>
            </span>
            <span>
              À <span className="font-semibold text-primary-900">{formatDate(pendingRange?.to)}</span>
            </span>
          </div>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min={minTs}
              max={maxTs}
              step={86_400_000}
              value={startValue}
              onChange={e => handleStartChange(Number(e.target.value))}
              className="flex-1 accent-primary-900"
            />
            <input
              type="range"
              min={minTs}
              max={maxTs}
              step={86_400_000}
              value={endValue}
              onChange={e => handleEndChange(Number(e.target.value))}
              className="flex-1 accent-primary-700"
            />
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={onApplyRange}
              disabled={loading}
              className="!rounded-full"
            >
              Appliquer le filtre
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={onResetRange}
              disabled={loading}
            >
              Réinitialiser
            </Button>
          </div>
        </div>
      ) : null}

      {loading ? (
        <div className="py-6">
          <Loader text="Chargement de l’aperçu…" />
        </div>
      ) : error ? (
        <p className="text-sm text-red-700">{error}</p>
      ) : !preview || rows.length === 0 ? (
        <p className="text-sm text-primary-600">Aucune ligne trouvée pour cette sélection.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-[12px]">
            <thead>
              <tr className="border-b border-primary-200">
                {columns.map(col => (
                  <th
                    key={col}
                    className="px-2 py-2 font-semibold text-primary-800 whitespace-nowrap"
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => (
                <tr key={idx} className="border-b border-primary-100 last:border-0">
                  {columns.map(col => (
                    <td key={col} className="px-2 py-1 text-primary-800 whitespace-nowrap">
                      {String((row as TableRow)[col] ?? '')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
