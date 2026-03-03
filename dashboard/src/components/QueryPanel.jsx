import { LoadingButton } from '@mui/lab'
import { Alert, Chip, Paper, Stack, TextField, Typography } from '@mui/material'
import { useState } from 'react'

const samples = [
  'show me all of the trending topics from last month',
  'summarize Let There Be Claws: An Early Social Network Analysis of AI Agents on Moltbook',
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
          Query the SQLite archive through the DAO-backed LLM adapter. You can ask for records, related stories, or article summaries by title.
        </Typography>
        <TextField
          multiline
          minRows={3}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Ask about trends, related stories, named entities, recent news, or summarize an article by title."
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
