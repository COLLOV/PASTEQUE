import { Outlet } from 'react-router-dom'
import { Button } from '@/components/ui'
import { clearAuth, getAuth } from '@/services/auth'
import { useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import Navigation from './Navigation'
import { useCallback } from 'react'

export default function Layout() {
  const navigate = useNavigate()
  const [auth, setAuth] = useState(() => getAuth())

  useEffect(() => {
    const currentAuth = getAuth()
    setAuth(currentAuth)
  }, [])

  const handleLogout = () => {
    clearAuth()
    setAuth(null)
    navigate('/login')
  }

  const goTo = useCallback(
    (path: string) => () => {
      navigate(path)
    },
    [navigate]
  )

  if (!auth) {
    navigate('/login')
    return null
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-50 to-white">
      <header className="border-b-2 border-primary-100 bg-white/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <h1 className="text-2xl font-bold text-primary-950 tracking-tight">
                FoyerInsight
              </h1>
              <div className="h-6 w-px bg-primary-200" />
              <p className="text-sm text-primary-600">
                Connecté en tant que <strong className="text-primary-950">{auth.username}</strong>
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="secondary" size="sm" onClick={goTo('/dashboard')}>
                Dashboard
              </Button>
              {auth.isAdmin && (
                <Button variant="secondary" size="sm" onClick={goTo('/admin')}>
                  Admin
                </Button>
              )}
              <Button variant="ghost" onClick={handleLogout} size="sm">
                Se déconnecter
              </Button>
            </div>
          </div>
        </div>
      </header>

      <Navigation />

      <main className="container mx-auto px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
