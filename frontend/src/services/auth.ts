import type { AuthState, LoginResponse } from '@/types/auth'

const AUTH_KEY = 'authState'

function getApiBaseUrl(): string {
  const url = import.meta.env.VITE_API_URL
  if (!url) {
    throw new Error('VITE_API_URL manquant. Définissez-le dans .env.development.')
  }
  return url
}

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
    const parsed = JSON.parse(raw) as Partial<AuthState>
    if (!parsed?.token || !parsed?.username) {
      throw new Error('Invalid auth payload')
    }
    const normalized: AuthState = {
      token: parsed.token,
      tokenType: parsed.tokenType || 'bearer',
      username: parsed.username,
      isAdmin: Boolean(parsed.isAdmin),
      showDashboardCharts:
        typeof parsed.showDashboardCharts === 'boolean' ? parsed.showDashboardCharts : true,
    }
    if (typeof parsed.showDashboardCharts !== 'boolean') {
      storeAuth(normalized)
    }
    return normalized
  } catch (err) {
    console.error('Invalid auth state, clearing.', err)
    clearAuth()
    return null
  }
}

export function updateAuthState(patch: Partial<AuthState>): AuthState | null {
  const current = getAuth()
  if (!current) {
    return null
  }
  const next: AuthState = { ...current, ...patch }
  storeAuth(next)
  return next
}

export async function login(username: string, password: string): Promise<AuthState> {
  const res = await fetch(`${getApiBaseUrl()}/auth/login`, {
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
    showDashboardCharts: data.show_dashboard_charts ?? true,
  }
  storeAuth(auth)
  return auth
}

export async function updateDashboardPreference(
  showDashboardCharts: boolean
): Promise<AuthState | null> {
  const auth = getAuth()
  if (!auth) {
    throw new Error('Utilisateur non authentifié')
  }

  const res = await fetch(`${getApiBaseUrl()}/auth/users/preferences`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `${auth.tokenType || 'bearer'} ${auth.token}`,
    },
    body: JSON.stringify({ show_dashboard_charts: showDashboardCharts }),
  })

  if (!res.ok) {
    const message = await res.text()
    throw new Error(message || 'Impossible de mettre à jour la préférence')
  }

  const data = (await res.json()) as { show_dashboard_charts: boolean }
  return updateAuthState({ showDashboardCharts: data.show_dashboard_charts })
}
