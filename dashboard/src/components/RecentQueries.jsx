import { List, ListItemButton, ListItemText, Paper, Stack, Typography } from '@mui/material'

export default function RecentQueries({ items, selectedId, loading, onSelect }) {
  return (
    <Paper sx={{ p: 2.5, borderRadius: 4 }}>
      <Stack spacing={1.5}>
        <div>
          <Typography variant="h6">Recent queries</Typography>
          <Typography variant="body2" color="text.secondary">
            Last 14 days, capped at 20. Selecting one reopens the exact stored response.
          </Typography>
        </div>
        {loading ? <Typography color="text.secondary">Loading query history...</Typography> : null}
        {!loading && items.length === 0 ? <Typography color="text.secondary">No saved queries yet.</Typography> : null}
        {!loading && items.length > 0 ? (
          <List disablePadding sx={{ maxHeight: { xs: 'none', md: 540 }, overflowY: 'auto' }}>
            {items.map((item) => (
              <ListItemButton
                key={item.id}
                selected={item.id === selectedId}
                onClick={() => onSelect(item.id)}
                sx={{ borderRadius: 3, alignItems: 'flex-start', mb: 0.75 }}
              >
                <ListItemText
                  primary={item.user_query}
                  secondary={`${new Date(item.created_at).toLocaleString()}${item.response_preview ? ` • ${item.response_preview}` : ''}`}
                  primaryTypographyProps={{ sx: { fontWeight: 700 } }}
                  secondaryTypographyProps={{ sx: { mt: 0.35 } }}
                />
              </ListItemButton>
            ))}
          </List>
        ) : null}
      </Stack>
    </Paper>
  )
}
