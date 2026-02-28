import { Divider, Paper, Stack, Typography } from '@mui/material'
import ReactMarkdown from 'react-markdown'

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
      <ReactMarkdown
        components={{
          h1: ({ children }) => <Typography variant="h3" sx={{ mt: 2, mb: 3 }}>{children}</Typography>,
          h2: ({ children }) => <Typography variant="h5" sx={{ mt: 4, mb: 2.25 }}>{children}</Typography>,
          h3: ({ children }) => <Typography variant="h6" sx={{ mt: 3, mb: 1.5, color: 'primary.main' }}>{children}</Typography>,
          p: ({ children }) => <Typography variant="body1" sx={{ mb: 2.2, lineHeight: 1.9, color: 'text.primary' }}>{children}</Typography>,
          li: ({ children }) => <li><Typography variant="body1" sx={{ mb: 1.2, lineHeight: 1.85 }}>{children}</Typography></li>,
          a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer" style={{ color: 'inherit', fontWeight: 700 }}>{children}</a>,
          em: ({ children }) => <Typography component="em" variant="body2" sx={{ color: 'text.secondary', display: 'block', mb: 2 }}>{children}</Typography>,
        }}
      >
        {markdown || '_No brief selected._'}
      </ReactMarkdown>
    </Paper>
  )
}
