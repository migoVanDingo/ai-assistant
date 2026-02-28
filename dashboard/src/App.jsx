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
            ? 'linear-gradient(180deg, #111418 0%, #181f26 45%, #111418 100%)'
            : 'linear-gradient(180deg, #f6f2e8 0%, #efe4d3 40%, #f6f2e8 100%)',
      }}
    >
      <HeaderBar />
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Routes>
          <Route path="/" element={<BriefPage />} />
          <Route path="/ask" element={<QueryPage />} />
        </Routes>
      </Container>
    </Box>
  )
}
