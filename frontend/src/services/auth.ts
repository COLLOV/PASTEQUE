import type { AuthState, LoginResponse } from '@/types/auth'

const AUTH_KEY = 'authState'

export function storeAuth(auth: AuthState): void {
  window.localStorage.setItem(AUTH_KEY, JSON.stringify(auth))
}

export function clearAuth(): void {
  window.localStorage.removeItem(AUTH_KEY)
}

export function getToken(): string | null {
  const auth = getAuth()
  return auth ? auth.token : null
}

export function getAuth(): AuthState | null {
  const raw = window.localStorage.getItem(AUTH_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as AuthState
  } catch (err) {
    console.error('Invalid auth state, clearing.', err)
    clearAuth()
    return null
  }
}

export async function login(username: string, password: string): Promise<AuthState> {
  const res = await fetch(`${import.meta.env.VITE_API_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || 'Échec de la connexion')
  }
  const data = (await res.json()) as LoginResponse
  if (!data?.access_token) {
    throw new Error('Réponse API invalide')
  }
  const auth: AuthState = {
    token: data.access_token,
    tokenType: data.token_type || 'bearer',
    username: data.username,
    isAdmin: Boolean(data.is_admin),
  }
  storeAuth(auth)
  return auth
}
