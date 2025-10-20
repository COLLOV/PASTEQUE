import React, { useState } from 'react'
import { login } from '../../services/auth'

export default function Login({ onSuccess }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const token = await login(username.trim(), password)
      setUsername('')
      setPassword('')
      onSuccess(token)
    } catch (err) {
      setError(err.message || 'Échec de la connexion')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ maxWidth: 320, margin: '0 auto', display: 'grid', gap: 8 }}>
      <h2>Connexion</h2>
      <label>
        Utilisateur
        <input
          type="text"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          required
          autoComplete="username"
        />
      </label>
      <label>
        Mot de passe
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          autoComplete="current-password"
        />
      </label>
      {error ? <p style={{ color: 'crimson' }}>{error}</p> : null}
      <button type="submit" disabled={loading}>
        {loading ? 'Connexion…' : 'Se connecter'}
      </button>
    </form>
  )
}
