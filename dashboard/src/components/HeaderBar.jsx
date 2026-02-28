import {
  AppBar,
  Box,
  Chip,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Stack,
  Toolbar,
  Typography,
  useMediaQuery,
} from '@mui/material'
import LightModeRoundedIcon from '@mui/icons-material/LightModeRounded'
import DarkModeRoundedIcon from '@mui/icons-material/DarkModeRounded'
import ArticleRoundedIcon from '@mui/icons-material/ArticleRounded'
import SmartToyRoundedIcon from '@mui/icons-material/SmartToyRounded'
import MenuRoundedIcon from '@mui/icons-material/MenuRounded'
import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useTheme } from '@mui/material/styles'
import { useThemeMode } from '../theme/ThemeModeProvider'
import { useGreeting } from '../hooks/useGreeting'

export default function HeaderBar({ briefs, selectedDate, onSelectBrief }) {
  const location = useLocation()
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))
  const { mode, toggleMode } = useThemeMode()
  const greeting = useGreeting()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const showBriefsMenu = location.pathname === '/'

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
      <Toolbar sx={{ gap: { xs: 1, md: 2 }, py: { xs: 0.9, md: 1.25 }, minHeight: { xs: 72, md: 88 } }}>
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="overline" sx={{ letterSpacing: { xs: 1.8, md: 2.4 }, color: 'text.secondary', fontSize: { xs: 10, md: 12 } }}>
            Morning Brief Dashboard
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <Typography variant={isMobile ? 'h6' : 'h4'} sx={{ lineHeight: 1.1 }}>
              {greeting}
            </Typography>
            {!isMobile ? <Chip size="small" label="Archive + Query Workspace" sx={{ bgcolor: 'background.paper' }} /> : null}
          </Stack>
        </Box>
        {!isMobile ? (
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
        ) : null}
        <IconButton onClick={toggleMode} color="inherit" sx={{ border: 1, borderColor: 'divider', bgcolor: 'background.paper' }}>
          {mode === 'dark' ? <LightModeRoundedIcon /> : <DarkModeRoundedIcon />}
        </IconButton>
        {isMobile ? (
          <>
            <IconButton
              onClick={() => setDrawerOpen(true)}
              color="inherit"
              sx={{ border: 1, borderColor: 'divider', bgcolor: 'background.paper' }}
            >
              <MenuRoundedIcon />
            </IconButton>
            <Drawer
              anchor="right"
              open={drawerOpen}
              onClose={() => setDrawerOpen(false)}
              PaperProps={{
                sx: {
                  width: 'min(86vw, 360px)',
                  p: 1.25,
                  bgcolor: 'background.default',
                },
              }}
            >
              <Stack spacing={1} sx={{ height: '100%' }}>
                <Box sx={{ px: 1.25, pt: 0.5 }}>
                  <Typography variant="overline" sx={{ color: 'text.secondary', letterSpacing: 2 }}>
                    Navigation
                  </Typography>
                  <Typography variant="h6">Menu</Typography>
                </Box>
                <List disablePadding>
                  {navItems.map((item) => {
                    const active = location.pathname === item.to
                    return (
                      <ListItemButton
                        key={item.to}
                        component={Link}
                        to={item.to}
                        selected={active}
                        onClick={() => setDrawerOpen(false)}
                        sx={{ borderRadius: 3, mb: 0.75 }}
                      >
                        <ListItemIcon sx={{ minWidth: 36, color: 'inherit' }}>{item.icon}</ListItemIcon>
                        <ListItemText primary={item.label} />
                      </ListItemButton>
                    )
                  })}
                </List>
                {showBriefsMenu ? (
                  <>
                    <Divider sx={{ my: 0.5 }} />
                    <Box sx={{ px: 1.25 }}>
                      <Typography variant="overline" sx={{ color: 'text.secondary', letterSpacing: 2 }}>
                        Brief Archive
                      </Typography>
                    </Box>
                    <List disablePadding sx={{ overflowY: 'auto', flex: 1, pr: 0.5 }}>
                      {briefs.map((brief) => (
                        <ListItemButton
                          key={brief.date}
                          selected={brief.date === selectedDate}
                          onClick={() => {
                            onSelectBrief(brief.date)
                            setDrawerOpen(false)
                          }}
                          sx={{ borderRadius: 3, mb: 0.75, alignItems: 'flex-start' }}
                        >
                          <ListItemText
                            primary={brief.date}
                            secondary={new Date(brief.updated_at).toLocaleString()}
                            primaryTypographyProps={{ fontWeight: 700 }}
                            secondaryTypographyProps={{ sx: { mt: 0.35 } }}
                          />
                        </ListItemButton>
                      ))}
                    </List>
                  </>
                ) : null}
              </Stack>
            </Drawer>
          </>
        ) : null}
      </Toolbar>
    </AppBar>
  )
}
