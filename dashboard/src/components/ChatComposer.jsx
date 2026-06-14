import { IconButton, Paper, Stack, TextField } from '@mui/material'
import SendRoundedIcon from '@mui/icons-material/SendRounded'
import StopRoundedIcon from '@mui/icons-material/StopRounded'
import { useState } from 'react'

export default function ChatComposer({ onSend, onStop, busy }) {
  const [value, setValue] = useState('')

  const submit = () => {
    const text = value.trim()
    if (!text || busy) return
    onSend(text)
    setValue('')
  }

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <Paper
      elevation={0}
      sx={{
        p: 1,
        border: 1,
        borderColor: 'divider',
        borderRadius: 4,
        bgcolor: 'background.paper',
      }}
    >
      <Stack direction="row" spacing={1} alignItems="flex-end">
        <TextField
          fullWidth
          multiline
          maxRows={8}
          variant="standard"
          placeholder="Ask about trends, related stories, or summarize an article…"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          InputProps={{ disableUnderline: true, sx: { px: 1.5, py: 0.75 } }}
        />
        {busy ? (
          <IconButton color="error" onClick={onStop} aria-label="Stop">
            <StopRoundedIcon />
          </IconButton>
        ) : (
          <IconButton
            color="primary"
            onClick={submit}
            disabled={!value.trim()}
            aria-label="Send"
          >
            <SendRoundedIcon />
          </IconButton>
        )}
      </Stack>
    </Paper>
  )
}
