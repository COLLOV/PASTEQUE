import { useState, useEffect, useCallback, FormEvent } from 'react'
import { apiFetch } from '@/services/api'
import { getAuth } from '@/services/auth'
import { Button, Input, Card, Loader } from '@/components/ui'
import type {
  CreateUserRequest,
  CreateUserResponse,
  UpdateUserPermissionsRequest,
  UserPermissionsOverviewResponse,
  UserWithPermissionsResponse
} from '@/types/user'
import { HiCheckCircle, HiXCircle } from 'react-icons/hi2'

interface Status {
  type: 'success' | 'error'
  message: string
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

export default function AdminPanel() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [status, setStatus] = useState<Status | null>(null)
  const [loadingUser, setLoadingUser] = useState(false)
  const [overview, setOverview] = useState<UserPermissionsOverviewResponse | null>(null)
  const [permissionsLoading, setPermissionsLoading] = useState(true)
  const [permissionsError, setPermissionsError] = useState('')
  const [updatingUsers, setUpdatingUsers] = useState<Set<string>>(() => new Set())
  const auth = getAuth()
  const adminUsername = auth?.username ?? ''

  const loadPermissions = useCallback(async () => {
    setPermissionsLoading(true)
    setPermissionsError('')
    try {
      const response = await apiFetch<UserPermissionsOverviewResponse>('/auth/users')
      setOverview(response ?? { tables: [], users: [] })
    } catch (err) {
      setPermissionsError(
        err instanceof Error ? err.message : 'Chargement des droits impossible.'
      )
    } finally {
      setPermissionsLoading(false)
    }
  }, [])

  useEffect(() => {
    loadPermissions()
  }, [loadPermissions])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const nextUsername = username.trim()
    if (!nextUsername || !password) {
      setStatus({ type: 'error', message: 'Utilisateur et mot de passe sont requis.' })
      return
    }
    setLoadingUser(true)
    setStatus(null)
    try {
      const response = await apiFetch<CreateUserResponse>('/auth/users', {
        method: 'POST',
        body: JSON.stringify({ username: nextUsername, password } as CreateUserRequest)
      })
      setStatus({
        type: 'success',
        message: `Utilisateur ${response.username} créé avec succès.`,
      })
      setUsername('')
      setPassword('')
      await loadPermissions()
    } catch (err) {
      setStatus({
        type: 'error',
        message: err instanceof Error ? err.message : 'Création impossible.'
      })
    } finally {
      setLoadingUser(false)
    }
  }

  async function handleTogglePermission(username: string, table: string, nextChecked: boolean) {
    if (!overview || updatingUsers.has(username)) return
    const target = overview.users.find(user => user.username === username)
    if (!target || target.is_admin) return

    const tableKey = table.toLowerCase()
    const filtered = target.allowed_tables.filter(value => value.toLowerCase() !== tableKey)
    const nextAllowed = nextChecked ? [...filtered, table] : filtered
    nextAllowed.sort((a, b) => a.localeCompare(b, 'fr', { sensitivity: 'base' }))
    const payload: UpdateUserPermissionsRequest = { allowed_tables: nextAllowed }

    setUpdatingUsers(prev => {
      const next = new Set(prev)
      next.add(username)
      return next
    })

    setOverview(prev => {
      if (!prev) return prev
      return {
        ...prev,
        users: prev.users.map(user =>
          user.username === username
            ? { ...user, allowed_tables: nextAllowed }
            : user
        ),
      }
    })

    try {
      const response = await apiFetch<UserWithPermissionsResponse>(
        `/auth/users/${encodeURIComponent(username)}/table-permissions`,
        {
          method: 'PUT',
          body: JSON.stringify(payload)
        }
      )
      setOverview(prev => {
        if (!prev) return prev
        return {
          ...prev,
          users: prev.users.map(user =>
            user.username === username
              ? { ...user, allowed_tables: response.allowed_tables }
              : user
          ),
        }
      })
      setStatus({ type: 'success', message: `Droits mis à jour pour ${username}.` })
    } catch (err) {
      await loadPermissions()
      setStatus({
        type: 'error',
        message: err instanceof Error ? err.message : 'Mise à jour impossible.'
      })
    } finally {
      setUpdatingUsers(prev => {
        const next = new Set(prev)
        next.delete(username)
        return next
      })
    }
  }

  const tables = overview?.tables ?? []
  const users = overview?.users ?? []

  return (
    <div className="max-w-5xl mx-auto animate-fade-in space-y-6">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-primary-950 mb-2">Espace admin</h2>
        <p className="text-primary-600">
          Connecté en tant que <strong className="text-primary-950">{adminUsername}</strong>.
          Gérez ici les comptes et leurs accès aux tables de données.
        </p>
      </div>

      {status && (
        <div
          className={`flex items-start gap-3 p-4 rounded-lg border-2 animate-fade-in ${
            status.type === 'success'
              ? 'bg-green-50 border-green-200'
              : 'bg-red-50 border-red-200'
          }`}
        >
          {status.type === 'success' ? (
            <HiCheckCircle className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
          ) : (
            <HiXCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          )}
          <p
            className={`text-sm ${
              status.type === 'success' ? 'text-green-800' : 'text-red-800'
            }`}
          >
            {status.message}
          </p>
        </div>
      )}

      <Card variant="elevated">
        <h3 className="text-lg font-semibold text-primary-950 mb-4">
          Créer un nouvel utilisateur
        </h3>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Nouvel utilisateur"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            minLength={1}
            maxLength={64}
            autoComplete="off"
            fullWidth
            placeholder="Nom d'utilisateur"
          />

          <Input
            label="Mot de passe"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={1}
            maxLength={128}
            autoComplete="new-password"
            fullWidth
            placeholder="Mot de passe"
          />
          <Button
            type="submit"
            disabled={loadingUser}
            fullWidth
            size="lg"
          >
            {loadingUser ? 'Création en cours…' : 'Créer l\'utilisateur'}
          </Button>
        </form>
      </Card>

      <Card variant="elevated">
        <div className="flex flex-col gap-2 mb-4">
          <h3 className="text-lg font-semibold text-primary-950">
            Droits d’accès aux tables
          </h3>
          <p className="text-sm text-primary-600">
            Activez ou désactivez l’accès aux tables pour chaque utilisateur. L’administrateur dispose toujours d’un accès complet.
          </p>
        </div>

        {permissionsLoading ? (
          <div className="py-12 flex justify-center">
            <Loader text="Chargement des droits…" />
          </div>
        ) : permissionsError ? (
          <div className="py-6 text-sm text-red-600">
            {permissionsError}
          </div>
        ) : tables.length === 0 ? (
          <div className="py-6 text-sm text-primary-600">
            Aucune table de données détectée dans le système.
          </div>
        ) : users.length === 0 ? (
          <div className="py-6 text-sm text-primary-600">
            Aucun utilisateur enregistré pour le moment.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full border border-primary-100 rounded-lg overflow-hidden">
              <thead className="bg-primary-50">
                <tr>
                  <th className="text-left text-xs font-semibold uppercase tracking-wide text-primary-600 px-4 py-3 border-b border-primary-100">
                    Utilisateur
                  </th>
                  {tables.map(table => (
                    <th
                      key={table}
                      className="text-center text-xs font-semibold uppercase tracking-wide text-primary-600 px-4 py-3 border-b border-primary-100"
                    >
                      {table}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map(user => {
                  const isAdminRow = Boolean(user.is_admin)
                  const isUpdating = updatingUsers.has(user.username)
                  const allowedSet = new Set(
                    user.allowed_tables.map(name => name.toLowerCase())
                  )
                  return (
                    <tr
                      key={user.username}
                      className="odd:bg-white even:bg-primary-25"
                    >
                      <td className="align-top px-4 py-3 border-b border-primary-100">
                        <div className="flex flex-col gap-1">
                          <span className="text-sm font-medium text-primary-900">
                            {user.username}
                          </span>
                          <span className="text-xs text-primary-500">
                            Créé le {formatDate(user.created_at)}
                          </span>
                          {isAdminRow && (
                            <span className="text-xs font-semibold text-primary-600">
                              Accès administrateur
                            </span>
                          )}
                        </div>
                      </td>
                      {tables.map(table => {
                        const checked = isAdminRow || allowedSet.has(table.toLowerCase())
                        return (
                          <td
                            key={`${user.username}-${table}`}
                            className="text-center px-4 py-3 border-b border-primary-100"
                          >
                            <input
                              type="checkbox"
                              className="h-4 w-4"
                              checked={checked}
                              disabled={isAdminRow || isUpdating}
                              onChange={(event) =>
                                handleTogglePermission(user.username, table, event.target.checked)
                              }
                            />
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
