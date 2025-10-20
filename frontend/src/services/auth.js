const TOKEN_KEY = 'authToken'

export function storeToken(token) {
  window.localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  window.localStorage.removeItem(TOKEN_KEY)
}

export function getToken() {
  return window.localStorage.getItem(TOKEN_KEY)
}

export async function login(username, password) {
  const res = await fetch(`${import.meta.env.VITE_API_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || 'Échec de la connexion')
  }
  const data = await res.json()
  if (!data?.access_token) {
    throw new Error('Réponse API invalide')
  }
  storeToken(data.access_token)
  return data.access_token
}
