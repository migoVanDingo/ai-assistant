import { AppBar, Box, IconButton, Stack, Toolbar, Typography } from '@mui/material'
import LightModeRoundedIcon from '@mui/icons-material/LightModeRounded'
import DarkModeRoundedIcon from '@mui/icons-material/DarkModeRounded'
import ArticleRoundedIcon from '@mui/icons-material/ArticleRounded'
import SmartToyRoundedIcon from '@mui/icons-material/SmartToyRounded'
import { Link, useLocation } from 'react-router-dom'
import { useTheme } from '@mui/material/styles'
import { useThemeMode } from '../theme/ThemeModeProvider'
import { useGreeting } from '../hooks/useGreeting'

export default function HeaderBar() {
  const location = useLocation()
  const theme = useTheme()
  const { mode, toggleMode } = useThemeMode()
  const greeting = useGreeting()

  const navItems = [
    { to: '/', label: 'Morning Brief', icon: <ArticleRoundedIcon fontSize="small" /> },
    { to: '/ask', label: 'Ask Briefbot', icon: <SmartToyRoundedIcon fontSize="small" /> },
  ]

  return (
    <AppBar position="sticky" elevation={0} sx={{ bgcolor: 'background.paper', color: 'text.primary', borderBottom: 1, borderColor: 'divider' }}>
      <Toolbar sx={{ gap: 2, py: 1 }}>
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="overline" sx={{ letterSpacing: 2, color: 'text.secondary' }}>
            Morning Brief Dashboard
          </Typography>
          <Typography variant="h5">{greeting}</Typography>
        </Box>
        <Stack direction="row" spacing={1} sx={{ mr: 1 }}>
          {navItems.map((item) => {
            const active = location.pathname === item.to
            return (
              <Box
                key={item.to}
                component={Link}
                to={item.to}
                sx={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 1,
                  px: 1.5,
                  py: 1,
                  borderRadius: 999,
                  textDecoration: 'none',
                  bgcolor: active ? 'primary.main' : 'transparent',
                  color: active ? 'primary.contrastText' : 'text.secondary',
                  border: 1,
                  borderColor: active ? 'primary.main' : 'divider',
                }}
              >
                {item.icon}
                <Typography variant="body2">{item.label}</Typography>
              </Box>
            )
          })}
        </Stack>
        <IconButton onClick={toggleMode} color="inherit" sx={{ border: 1, borderColor: 'divider' }}>
          {mode === 'dark' ? <LightModeRoundedIcon /> : <DarkModeRoundedIcon />}
        </IconButton>
      </Toolbar>
    </AppBar>
  )
}
