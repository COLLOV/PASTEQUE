import { NavLink } from 'react-router-dom'
import clsx from 'clsx'
import { HiChatBubbleLeftRight, HiChartBar, HiCog6Tooth } from 'react-icons/hi2'

interface NavigationProps {
  isAdmin: boolean
}

export default function Navigation({ isAdmin }: NavigationProps) {
  const links = [
    { to: '/chat', label: 'Chat', icon: HiChatBubbleLeftRight },
    { to: '/dashboard', label: 'Dashboard', icon: HiChartBar },
    ...(isAdmin ? [{ to: '/admin', label: 'Admin', icon: HiCog6Tooth }] : []),
  ]

  return (
    <nav className="border-b-2 border-primary-100 bg-white">
      <div className="container mx-auto px-4">
        <div className="flex gap-1">
          {links.map((link) => {
            const Icon = link.icon
            return (
              <NavLink
                key={link.to}
                to={link.to}
                className={({ isActive }) =>
                  clsx(
                    'flex items-center gap-2 px-4 py-3 text-sm font-medium',
                    'border-b-2 transition-all duration-200',
                    {
                      'border-primary-950 text-primary-950 bg-primary-50': isActive,
                      'border-transparent text-primary-600 hover:text-primary-950 hover:bg-primary-50': !isActive,
                    }
                  )
                }
              >
                <Icon className="w-4 h-4" />
                {link.label}
              </NavLink>
            )
          })}
        </div>
      </div>
    </nav>
  )
}
