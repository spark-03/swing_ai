import React from 'react'
import ReactDom from 'react-dom/client'
import './index.css'
import App from './app.jsx'
import { ErrorBoundary } from './components/ErrorBoundary.jsx'

ReactDom.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
)
