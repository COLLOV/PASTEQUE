import { useState, FormEvent } from 'react'
import { apiFetch } from '@/services/api'
import { Button, Input, Card } from '@/components/ui'
import type { CreateUserRequest, CreateUserResponse } from '@/types/user'
import { HiCheckCircle, HiXCircle } from 'react-icons/hi2'

interface AdminPanelProps {
  adminUsername: string
}

interface Status {
  type: 'success' | 'error'
  message: string
}

export default function AdminPanel({ adminUsername }: AdminPanelProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [status, setStatus] = useState<Status | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const nextUsername = username.trim()
    if (!nextUsername || !password) {
      setStatus({ type: 'error', message: 'Utilisateur et mot de passe sont requis.' })
      return
    }
    setLoading(true)
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
    } catch (err) {
      setStatus({
        type: 'error',
        message: err instanceof Error ? err.message : 'Création impossible.'
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto animate-fade-in">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-primary-950 mb-2">Espace admin</h2>
        <p className="text-primary-600">
          Connecté en tant que <strong className="text-primary-950">{adminUsername}</strong>. Créez de nouveaux accès ici.
        </p>
      </div>

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

          <Button
            type="submit"
            disabled={loading}
            fullWidth
            size="lg"
          >
            {loading ? 'Création en cours…' : 'Créer l\'utilisateur'}
          </Button>
        </form>
      </Card>
    </div>
  )
}
