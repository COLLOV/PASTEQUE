import React, { useState } from 'react'
import Chat from './features/chat/Chat'
import Dashboard from './features/dashboard/Dashboard'
import Login from './features/auth/Login'
import AdminPanel from './features/admin/AdminPanel'
import { getAuth, clearAuth } from './services/auth'

const VIEW_CHAT = 'chat'
const VIEW_DASHBOARD = 'dashboard'
const VIEW_ADMIN = 'admin'

export default function App() {
  const [auth, setAuth] = useState(() => getAuth())
  const [activeView, setActiveView] = useState(VIEW_CHAT)

  function handleLogin(newAuth) {
    setAuth(newAuth)
    setActiveView(VIEW_CHAT)
  }

  function handleLogout() {
    clearAuth()
    setAuth(null)
  }

  if (!auth) {
    return (
      <div style={{ padding: 16 }}>
        <h1>20_insightv2</h1>
        <p>Veuillez vous connecter pour accéder à la plateforme.</p>
        <Login onSuccess={handleLogin} />
      </div>
    )
  }

  const views = auth.isAdmin ? [VIEW_CHAT, VIEW_DASHBOARD, VIEW_ADMIN] : [VIEW_CHAT, VIEW_DASHBOARD]

  return (
    <div style={{ padding: 16 }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <h1 style={{ marginBottom: 4 }}>20_insightv2</h1>
          <p style={{ margin: 0 }}>Connecté en tant que <strong>{auth.username}</strong></p>
        </div>
        <button onClick={handleLogout}>
          Se déconnecter
        </button>
      </header>

      <nav style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {views.map((view) => (
          <button
            key={view}
            onClick={() => setActiveView(view)}
            style={{
              padding: '8px 12px',
              borderRadius: 6,
              border: activeView === view ? '1px solid #111827' : '1px solid #d1d5db',
              background: activeView === view ? '#111827' : '#ffffff',
              color: activeView === view ? '#ffffff' : '#111827',
              cursor: 'pointer'
            }}
          >
            {labelFor(view)}
          </button>
        ))}
      </nav>

      {activeView === VIEW_CHAT && <Chat />}
      {activeView === VIEW_DASHBOARD && <Dashboard />}
      {activeView === VIEW_ADMIN && auth.isAdmin && <AdminPanel adminUsername={auth.username} />}
    </div>
  )
}

function labelFor(view) {
  switch (view) {
    case VIEW_CHAT:
      return 'Chat'
    case VIEW_DASHBOARD:
      return 'Dashboard'
    case VIEW_ADMIN:
      return 'Admin'
    default:
      return view
  }
}
