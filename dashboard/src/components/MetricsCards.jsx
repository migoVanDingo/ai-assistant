import { Grid2 as Grid, Paper, Stack, Typography } from '@mui/material'

export default function MetricsCards({ metrics }) {
  const cards = [
    { label: 'Briefs', value: metrics?.brief_count ?? '—', hint: metrics?.latest_brief_date ? `Latest ${metrics.latest_brief_date}` : 'No brief yet' },
    { label: 'Items', value: metrics?.item_count ?? '—', hint: `${metrics?.items_last_7d ?? 0} in last 7d` },
    { label: 'Clusters', value: metrics?.cluster_count ?? '—', hint: 'Storylines tracked' },
    { label: 'Topics', value: metrics?.topic_count ?? '—', hint: 'Computed topic profiles' },
  ]

  return (
    <Grid container spacing={2} sx={{ mb: 3 }}>
      {cards.map((card) => (
        <Grid key={card.label} size={{ xs: 12, sm: 6, lg: 3 }}>
          <Paper sx={{ p: 2.75, borderRadius: 4 }}>
            <Stack spacing={0.5} sx={{ textAlign: 'center', alignItems: 'center' }}>
              <Typography variant="overline" color="text.secondary">{card.label}</Typography>
              <Typography variant="h4">{card.value}</Typography>
              <Typography variant="body2" color="text.secondary">{card.hint}</Typography>
            </Stack>
          </Paper>
        </Grid>
      ))}
    </Grid>
  )
}
