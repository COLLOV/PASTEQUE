export interface Message {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatCompletionRequest {
  messages: Message[]
}

export interface ChatCompletionResponse {
  reply: string
}
