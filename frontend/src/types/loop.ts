export interface LoopConfig {
  id: number
  table_name: string
  text_column: string
  date_column: string
  updated_at: string
  last_generated_at?: string | null
}

export type LoopKind = 'weekly' | 'monthly'

export interface LoopSummary {
  id: number
  kind: LoopKind
  period_label: string
  period_start: string
  period_end: string
  ticket_count: number
  content: string
  created_at: string
}

export interface LoopOverview {
  config: LoopConfig | null
  weekly: LoopSummary[]
  monthly: LoopSummary[]
  last_generated_at?: string | null
}

export interface LoopConfigPayload {
  table_name: string
  text_column: string
  date_column: string
}
