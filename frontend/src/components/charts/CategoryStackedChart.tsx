import { useMemo, useRef, type MouseEvent } from 'react'
import { Doughnut, getElementAtEvent } from 'react-chartjs-2'
import { ArcElement, Chart as ChartJS, Legend, Tooltip, type ChartData, type ChartOptions } from 'chart.js'
import { Card } from '@/components/ui'
import type { CategorySubCategoryCount } from '@/types/data'

ChartJS.register(ArcElement, Tooltip, Legend)

const PALETTE = ['#2563eb', '#0ea5e9', '#14b8a6', '#10b981', '#f59e0b', '#ef4444', '#a855f7', '#f97316']

function pickColor(index: number): string {
  const size = PALETTE.length
  if (size === 0) return '#2563eb'
  return PALETTE[index % size]
}

type Props = {
  breakdown: CategorySubCategoryCount[]
  onSelect?: (category: string, subCategory?: string) => void
  title?: string
  subtitle?: string
  height?: number
  className?: string
}

export default function CategoryStackedChart({
  breakdown,
  onSelect,
  title = 'Répartition Category / Sub Category',
  subtitle = 'Cliquez sur une part pour ouvrir la sous-catégorie la plus fréquente.',
  height = 224,
  className,
}: Props) {
  const sanitized = useMemo(
    () =>
      breakdown
        .map(item => ({
          category: item.category?.trim(),
          sub_category: item.sub_category?.trim(),
          count: item.count,
        }))
        .filter(item => item.category && item.sub_category) as CategorySubCategoryCount[],
    [breakdown]
  )

  const categoryTotals = useMemo(() => {
    const totals = new Map<string, number>()
    const topSub = new Map<string, { sub: string; count: number }>()
    sanitized.forEach(item => {
      const category = item.category as string
      const sub = item.sub_category as string
      const count = item.count ?? 0
      totals.set(category, (totals.get(category) ?? 0) + count)
      const currentTop = topSub.get(category)
      if (!currentTop || count > currentTop.count) {
        topSub.set(category, { sub, count })
      }
    })
    return { totals, topSub }
  }, [sanitized])

  const categories = useMemo(() => {
    return Array.from(categoryTotals.totals.entries())
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([cat]) => cat)
  }, [categoryTotals.totals])

  const chartRef = useRef<ChartJS<'doughnut'> | null>(null)

  if (!categories.length) {
    return null
  }

  const chartData = useMemo<ChartData<'doughnut'>>(
    () => ({
      labels: categories,
      datasets: [
        {
          label: 'Occurrences',
          data: categories.map(cat => categoryTotals.totals.get(cat) ?? 0),
          backgroundColor: categories.map((_, index) => pickColor(index)),
          borderColor: '#ffffff',
          borderWidth: 1,
          hoverOffset: 8,
        },
      ],
    }),
    [categories, categoryTotals.totals]
  )

  const options = useMemo<ChartOptions<'doughnut'>>(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          position: 'right',
          labels: { color: '#52525b', boxWidth: 12 },
        },
        tooltip: {
          callbacks: {
            label: context => {
              const value = typeof context.raw === 'number' ? context.raw : Number(context.raw ?? 0)
              const total = context.dataset.data.reduce((acc, v) => acc + (typeof v === 'number' ? v : Number(v ?? 0)), 0)
              const pct = total ? ((value / total) * 100).toFixed(1) : '0'
              return `${context.label ?? ''}: ${value.toLocaleString('fr-FR')} (${pct}%)`
            },
          },
        },
      },
      cutout: '55%',
    }),
    []
  )

  const handleClick = (event: MouseEvent<HTMLCanvasElement>) => {
    if (!onSelect) return
    const chart = chartRef.current
    if (!chart) return
    const elements = getElementAtEvent(chart, event)
    if (!elements.length) return
    const { index } = elements[0]
    const category = categories[index ?? 0]
    const topSub = categoryTotals.topSub.get(category)?.sub
    if (category) {
      onSelect(category, topSub)
    }
  }

  const cardClass = ['bg-primary-50', className].filter(Boolean).join(' ')

  return (
    <Card padding="sm" className={cardClass || undefined}>
      {title || subtitle ? (
        <div className="flex items-center justify-between mb-2">
          <div>
            {title ? <p className="text-sm font-semibold text-primary-800">{title}</p> : null}
            {subtitle ? <p className="text-[11px] text-primary-500">{subtitle}</p> : null}
          </div>
        </div>
      ) : null}
      <div style={{ height }}>
        <Doughnut ref={chartRef} data={chartData} options={options} onClick={handleClick} />
      </div>
    </Card>
  )
}
