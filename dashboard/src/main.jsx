import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { CssBaseline, GlobalStyles } from '@mui/material'
import App from './App'
import { ThemeModeProvider } from './theme/ThemeModeProvider'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <ThemeModeProvider>
        <CssBaseline />
        <GlobalStyles
          styles={{
            body: { margin: 0 },
            '#root': { minHeight: '100vh' },
            a: { color: 'inherit' },
          }}
        />
        <App />
      </ThemeModeProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
