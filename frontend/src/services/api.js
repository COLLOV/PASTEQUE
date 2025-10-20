import { getToken } from './auth'

export function getApiBaseUrl() {
  const url = import.meta.env.VITE_API_URL
  if (!url) {
    throw new Error("VITE_API_URL manquant. Définissez-le dans .env.development.")
  }
  return url
}

export async function apiFetch(path, options = {}) {
  const base = getApiBaseUrl()
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  const token = getToken()
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  const res = await fetch(`${base}${path}`, {
    headers,
    ...options,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API ${res.status}: ${body}`)
  }
  return res.json()
}
