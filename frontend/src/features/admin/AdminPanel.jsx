import React, { useState } from 'react'
import { apiFetch } from '../../services/api'

export default function AdminPanel({ adminUsername }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    const nextUsername = username.trim()
    if (!nextUsername || !password) {
      setStatus({ type: 'error', message: 'Utilisateur et mot de passe sont requis.' })
      return
    }
    setLoading(true)
    setStatus(null)
    try {
      const response = await apiFetch('/auth/users', {
        method: 'POST',
        body: JSON.stringify({ username: nextUsername, password })
      })
      setStatus({
        type: 'success',
        message: `Utilisateur ${response.username} créé avec succès.`,
      })
      setUsername('')
      setPassword('')
    } catch (err) {
      setStatus({ type: 'error', message: err.message || 'Création impossible.' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <section>
      <h2>Espace admin</h2>
      <p>Connecté en tant que <strong>{adminUsername}</strong>. Créez de nouveaux accès ici.</p>
      <form onSubmit={handleSubmit} style={{ maxWidth: 360, display: 'grid', gap: 8 }}>
        <label>
          Nouvel utilisateur
          <input
            type="text"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            required
            minLength={1}
            maxLength={64}
            autoComplete="off"
          />
        </label>
        <label>
          Mot de passe
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            minLength={1}
            maxLength={128}
            autoComplete="new-password"
          />
        </label>
        {status ? (
          <div
            style={{
              padding: '8px 12px',
              borderRadius: 6,
              background: status.type === 'success' ? '#ecfdf5' : '#fef2f2',
              border: status.type === 'success' ? '1px solid #34d399' : '1px solid #fca5a5',
              color: status.type === 'success' ? '#047857' : '#b91c1c'
            }}
          >
            {status.message}
          </div>
        ) : null}
        <button type="submit" disabled={loading}>
          {loading ? 'Création…' : 'Créer'}
        </button>
      </form>
    </section>
  )
}
