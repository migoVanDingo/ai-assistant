import { LoadingButton } from '@mui/lab'
import { Alert, Chip, Paper, Stack, TextField, Typography } from '@mui/material'
import { useState } from 'react'

const samples = [
  'show me all of the trending topics from last month',
  'are there any other stories related to Anthropic supply chain risk',
  'has there been any news about nvidia in the last week',
]

export default function QueryPanel({ onSubmit, loading, error }) {
  const [query, setQuery] = useState('')

  return (
    <Paper sx={{ p: 3, mb: 3 }}>
      <Stack spacing={2}>
        <Typography variant="h5">Ask Briefbot</Typography>
        <Typography color="text.secondary">
          Query the SQLite archive through the DAO-backed LLM adapter. Results stay grounded in returned database rows.
        </Typography>
        <TextField
          multiline
          minRows={3}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Ask about trends, related stories, named entities, or recent news."
        />
        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
          {samples.map((sample) => (
            <Chip key={sample} label={sample} onClick={() => setQuery(sample)} />
          ))}
        </Stack>
        {error ? <Alert severity="error">{error}</Alert> : null}
        <LoadingButton variant="contained" loading={loading} onClick={() => onSubmit(query)} disabled={!query.trim()}>
          Run query
        </LoadingButton>
      </Stack>
    </Paper>
  )
}
