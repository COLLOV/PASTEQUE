import { useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { login } from '@/services/auth'
import { Button, Input, Card } from '@/components/ui'

export default function Login() {
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await login(username.trim(), password)
      setUsername('')
      setPassword('')
      navigate('/chat')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Échec de la connexion')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-50 to-white flex items-center justify-center p-4">
      <Card className="w-full max-w-md animate-slide-up" variant="elevated">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-primary-950 mb-2">
            FoyerInsight
          </h1>
          <p className="text-primary-600">
            Veuillez vous connecter pour accéder à la plateforme.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Utilisateur"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoComplete="username"
            fullWidth
            placeholder="Entrez votre nom d'utilisateur"
          />

          <Input
            label="Mot de passe"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
            fullWidth
            placeholder="Entrez votre mot de passe"
          />

          {error && (
            <div className="bg-red-50 border-2 border-red-200 rounded-lg p-3 animate-fade-in">
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}

          <Button
            type="submit"
            disabled={loading}
            fullWidth
            size="lg"
            className="mt-6"
          >
            {loading ? 'Connexion en cours…' : 'Se connecter'}
          </Button>
        </form>
      </Card>
    </div>
  )
}
