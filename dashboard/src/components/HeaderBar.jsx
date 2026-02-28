import { AppBar, Box, Chip, IconButton, Stack, Toolbar, Typography } from '@mui/material'
import LightModeRoundedIcon from '@mui/icons-material/LightModeRounded'
import DarkModeRoundedIcon from '@mui/icons-material/DarkModeRounded'
import ArticleRoundedIcon from '@mui/icons-material/ArticleRounded'
import SmartToyRoundedIcon from '@mui/icons-material/SmartToyRounded'
import { Link, useLocation } from 'react-router-dom'
import { useThemeMode } from '../theme/ThemeModeProvider'
import { useGreeting } from '../hooks/useGreeting'

export default function HeaderBar() {
  const location = useLocation()
  const { mode, toggleMode } = useThemeMode()
  const greeting = useGreeting()

  const navItems = [
    { to: '/', label: 'Morning Brief', icon: <ArticleRoundedIcon fontSize="small" /> },
    { to: '/ask', label: 'Ask Briefbot', icon: <SmartToyRoundedIcon fontSize="small" /> },
  ]

  return (
    <AppBar
      position="sticky"
      elevation={0}
      sx={{
        bgcolor: 'transparent',
        color: 'text.primary',
        backdropFilter: 'blur(14px)',
        borderBottom: 1,
        borderColor: 'divider',
      }}
    >
      <Toolbar sx={{ gap: 2, py: 1.25 }}>
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="overline" sx={{ letterSpacing: 2.4, color: 'text.secondary' }}>
            Morning Brief Dashboard
          </Typography>
          <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap">
            <Typography variant="h4">{greeting}</Typography>
            <Chip size="small" label="Archive + Query Workspace" sx={{ bgcolor: 'background.paper' }} />
          </Stack>
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
                  bgcolor: active ? 'primary.main' : 'background.paper',
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
        <IconButton onClick={toggleMode} color="inherit" sx={{ border: 1, borderColor: 'divider', bgcolor: 'background.paper' }}>
          {mode === 'dark' ? <LightModeRoundedIcon /> : <DarkModeRoundedIcon />}
        </IconButton>
      </Toolbar>
    </AppBar>
  )
}
