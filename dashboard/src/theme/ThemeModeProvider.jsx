import { createContext, useContext, useMemo, useState } from 'react'
import { ThemeProvider, createTheme } from '@mui/material/styles'

const ThemeModeContext = createContext({ mode: 'light', toggleMode: () => {} })

const baseTokens = {
  light: {
    background: '#f4f7fb',
    paper: '#ffffff',
    accent: '#1769aa',
    accentSoft: '#d7e7f6',
    accentStrong: '#0f4f84',
    text: '#0f1720',
    muted: '#5d6b7a',
    canvas: '#e9f1f8',
  },
  dark: {
    background: '#0b1220',
    paper: '#121b2b',
    accent: '#5ab0ff',
    accentSoft: '#1a2a43',
    accentStrong: '#8bc8ff',
    text: '#ebf3ff',
    muted: '#93a4b7',
    canvas: '#0f1725',
  },
}

export function ThemeModeProvider({ children }) {
  const [mode, setMode] = useState(() => localStorage.getItem('briefbot-dashboard-theme') || 'light')

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
        fontFamily: '"Inter", "SF Pro Display", "Segoe UI", "Helvetica Neue", Arial, sans-serif',
        h3: { fontWeight: 800, letterSpacing: '-0.03em' },
        h4: { fontWeight: 800, letterSpacing: '-0.02em' },
        h5: { fontWeight: 750, letterSpacing: '-0.02em' },
        h6: { fontWeight: 700 },
        button: { textTransform: 'none', fontWeight: 600 },
      },
      components: {
        MuiPaper: {
          styleOverrides: {
            root: {
              backgroundImage: 'none',
              border: `1px solid ${token.accentSoft}`,
              boxShadow: mode === 'dark' ? '0 18px 50px rgba(0, 0, 0, 0.25)' : '0 18px 50px rgba(15, 23, 32, 0.08)',
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
