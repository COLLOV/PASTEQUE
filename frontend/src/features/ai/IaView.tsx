import { useEffect, useMemo, useRef, useState } from 'react'
import { Card, Loader } from '@/components/ui'
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

  const totalCategoryPairs = useMemo(
    () =>
      sourcesWithCategories.reduce(
        (acc, src) => acc + (src.category_breakdown?.length ?? 0),
        0
      ),
    [sourcesWithCategories]
  )

  const handleSelect = (source: string, category: string, subCategory: string) => {
    const nextSelection: Selection = { source, category, subCategory }
    setSelection(nextSelection)
    setPreview(null)
    setPreviewError('')
    const requestId = requestRef.current + 1
    requestRef.current = requestId
    setPreviewLoading(true)

    void (async () => {
      try {
        const res = await apiFetch<TableExplorePreview>(
          `/data/explore/${encodeURIComponent(source)}?category=${encodeURIComponent(
            category
          )}&sub_category=${encodeURIComponent(subCategory)}&limit=50`
        )
        if (requestRef.current !== requestId) return
        setPreview(res ?? null)
      } catch (err) {
        if (requestRef.current !== requestId) return
        setPreviewError(
          err instanceof Error
            ? err.message
            : "Impossible de charger les données pour cette sélection."
        )
      } finally {
        if (requestRef.current === requestId) {
          setPreviewLoading(false)
        }
      }
    })()
  }

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
                Les aperçus sont limités à 50 lignes pour rester réactifs.
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
          <div key={node.name} className="border border-primary-100 rounded-lg bg-primary-50/60">
            <div className="flex items-start justify-between px-3 py-2 border-b border-primary-100">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-primary-900 truncate">{node.name}</p>
                <p className="text-[11px] text-primary-500">
                  {node.total.toLocaleString('fr-FR')} lignes
                </p>
              </div>
              <span className="text-[11px] text-primary-600">
                {node.subCategories.length.toLocaleString('fr-FR')} sous-catégories
              </span>
            </div>
            <div className="flex flex-col divide-y divide-primary-100">
              {node.subCategories.map(sub => (
                <button
                  key={sub.name}
                  type="button"
                  className="flex items-center justify-between px-3 py-2 text-left hover:bg-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400"
                  onClick={() => onSelect(source.source, node.name, sub.name)}
                >
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-primary-900 truncate">{sub.name}</p>
                    <p className="text-[11px] text-primary-500">Sub Category</p>
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
}: {
  selection: Selection | null
  preview: TableExplorePreview | null
  loading: boolean
  error: string
}) {
  if (!selection) return null

  const columns = preview?.preview_columns ?? []
  const rows = preview?.preview_rows ?? []

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
            {preview.matching_rows.toLocaleString('fr-FR')} lignes correspondantes (aperçu des{' '}
            {rows.length.toLocaleString('fr-FR')})
          </div>
        ) : null}
      </div>

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
