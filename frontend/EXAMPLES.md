# Exemples de Code

Ce document contient des exemples pratiques pour travailler avec le codebase modernisé.

## Table des Matières

1. [Composants UI](#composants-ui)
2. [Formulaires](#formulaires)
3. [API Calls](#api-calls)
4. [Navigation](#navigation)
5. [Gestion d'État](#gestion-détat)
6. [Patterns Courants](#patterns-courants)

## Composants UI

### Button avec Loading State

```tsx
import { useState } from 'react'
import { Button } from '@/components/ui'

function SubmitButton() {
  const [loading, setLoading] = useState(false)

  const handleClick = async () => {
    setLoading(true)
    try {
      await someApiCall()
    } finally {
      setLoading(false)
    }
  }

  return (
    <Button
      onClick={handleClick}
      disabled={loading}
      variant="primary"
    >
      {loading ? 'Chargement...' : 'Soumettre'}
    </Button>
  )
}
```

### Card avec Header et Footer

```tsx
import { Card, Button } from '@/components/ui'

function ProfileCard() {
  return (
    <Card variant="elevated" padding="none">
      <div className="p-4 border-b-2 border-primary-100">
        <h3 className="text-lg font-semibold text-primary-950">
          Profil Utilisateur
        </h3>
      </div>

      <div className="p-4">
        <p className="text-primary-600">
          Informations du profil...
        </p>
      </div>

      <div className="p-4 border-t-2 border-primary-100 bg-primary-50 flex justify-end gap-2">
        <Button variant="secondary" size="sm">Annuler</Button>
        <Button variant="primary" size="sm">Enregistrer</Button>
      </div>
    </Card>
  )
}
```

### Input avec Validation

```tsx
import { useState } from 'react'
import { Input, Button } from '@/components/ui'

function EmailForm() {
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    if (!email.includes('@')) {
      setError('Email invalide')
      return
    }

    setError('')
    // Submit logic
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <Input
        label="Email"
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        error={error}
        placeholder="vous@exemple.com"
        fullWidth
      />
      <Button type="submit" fullWidth>
        Envoyer
      </Button>
    </form>
  )
}
```

## Formulaires

### Formulaire Complet avec État Multiple

```tsx
import { useState, FormEvent } from 'react'
import { Input, Textarea, Button, Card } from '@/components/ui'

interface FormData {
  name: string
  email: string
  message: string
}

function ContactForm() {
  const [formData, setFormData] = useState<FormData>({
    name: '',
    email: '',
    message: ''
  })
  const [errors, setErrors] = useState<Partial<FormData>>({})
  const [loading, setLoading] = useState(false)

  const validate = (): boolean => {
    const newErrors: Partial<FormData> = {}

    if (!formData.name.trim()) {
      newErrors.name = 'Le nom est requis'
    }

    if (!formData.email.includes('@')) {
      newErrors.email = 'Email invalide'
    }

    if (formData.message.length < 10) {
      newErrors.message = 'Le message doit contenir au moins 10 caractères'
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()

    if (!validate()) return

    setLoading(true)
    try {
      // API call
      console.log('Envoi:', formData)
    } finally {
      setLoading(false)
    }
  }

  const handleChange = (field: keyof FormData) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    setFormData(prev => ({ ...prev, [field]: e.target.value }))
    // Effacer l'erreur lors de la saisie
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: undefined }))
    }
  }

  return (
    <Card variant="elevated">
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Nom"
          value={formData.name}
          onChange={handleChange('name')}
          error={errors.name}
          fullWidth
        />

        <Input
          label="Email"
          type="email"
          value={formData.email}
          onChange={handleChange('email')}
          error={errors.email}
          fullWidth
        />

        <Textarea
          label="Message"
          value={formData.message}
          onChange={handleChange('message')}
          error={errors.message}
          rows={5}
          fullWidth
        />

        <div className="flex gap-2">
          <Button
            type="button"
            variant="secondary"
            onClick={() => setFormData({ name: '', email: '', message: '' })}
          >
            Réinitialiser
          </Button>
          <Button type="submit" disabled={loading}>
            {loading ? 'Envoi...' : 'Envoyer'}
          </Button>
        </div>
      </form>
    </Card>
  )
}
```

## API Calls

### Hook Personnalisé pour Fetch

```tsx
import { useState, useEffect } from 'react'
import { apiFetch } from '@/services/api'

interface UseFetchResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  refetch: () => void
}

function useFetch<T>(url: string): UseFetchResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await apiFetch<T>(url)
      setData(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur inconnue')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [url])

  return { data, loading, error, refetch: fetchData }
}

// Utilisation
function UserProfile() {
  const { data, loading, error, refetch } = useFetch<User>('/api/user/profile')

  if (loading) return <Loader text="Chargement..." />
  if (error) return <div className="text-red-600">{error}</div>
  if (!data) return null

  return (
    <Card>
      <h2>{data.name}</h2>
      <Button onClick={refetch}>Rafraîchir</Button>
    </Card>
  )
}
```

### Mutation avec Optimistic Update

```tsx
import { useState } from 'react'
import { apiFetch } from '@/services/api'

interface Todo {
  id: number
  text: string
  completed: boolean
}

function TodoList() {
  const [todos, setTodos] = useState<Todo[]>([])

  const toggleTodo = async (id: number) => {
    // Optimistic update
    setTodos(prev =>
      prev.map(todo =>
        todo.id === id ? { ...todo, completed: !todo.completed } : todo
      )
    )

    try {
      await apiFetch(`/api/todos/${id}/toggle`, { method: 'PATCH' })
    } catch (error) {
      // Rollback en cas d'erreur
      setTodos(prev =>
        prev.map(todo =>
          todo.id === id ? { ...todo, completed: !todo.completed } : todo
        )
      )
      console.error('Erreur:', error)
    }
  }

  return (
    <div className="space-y-2">
      {todos.map(todo => (
        <Card
          key={todo.id}
          className={todo.completed ? 'opacity-50' : ''}
        >
          <button onClick={() => toggleTodo(todo.id)}>
            {todo.text}
          </button>
        </Card>
      ))}
    </div>
  )
}
```

## Navigation

### Navigation avec État

```tsx
import { useNavigate, useLocation } from 'react-router-dom'
import { Button } from '@/components/ui'

function NavigationExample() {
  const navigate = useNavigate()
  const location = useLocation()

  const goToChat = () => {
    navigate('/chat', {
      state: { from: location.pathname }
    })
  }

  return (
    <div className="space-y-2">
      <Button onClick={goToChat}>Aller au Chat</Button>
      <Button onClick={() => navigate(-1)}>Retour</Button>
    </div>
  )
}
```

### Route Protégée Conditionnelle

```tsx
import { Navigate, useLocation } from 'react-router-dom'
import { getAuth } from '@/services/auth'

interface ConditionalRouteProps {
  children: React.ReactNode
  condition: boolean
  redirectTo?: string
}

function ConditionalRoute({
  children,
  condition,
  redirectTo = '/login'
}: ConditionalRouteProps) {
  const location = useLocation()

  if (!condition) {
    return <Navigate to={redirectTo} state={{ from: location }} replace />
  }

  return <>{children}</>
}

// Utilisation
function AdminRoute({ children }: { children: React.ReactNode }) {
  const auth = getAuth()
  return (
    <ConditionalRoute condition={auth?.isAdmin || false}>
      {children}
    </ConditionalRoute>
  )
}
```

## Gestion d'État

### Hook pour Local Storage

```tsx
import { useState, useEffect } from 'react'

function useLocalStorage<T>(key: string, initialValue: T) {
  const [value, setValue] = useState<T>(() => {
    const stored = localStorage.getItem(key)
    return stored ? JSON.parse(stored) : initialValue
  })

  useEffect(() => {
    localStorage.setItem(key, JSON.stringify(value))
  }, [key, value])

  return [value, setValue] as const
}

// Utilisation
function UserPreferences() {
  const [theme, setTheme] = useLocalStorage('theme', 'light')
  const [fontSize, setFontSize] = useLocalStorage('fontSize', 16)

  return (
    <div>
      <Button onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>
        Toggle Theme: {theme}
      </Button>
      <Button onClick={() => setFontSize(fontSize + 1)}>
        Font Size: {fontSize}
      </Button>
    </div>
  )
}
```

## Patterns Courants

### Liste avec Loading et Empty States

```tsx
import { Loader, Card, Button } from '@/components/ui'

interface Item {
  id: number
  name: string
}

function ItemList() {
  const [items, setItems] = useState<Item[]>([])
  const [loading, setLoading] = useState(true)

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Loader text="Chargement des items..." />
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <Card className="text-center py-12">
        <p className="text-primary-600 mb-4">Aucun item trouvé</p>
        <Button>Ajouter un item</Button>
      </Card>
    )
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {items.map(item => (
        <Card key={item.id}>
          <h3 className="font-semibold">{item.name}</h3>
        </Card>
      ))}
    </div>
  )
}
```

### Modal Simple

```tsx
import { useState } from 'react'
import { Card, Button } from '@/components/ui'

function Modal({
  isOpen,
  onClose,
  children
}: {
  isOpen: boolean
  onClose: () => void
  children: React.ReactNode
}) {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <Card
        variant="elevated"
        className="max-w-md w-full animate-slide-up"
        onClick={(e) => e.stopPropagation()}
      >
        {children}
        <div className="mt-4 flex justify-end">
          <Button onClick={onClose} variant="secondary">
            Fermer
          </Button>
        </div>
      </Card>
    </div>
  )
}

// Utilisation
function ModalExample() {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <>
      <Button onClick={() => setIsOpen(true)}>
        Ouvrir Modal
      </Button>

      <Modal isOpen={isOpen} onClose={() => setIsOpen(false)}>
        <h2 className="text-xl font-bold mb-2">Titre du Modal</h2>
        <p className="text-primary-600">Contenu du modal...</p>
      </Modal>
    </>
  )
}
```

### Debounced Search

```tsx
import { useState, useEffect } from 'react'
import { Input } from '@/components/ui'

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value)
    }, delay)

    return () => clearTimeout(handler)
  }, [value, delay])

  return debouncedValue
}

function SearchComponent() {
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounce(search, 500)

  useEffect(() => {
    if (debouncedSearch) {
      // Faire la recherche
      console.log('Recherche:', debouncedSearch)
    }
  }, [debouncedSearch])

  return (
    <Input
      placeholder="Rechercher..."
      value={search}
      onChange={(e) => setSearch(e.target.value)}
      fullWidth
    />
  )
}
```

## Styles TailwindCSS Courants

### Layouts Responsive

```tsx
// Grid responsive
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">

// Flex avec wrap
<div className="flex flex-wrap gap-2">

// Centrer verticalement et horizontalement
<div className="flex items-center justify-center min-h-screen">

// Container avec max-width
<div className="container mx-auto px-4 max-w-7xl">
```

### États Hover et Focus

```tsx
// Bouton avec hover
<button className="bg-primary-950 hover:bg-primary-800 transition-colors">

// Card avec hover elevation
<div className="border-2 border-primary-200 hover:shadow-lg transition-shadow">

// Link avec underline au hover
<a className="text-primary-950 hover:underline">
```

### Animations

```tsx
// Fade in
<div className="animate-fade-in">

// Slide up
<div className="animate-slide-up">

// Transition personnalisée
<div className="transition-all duration-300 ease-in-out">
```
