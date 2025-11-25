export interface DimensionCount {
  label: string
  count: number
}

export interface DimensionBreakdown {
  field: string
  label: string
  counts: DimensionCount[]
}

export interface DataSourceOverview {
  source: string
  title: string
  total_rows: number
  columns: DimensionBreakdown[]
}

export interface DataOverviewResponse {
  generated_at: string
  sources: DataSourceOverview[]
}
