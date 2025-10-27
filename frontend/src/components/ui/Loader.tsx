import { HTMLAttributes } from 'react'
import clsx from 'clsx'

interface LoaderProps extends HTMLAttributes<HTMLDivElement> {
  size?: 'sm' | 'md' | 'lg'
  text?: string
}

export default function Loader({ className, size = 'md', text, ...props }: LoaderProps) {
  return (
    <div
      className={clsx('flex items-center justify-center gap-3', className)}
      {...props}
    >
      <div
        className={clsx(
          'animate-spin rounded-full border-2 border-primary-200 border-t-primary-950',
          {
            'w-4 h-4': size === 'sm',
            'w-8 h-8': size === 'md',
            'w-12 h-12': size === 'lg',
          }
        )}
      />
      {text && (
        <span className="text-primary-600 text-sm font-medium animate-pulse">
          {text}
        </span>
      )}
    </div>
  )
}
