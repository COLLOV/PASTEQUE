export interface Message {
  role: 'user' | 'assistant'
  content: string
  chartUrl?: string
  chartTitle?: string
  chartDescription?: string
  chartTool?: string
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
