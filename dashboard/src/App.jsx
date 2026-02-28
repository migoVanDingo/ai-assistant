import { Box, Container } from '@mui/material'
import { Routes, Route } from 'react-router-dom'
import HeaderBar from './components/HeaderBar'
import BriefPage from './pages/BriefPage'
import QueryPage from './pages/QueryPage'

export default function App() {
  return (
    <Box
      sx={{
        minHeight: '100vh',
        background: (theme) =>
          theme.palette.mode === 'dark'
            ? 'radial-gradient(circle at top right, rgba(90,176,255,0.18), transparent 28%), linear-gradient(180deg, #0b1220 0%, #0f1725 38%, #0b1220 100%)'
            : 'radial-gradient(circle at top right, rgba(23,105,170,0.12), transparent 25%), linear-gradient(180deg, #f4f7fb 0%, #eef4fa 36%, #f6f9fc 100%)',
      }}
    >
      <HeaderBar />
      <Container maxWidth="xl" sx={{ py: { xs: 2.5, md: 4 } }}>
        <Routes>
          <Route path="/" element={<BriefPage />} />
          <Route path="/ask" element={<QueryPage />} />
        </Routes>
      </Container>
    </Box>
  )
}
