import React from 'react'
import Chat from './features/chat/Chat'
import Dashboard from './features/dashboard/Dashboard'

export default function App() {
  return (
    <div style={{ padding: 16 }}>
      <h1>20_insightv2</h1>
      <p>Plateforme pour discuter avec les données</p>
      <hr />
      <Chat />
      <hr />
      <Dashboard />
    </div>
  )
}

