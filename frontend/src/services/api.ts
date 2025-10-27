import { clearAuth, getAuth } from './auth'

export function getApiBaseUrl(): string {
  const url = import.meta.env.VITE_API_URL
  if (!url) {
    throw new Error("VITE_API_URL manquant. Définissez-le dans .env.development.")
  }
  return url
}

export function resolveApiUrl(path: string): string {
  if (!path) return path
  if (/^https?:\/\//i.test(path)) {
    return path
  }
  try {
    return new URL(path, getApiBaseUrl()).toString()
  } catch {
    return path
  }
}

interface ApiFetchOptions extends RequestInit {
  headers?: Record<string, string>
}

export async function apiFetch<T = any>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const base = getApiBaseUrl()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  }

  const auth = getAuth()
  const token = auth ? auth.token : null

  if (token) {
    const scheme = auth?.tokenType || 'bearer'
    headers.Authorization = `${scheme} ${token}`
  }

  const res = await fetch(`${base}${path}`, {
    headers,
    ...options,
  })

  if (res.status === 401) {
    clearAuth()
    if (!window.location.pathname.startsWith('/login')) {
      window.location.href = '/login'
    }
    throw new Error('Session expirée, veuillez vous reconnecter')
  }

  const raw = await res.text()
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${raw}`)
  }

  const text = raw.trim()
  if (!text) {
    return undefined as T
  }

  try {
    return JSON.parse(text) as T
  } catch {
    throw new Error(`API ${res.status}: Réponse JSON invalide`)
  }
}

export interface StreamSSEOptions {
  headers?: Record<string, string>
  signal?: AbortSignal
}

export async function streamSSE(
  path: string,
  body: unknown,
  onEvent: (type: string, data: any) => void,
  options: StreamSSEOptions = {}
): Promise<void> {
  const base = getApiBaseUrl()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
    ...(options.headers || {}),
  }

  const auth = getAuth()
  const token = auth ? auth.token : null
  if (token) {
    const scheme = auth?.tokenType || 'bearer'
    headers.Authorization = `${scheme} ${token}`
  }

  const res = await fetch(`${base}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal: options.signal,
  })

  if (res.status === 401) {
    clearAuth()
    if (!window.location.pathname.startsWith('/login')) {
      window.location.href = '/login'
    }
    throw new Error('Session expirée, veuillez vous reconnecter')
  }

  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => '')
    throw new Error(`STREAM ${res.status}: ${text}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    // SSE events are separated by double newlines
    let idx
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      // Parse event block
      const lines = raw.split(/\r?\n/)
      let evt = 'message'
      let data = ''
      for (const line of lines) {
        if (line.startsWith('event: ')) evt = line.slice(7).trim()
        else if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (!data) continue
      try {
        const obj = JSON.parse(data)
        onEvent(evt, obj)
      } catch {
        // ignore malformed chunk
      }
    }
  }
}
