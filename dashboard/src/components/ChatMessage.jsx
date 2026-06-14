import { Box, Paper, Stack, Typography } from '@mui/material'
import SmartToyRoundedIcon from '@mui/icons-material/SmartToyRounded'
import PersonRoundedIcon from '@mui/icons-material/PersonRounded'
import MarkdownContent from './MarkdownContent'
import ToolCallChips from './ToolCallChips'

export default function ChatMessage({ role, content, toolCalls = [], pending = false }) {
  const isUser = role === 'user'

  if (isUser) {
    return (
      <Stack direction="row" spacing={1.5} justifyContent="flex-end" sx={{ alignItems: 'flex-start' }}>
        <Paper
          elevation={0}
          sx={{
            p: 1.75,
            px: 2.25,
            maxWidth: '80%',
            bgcolor: 'primary.main',
            color: 'primary.contrastText',
            borderRadius: 3,
            borderTopRightRadius: 6,
          }}
        >
          <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>
            {content}
          </Typography>
        </Paper>
        <Box sx={{ mt: 0.5, color: 'text.secondary' }}>
          <PersonRoundedIcon fontSize="small" />
        </Box>
      </Stack>
    )
  }

  return (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: 'flex-start' }}>
      <Box sx={{ mt: 0.5, color: 'primary.main' }}>
        <SmartToyRoundedIcon fontSize="small" />
      </Box>
      <Paper
        elevation={0}
        sx={{
          p: 2,
          px: 2.5,
          maxWidth: '90%',
          bgcolor: 'background.paper',
          border: 1,
          borderColor: 'divider',
          borderRadius: 3,
          borderTopLeftRadius: 6,
          flexGrow: 1,
        }}
      >
        <ToolCallChips calls={toolCalls} />
        {content ? (
          <MarkdownContent markdown={content} />
        ) : pending ? (
          <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic' }}>
            Thinking…
          </Typography>
        ) : null}
      </Paper>
    </Stack>
  )
}
