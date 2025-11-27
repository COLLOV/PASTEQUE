import { useMemo, useRef, type MouseEvent } from 'react'
import { Bar, getElementAtEvent } from 'react-chartjs-2'
import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  Tooltip,
  type ChartData,
  type ChartOptions,
} from 'chart.js'
import { Card } from '@/components/ui'
import type { CategorySubCategoryCount } from '@/types/data'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend)

const PALETTE = ['#2563eb', '#0ea5e9', '#14b8a6', '#10b981', '#f59e0b', '#ef4444', '#a855f7', '#f97316']

function pickColor(index: number): string {
  const size = PALETTE.length
  if (size === 0) return '#2563eb'
  return PALETTE[index % size]
}

type Props = {
  breakdown: CategorySubCategoryCount[]
  onSelect?: (category: string, subCategory: string) => void
  title?: string
  subtitle?: string
  height?: number
  className?: string
}

export default function CategoryStackedChart({
  breakdown,
  onSelect,
  title = 'Répartition Category / Sub Category',
  subtitle = 'Cliquez sur un segment pour explorer les lignes correspondantes.',
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

  const categories = useMemo(
    () => Array.from(new Set(sanitized.map(item => item.category as string))),
    [sanitized]
  )
  const subCategories = useMemo(
    () => Array.from(new Set(sanitized.map(item => item.sub_category as string))),
    [sanitized]
  )
  const chartRef = useRef<ChartJS<'bar'> | null>(null)

  if (!categories.length || !subCategories.length) {
    return null
  }

  const chartData = useMemo<ChartData<'bar'>>(
    () => ({
      labels: categories,
      datasets: subCategories.map((sub, datasetIndex) => ({
        label: sub,
        data: categories.map(cat => {
          const match = sanitized.find(
            item => item.category === cat && item.sub_category === sub
          )
          return match ? match.count : 0
        }),
        backgroundColor: pickColor(datasetIndex),
        borderColor: pickColor(datasetIndex),
        borderWidth: 1,
        stack: 'category',
      })),
    }),
    [categories, subCategories, sanitized]
  )

  const options = useMemo<ChartOptions<'bar'>>(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          position: 'bottom',
          labels: { color: '#52525b' },
        },
        tooltip: {
          callbacks: {
            label: context => {
              const value = typeof context.raw === 'number' ? context.raw : Number(context.raw ?? 0)
              return `${context.dataset.label ?? ''}: ${value.toLocaleString('fr-FR')} enregistrements`
            },
          },
        },
      },
      scales: {
        x: {
          stacked: true,
          grid: { display: false },
          ticks: { color: '#52525b', maxRotation: 45, minRotation: 45 },
        },
        y: {
          stacked: true,
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

  const handleClick = (event: MouseEvent<HTMLCanvasElement>) => {
    if (!onSelect) return
    const chart = chartRef.current
    if (!chart) return
    const elements = getElementAtEvent(chart, event)
    if (!elements.length) return
    const { index, datasetIndex } = elements[0]
    const category = categories[index ?? 0]
    const subCategory = subCategories[datasetIndex ?? 0]
    if (category && subCategory) {
      onSelect(category, subCategory)
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
        <Bar ref={chartRef} data={chartData} options={options} onClick={handleClick} />
      </div>
    </Card>
  )
}
