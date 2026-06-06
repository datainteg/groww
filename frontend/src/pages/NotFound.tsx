import { Link } from 'react-router-dom'
import { Home, AlertCircle } from 'lucide-react'

export default function NotFound() {
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-dark-950 flex items-center justify-center transition-colors duration-200">
      <div className="text-center">
        <AlertCircle className="w-16 h-16 mx-auto text-gray-400 dark:text-dark-600 mb-4" />
        <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-2">404</h1>
        <p className="text-gray-500 dark:text-dark-400 mb-6">Page not found</p>
        <Link to="/" className="btn-primary inline-flex">
          <Home className="w-4 h-4" /> Back to Dashboard
        </Link>
      </div>
    </div>
  )
}
