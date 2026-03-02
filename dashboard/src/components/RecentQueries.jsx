import { List, ListItemButton, ListItemText, Paper, Stack, Typography } from '@mui/material'

export default function RecentQueries({ items, selectedId, loading, onSelect }) {
  return (
    <Paper sx={{ p: 1.5, position: 'sticky', top: 108 }}>
      <Stack spacing={0.25} sx={{ px: 1.5, pt: 0.5, pb: 1.5 }}>
        <div>
          <Typography variant="overline" sx={{ color: 'text.secondary', letterSpacing: 2 }}>
            Recent Queries
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Last 14 days, capped at 20. Selecting one reopens the exact stored response.
          </Typography>
        </div>
      </Stack>
      {loading ? <Typography color="text.secondary" sx={{ px: 1.5, py: 2 }}>Loading query history...</Typography> : null}
      {!loading && items.length === 0 ? <Typography color="text.secondary" sx={{ px: 1.5, py: 2 }}>No saved queries yet.</Typography> : null}
      {!loading && items.length > 0 ? (
        <List disablePadding sx={{ maxHeight: 'calc(100vh - 190px)', overflowY: 'auto' }}>
          {items.map((item) => (
            <ListItemButton
              key={item.id}
              selected={item.id === selectedId}
              onClick={() => onSelect(item.id)}
              sx={{
                borderRadius: 3,
                mb: 0.75,
                alignItems: 'flex-start',
                border: 1,
                borderColor: item.id === selectedId ? 'primary.main' : 'divider',
              }}
            >
              <ListItemText
                primary={item.user_query}
                secondary={new Date(item.created_at).toLocaleString()}
                primaryTypographyProps={{ sx: { fontWeight: 700 } }}
                secondaryTypographyProps={{ sx: { mt: 0.5 } }}
              />
            </ListItemButton>
          ))}
        </List>
      ) : null}
    </Paper>
  )
}
