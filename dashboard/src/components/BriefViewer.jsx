import { Divider, Paper, Stack, Typography } from '@mui/material'
import MarkdownContent from './MarkdownContent'

export default function BriefViewer({ markdown, title }) {
  return (
    <Paper sx={{ p: { xs: 2.5, md: 4 }, borderRadius: 4 }}>
      <Stack spacing={2.5}>
        <div>
          <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 2 }}>
            Brief Reader
          </Typography>
          <Typography variant="h4">{title || 'Brief Content'}</Typography>
        </div>
        <Divider />
      </Stack>
      <MarkdownContent markdown={markdown || '_No brief selected._'} />
    </Paper>
  )
}
