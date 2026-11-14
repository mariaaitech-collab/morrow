import React from 'react'
import ReactDOM from 'react-dom/client'
import { HelmetProvider } from 'react-helmet-async'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary'
import './styles/tokens.css'
import './index.css'

// Browser chrome colour follows the page background token.
const themeColor = document.createElement('meta')
themeColor.name = 'theme-color'
themeColor.content = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()
document.head.appendChild(themeColor)

ReactDOM.createRoot(document.getElementById('root')).render(
  <HelmetProvider>
    <React.StrictMode>
      <ErrorBoundary showDetail>
        <App />
      </ErrorBoundary>
    </React.StrictMode>
  </HelmetProvider>,
)
