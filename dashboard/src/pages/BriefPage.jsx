import { Grid2 as Grid, Paper, Stack, Typography, useMediaQuery } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import BriefSidebar from '../components/BriefSidebar'
import BriefViewer from '../components/BriefViewer'
import MetricsCards from '../components/MetricsCards'

export default function BriefPage({ briefs, selectedDate, markdown, metrics, onSelectBrief }) {
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))
  return (
    <Stack spacing={3}>
      {!isMobile ? <MetricsCards metrics={metrics} /> : null}
      <Paper sx={{ p: { xs: 2, md: 2.5 }, borderRadius: 4 }}>
        <Typography variant="h5" sx={{ mb: 0.5 }}>Morning Brief Archive</Typography>
        <Typography color="text.secondary">
          Briefs are loaded directly from the markdown files in the briefs directory. Use the menu to switch views on mobile.
        </Typography>
      </Paper>
      <Grid container spacing={3} alignItems="flex-start">
        <Grid size={{ md: 3 }} sx={{ display: { xs: 'none', md: 'block' } }}>
          <BriefSidebar briefs={briefs} selectedDate={selectedDate} onSelect={onSelectBrief} />
        </Grid>
        <Grid size={{ xs: 12, md: 9 }}>
          {selectedDate ? (
            <BriefViewer markdown={markdown} title={selectedDate} />
          ) : (
            <Typography color="text.secondary">No brief files found.</Typography>
          )}
        </Grid>
      </Grid>
    </Stack>
  )
}
