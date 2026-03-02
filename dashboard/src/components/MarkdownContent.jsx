import { Typography } from '@mui/material'
import ReactMarkdown from 'react-markdown'

export default function MarkdownContent({ markdown }) {
  return (
    <ReactMarkdown
      components={{
        h1: ({ children }) => <Typography variant="h4" sx={{ mt: 1.5, mb: 2.5 }}>{children}</Typography>,
        h2: ({ children }) => <Typography variant="h5" sx={{ mt: 3, mb: 1.75 }}>{children}</Typography>,
        h3: ({ children }) => <Typography variant="h6" sx={{ mt: 2.5, mb: 1.25, color: 'primary.main' }}>{children}</Typography>,
        p: ({ children }) => <Typography variant="body1" sx={{ mb: 1.8, lineHeight: 1.85 }}>{children}</Typography>,
        li: ({ children }) => <li><Typography variant="body1" sx={{ mb: 1, lineHeight: 1.75 }}>{children}</Typography></li>,
        a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer" style={{ color: 'inherit', fontWeight: 700 }}>{children}</a>,
        em: ({ children }) => <Typography component="em" variant="body2" sx={{ color: 'text.secondary', display: 'block', mb: 1.5 }}>{children}</Typography>,
        code: ({ children }) => <code style={{ fontFamily: 'monospace' }}>{children}</code>,
      }}
    >
      {markdown || ''}
    </ReactMarkdown>
  )
}
