import { List, ListItemButton, ListItemText, Paper, Typography } from '@mui/material'

export default function BriefSidebar({ briefs, selectedDate, onSelect }) {
  return (
    <Paper sx={{ p: 1.5, position: 'sticky', top: 104 }}>
      <Typography variant="overline" sx={{ px: 1.5, color: 'text.secondary' }}>
        Brief Archive
      </Typography>
      <List disablePadding>
        {briefs.map((brief) => (
          <ListItemButton
            key={brief.date}
            selected={brief.date === selectedDate}
            onClick={() => onSelect(brief.date)}
            sx={{ borderRadius: 2, mb: 0.5 }}
          >
            <ListItemText
              primary={brief.date}
              secondary={new Date(brief.updated_at).toLocaleString()}
              primaryTypographyProps={{ fontWeight: 600 }}
            />
          </ListItemButton>
        ))}
      </List>
    </Paper>
  )
}
