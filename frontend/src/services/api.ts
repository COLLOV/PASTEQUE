import { getAuth } from './auth'

export function getApiBaseUrl(): string {
  const url = import.meta.env.VITE_API_URL
  if (!url) {
    throw new Error("VITE_API_URL manquant. Définissez-le dans .env.development.")
  }
  return url
}

interface ApiFetchOptions extends RequestInit {
  headers?: Record<string, string>
}

export async function apiFetch<T = any>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const base = getApiBaseUrl()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers || {})
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

  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API ${res.status}: ${body}`)
  }

  return res.json() as Promise<T>
}
