export type FieldKind = 'date' | 'text' | 'number' | 'boolean' | 'unknown'

export interface ValueCount {
  label: string
  count: number
}

export interface FieldBreakdown {
  field: string
  label: string
  kind: FieldKind
  non_null: number
  missing_values: number
  unique_values: number
  counts: ValueCount[]
  truncated: boolean
}

export interface DataSourceOverview {
  source: string
  title: string
  total_rows: number
  fields: FieldBreakdown[]
}

export interface DataOverviewResponse {
  generated_at: string
  sources: DataSourceOverview[]
}
