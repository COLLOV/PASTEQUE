export interface DimensionCount {
  label: string
  count: number
}

export interface DimensionBreakdown {
  field: string
  label: string
  kind: 'date' | 'number' | 'boolean' | 'category'
  counts: DimensionCount[]
}

export interface DataSourceOverview {
  source: string
  title: string
  total_rows: number
  dimensions: DimensionBreakdown[]
}

export interface DataOverviewResponse {
  generated_at: string
  sources: DataSourceOverview[]
}

export interface ExplorerColumnConfig {
  name: string
  label: string
  type?: string | null
  hidden: boolean
}

export interface ExplorerTableConfig {
  table: string
  title: string
  columns: ExplorerColumnConfig[]
}

export interface ExplorerColumnsConfigResponse {
  tables: ExplorerTableConfig[]
}

export interface UpdateExplorerColumnsRequest {
  hidden_columns: string[]
}
