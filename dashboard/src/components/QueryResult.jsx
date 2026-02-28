import { Accordion, AccordionDetails, AccordionSummary, Paper, Stack, Typography } from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'

export default function QueryResult({ result }) {
  if (!result) return null

  return (
    <Stack spacing={2}>
      <Paper sx={{ p: 3 }}>
        <Typography variant="overline" color="text.secondary">Answer</Typography>
        <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap', lineHeight: 1.8 }}>{result.answer}</Typography>
      </Paper>
      <Accordion>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography>Execution details</Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Stack spacing={1.5}>
            <Typography variant="body2"><strong>Tool:</strong> {result.tool}</Typography>
            <Typography variant="body2"><strong>Arguments:</strong> <code>{JSON.stringify(result.arguments)}</code></Typography>
            <Typography variant="body2"><strong>Data:</strong></Typography>
            <Paper variant="outlined" sx={{ p: 2, overflowX: 'auto' }}>
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{JSON.stringify(result.data, null, 2)}</pre>
            </Paper>
          </Stack>
        </AccordionDetails>
      </Accordion>
    </Stack>
  )
}
