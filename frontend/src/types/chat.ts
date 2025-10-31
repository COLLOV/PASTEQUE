export interface Message {
  id?: string
  role: 'user' | 'assistant'
  content: string
  // Optional dataset captured during NL→SQL streaming for this answer
  // Enables one-click chart generation from the assistant message bubble
  chartDataset?: ChartDatasetPayload
  chartUrl?: string
  chartTitle?: string
  chartDescription?: string
  chartTool?: string
  chartPrompt?: string
  chartSpec?: Record<string, unknown>
  chartSaved?: boolean
  chartSaving?: boolean
  chartSaveError?: string
  chartRecordId?: number
  // Streaming placeholder (ephemeral) removed at end
  ephemeral?: boolean
  // When streaming NL→SQL, show SQL first then final answer
  interimSql?: string
  // Optional per-message details shown on toggle inside the bubble
  details?: {
    requestId?: string
    provider?: string
    model?: string
    elapsed?: number
    plan?: any
    steps?: Array<{ step?: number; purpose?: string; sql?: string }>
    samples?: Array<{ step?: number; columns?: string[]; row_count?: number }>
  }
}

export interface ChatCompletionRequest {
  messages: Message[]
  metadata?: {
    nl2sql?: boolean
    [key: string]: unknown
  }
}

export interface ChatCompletionResponse {
  reply: string
}

// Streaming event shapes
export interface ChatStreamMeta {
  request_id: string
  provider?: string
  model?: string
  // Optional evidence spec provided by the pipeline (MCP/LLM)
  evidence_spec?: EvidenceSpec
  // Conversation identifier (server-created on first message)
  conversation_id?: number
}

export interface ChatStreamDelta {
  seq: number
  content: string
}

export interface ChatStreamDone {
  id: string
  content_full: string
  usage?: any
  finish_reason?: string
  elapsed_s?: number
}

export interface ChartDatasetPayload {
  sql: string
  columns: string[]
  rows: Record<string, unknown>[]
  row_count?: number
  step?: number
  description?: string
}

export interface ChartGenerationRequest {
  prompt: string
  answer?: string
  dataset: ChartDatasetPayload
}

export interface ChartGenerationResponse {
  prompt: string
  chart_url: string
  tool_name: string
  chart_title?: string
  chart_description?: string
  chart_spec?: Record<string, unknown>
  source_sql?: string
  source_row_count?: number
}

export interface SavedChartResponse {
  id: number
  prompt: string
  chart_url: string
  tool_name?: string | null
  chart_title?: string | null
  chart_description?: string | null
  chart_spec?: Record<string, unknown> | null
  created_at: string
  owner_username: string
}

// Generic evidence contract (no hardcoding to "tickets")
export interface EvidenceSpec {
  entity_label: string
  entity_name?: string
  pk: string
  display?: {
    title?: string
    status?: string
    created_at?: string
    link_template?: string
  }
  columns?: string[]
  limit?: number
  // Optional period hint for UI summary
  period?: { from?: string; to?: string } | string
}

export interface EvidenceRowsPayload {
  columns: string[]
  rows: Record<string, unknown>[]
  row_count?: number
  step?: number
  purpose?: string // expected: 'evidence'
}
