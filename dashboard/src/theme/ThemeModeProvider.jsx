import { createContext, useContext, useMemo, useState } from 'react'
import { ThemeProvider, createTheme } from '@mui/material/styles'

const ThemeModeContext = createContext({ mode: 'dark', toggleMode: () => {} })

const baseTokens = {
  light: {
    background: '#f6f2e8',
    paper: '#fffaf0',
    accent: '#8a3b12',
    accentSoft: '#e8c7ae',
    text: '#1f1b16',
    muted: '#695d52',
  },
  dark: {
    background: '#111418',
    paper: '#171c21',
    accent: '#f4a261',
    accentSoft: '#4b2f1e',
    text: '#f3efe8',
    muted: '#b8aa98',
  },
}

export function ThemeModeProvider({ children }) {
  const [mode, setMode] = useState(() => localStorage.getItem('briefbot-dashboard-theme') || 'dark')

  const toggleMode = () => {
    setMode((current) => {
      const next = current === 'dark' ? 'light' : 'dark'
      localStorage.setItem('briefbot-dashboard-theme', next)
      return next
    })
  }

  const theme = useMemo(() => {
    const token = baseTokens[mode]
    return createTheme({
      palette: {
        mode,
        primary: { main: token.accent },
        background: { default: token.background, paper: token.paper },
        text: { primary: token.text, secondary: token.muted },
      },
      shape: { borderRadius: 18 },
      typography: {
        fontFamily: 'Georgia, ui-serif, serif',
        h3: { fontWeight: 700 },
        h4: { fontWeight: 700 },
        h5: { fontWeight: 700 },
        button: { textTransform: 'none', fontWeight: 600 },
      },
      components: {
        MuiPaper: {
          styleOverrides: {
            root: {
              backgroundImage: 'none',
              border: `1px solid ${token.accentSoft}`,
            },
          },
        },
      },
      customTokens: token,
    })
  }, [mode])

  return (
    <ThemeModeContext.Provider value={{ mode, toggleMode }}>
      <ThemeProvider theme={theme}>{children}</ThemeProvider>
    </ThemeModeContext.Provider>
  )
}

export function useThemeMode() {
  return useContext(ThemeModeContext)
}
