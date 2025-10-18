export function getApiBaseUrl() {
  const url = import.meta.env.VITE_API_URL
  if (!url) {
    throw new Error("VITE_API_URL manquant. Définissez-le dans .env.development.")
  }
  return url
}

export async function apiFetch(path, options = {}) {
  const base = getApiBaseUrl()
  const res = await fetch(`${base}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API ${res.status}: ${body}`)
  }
  return res.json()
}

