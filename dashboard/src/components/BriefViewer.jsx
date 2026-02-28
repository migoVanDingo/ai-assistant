import { Paper, Typography } from '@mui/material'
import ReactMarkdown from 'react-markdown'

export default function BriefViewer({ markdown, title }) {
  return (
    <Paper sx={{ p: { xs: 2, md: 4 } }}>
      <Typography variant="overline" color="text.secondary">{title || 'Brief Content'}</Typography>
      <ReactMarkdown
        components={{
          h1: ({ children }) => <Typography variant="h3" sx={{ mt: 1, mb: 3 }}>{children}</Typography>,
          h2: ({ children }) => <Typography variant="h5" sx={{ mt: 4, mb: 2 }}>{children}</Typography>,
          h3: ({ children }) => <Typography variant="h6" sx={{ mt: 3, mb: 1.5 }}>{children}</Typography>,
          p: ({ children }) => <Typography variant="body1" sx={{ mb: 2, lineHeight: 1.8 }}>{children}</Typography>,
          li: ({ children }) => <li><Typography variant="body1" sx={{ mb: 1.1, lineHeight: 1.8 }}>{children}</Typography></li>,
          a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
          em: ({ children }) => <Typography component="em" variant="body1" sx={{ color: 'text.secondary', display: 'block', mb: 2 }}>{children}</Typography>,
        }}
      >
        {markdown || '_No brief selected._'}
      </ReactMarkdown>
    </Paper>
  )
}
