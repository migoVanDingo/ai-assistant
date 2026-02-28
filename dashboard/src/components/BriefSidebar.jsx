import { List, ListItemButton, ListItemText, Paper, Stack, Typography } from '@mui/material'

export default function BriefSidebar({ briefs, selectedDate, onSelect }) {
  return (
    <Paper sx={{ p: 1.5, position: 'sticky', top: 108 }}>
      <Stack spacing={0.25} sx={{ px: 1.5, pt: 0.5, pb: 1.5 }}>
        <Typography variant="overline" sx={{ color: 'text.secondary', letterSpacing: 2 }}>
          Brief Archive
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Reading directly from the markdown files in the briefs directory.
        </Typography>
      </Stack>
      <List disablePadding sx={{ maxHeight: 'calc(100vh - 190px)', overflowY: 'auto' }}>
        {briefs.map((brief) => (
          <ListItemButton
            key={brief.date}
            selected={brief.date === selectedDate}
            onClick={() => onSelect(brief.date)}
            sx={{
              borderRadius: 3,
              mb: 0.75,
              alignItems: 'flex-start',
              border: 1,
              borderColor: brief.date === selectedDate ? 'primary.main' : 'divider',
            }}
          >
            <ListItemText
              primary={brief.date}
              secondary={new Date(brief.updated_at).toLocaleString()}
              primaryTypographyProps={{ fontWeight: 700 }}
              secondaryTypographyProps={{ sx: { mt: 0.5 } }}
            />
          </ListItemButton>
        ))}
        {briefs.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 2 }}>
            No brief files were found in the configured briefs directory.
          </Typography>
        ) : null}
      </List>
    </Paper>
  )
}
