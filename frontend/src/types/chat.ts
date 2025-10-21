export interface Message {
  role: 'user' | 'assistant'
  content: string
  chartUrl?: string
  chartTitle?: string
  chartDescription?: string
  chartTool?: string
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
}

export interface ChatCompletionResponse {
  reply: string
}

// Streaming event shapes
export interface ChatStreamMeta {
  request_id: string
  provider?: string
  model?: string
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

export interface ChartGenerationResponse {
  prompt: string
  chart_url: string
  tool_name: string
  chart_title?: string
  chart_description?: string
  chart_spec?: Record<string, unknown>
}
