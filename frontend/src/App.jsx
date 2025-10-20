import React, { useState } from 'react'
import Chat from './features/chat/Chat'
import Dashboard from './features/dashboard/Dashboard'
import Login from './features/auth/Login'
import { getToken, clearToken } from './services/auth'

export default function App() {
  const [token, setToken] = useState(() => getToken())

  function handleLogin(newToken) {
    setToken(newToken)
  }

  function handleLogout() {
    clearToken()
    setToken(null)
  }

  if (!token) {
    return (
      <div style={{ padding: 16 }}>
        <h1>20_insightv2</h1>
        <p>Veuillez vous connecter pour accéder à la plateforme.</p>
        <Login onSuccess={handleLogin} />
      </div>
    )
  }

  return (
    <div style={{ padding: 16 }}>
      <h1>20_insightv2</h1>
      <p>Plateforme pour discuter avec les données</p>
      <button onClick={handleLogout} style={{ marginBottom: 16 }}>
        Se déconnecter
      </button>
      <hr />
      <Chat />
      <hr />
      <Dashboard />
    </div>
  )
}
