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
  date?: DimensionBreakdown | null
  department?: DimensionBreakdown | null
  campaign?: DimensionBreakdown | null
  domain?: DimensionBreakdown | null
}

export interface DataOverviewResponse {
  generated_at: string
  sources: DataSourceOverview[]
}
