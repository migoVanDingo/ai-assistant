import { Chip, CircularProgress, Stack } from '@mui/material'
import CheckCircleRoundedIcon from '@mui/icons-material/CheckCircleRounded'
import BuildRoundedIcon from '@mui/icons-material/BuildRounded'

const TOOL_LABELS = {
  search_items: 'Searching archive',
  get_trending_topics: 'Reading trending topics',
  get_trend_clusters: 'Reading trend clusters',
  get_related_stories: 'Finding related stories',
  get_news_about: 'Looking up news',
  summarize_article: 'Summarizing article',
}

function labelFor(call) {
  const base = TOOL_LABELS[call.name] || call.name
  if (call.status === 'done' && call.summary) return `${base} · ${call.summary}`
  return base
}

export default function ToolCallChips({ calls = [] }) {
  if (!calls.length) return null
  return (
    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 1.25 }}>
      {calls.map((call) => (
        <Chip
          key={call.id || call.name}
          size="small"
          variant="outlined"
          icon={
            call.status === 'done' ? (
              <CheckCircleRoundedIcon fontSize="small" />
            ) : (
              <CircularProgress size={13} thickness={6} />
            )
          }
          deleteIcon={<BuildRoundedIcon />}
          label={labelFor(call)}
          color={call.status === 'done' ? 'success' : 'default'}
          sx={{ '& .MuiChip-icon': { ml: 1 } }}
        />
      ))}
    </Stack>
  )
}
