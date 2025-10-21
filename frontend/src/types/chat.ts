export interface Message {
  id?: string
  role: 'user' | 'assistant'
  content: string
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
}

export interface ChatCompletionRequest {
  messages: Message[]
}

export interface ChatCompletionResponse {
  reply: string
}

export interface ChartGenerationResponse {
  prompt: string
  chart_url: string
  tool_name: string
  chart_title?: string
  chart_description?: string
  chart_spec?: Record<string, unknown>
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
