import {
  Box,
  Button,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import AddRoundedIcon from '@mui/icons-material/AddRounded'
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded'
import EditRoundedIcon from '@mui/icons-material/EditRounded'
import { useState } from 'react'

export default function ConversationSidebar({
  conversations = [],
  activeId,
  loading,
  onSelect,
  onNew,
  onDelete,
  onRename,
}) {
  const [editingId, setEditingId] = useState(null)
  const [draft, setDraft] = useState('')

  const beginEdit = (conversation) => {
    setEditingId(conversation.id)
    setDraft(conversation.title || '')
  }

  const commitEdit = () => {
    const title = draft.trim()
    if (editingId && title) onRename(editingId, title)
    setEditingId(null)
    setDraft('')
  }

  return (
    <Paper
      elevation={0}
      sx={{
        p: 1.5,
        border: 1,
        borderColor: 'divider',
        borderRadius: 4,
        bgcolor: 'background.paper',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <Button
        fullWidth
        variant="contained"
        startIcon={<AddRoundedIcon />}
        onClick={onNew}
        sx={{ borderRadius: 3, mb: 1.5 }}
      >
        New chat
      </Button>
      <Typography variant="overline" sx={{ color: 'text.secondary', px: 1, letterSpacing: 1.6 }}>
        Conversations
      </Typography>
      <List disablePadding sx={{ overflowY: 'auto', flex: 1, mt: 0.5 }}>
        {loading ? (
          <Typography variant="body2" color="text.secondary" sx={{ px: 1, py: 2 }}>
            Loading…
          </Typography>
        ) : null}
        {!loading && conversations.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ px: 1, py: 2 }}>
            No conversations yet.
          </Typography>
        ) : null}
        {conversations.map((conversation) => {
          if (conversation.id === editingId) {
            return (
              <Box key={conversation.id} sx={{ px: 1, py: 0.5 }}>
                <TextField
                  fullWidth
                  size="small"
                  autoFocus
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onBlur={commitEdit}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault()
                      commitEdit()
                    } else if (event.key === 'Escape') {
                      setEditingId(null)
                      setDraft('')
                    }
                  }}
                />
              </Box>
            )
          }
          return (
            <ListItemButton
              key={conversation.id}
              selected={conversation.id === activeId}
              onClick={() => onSelect(conversation.id)}
              sx={{
                borderRadius: 3,
                mb: 0.5,
                pr: 0.5,
                '& .conv-actions': { opacity: 0 },
                '&:hover .conv-actions': { opacity: 1 },
              }}
            >
              <ListItemText
                primary={conversation.title || 'New chat'}
                primaryTypographyProps={{
                  noWrap: true,
                  fontWeight: conversation.id === activeId ? 700 : 500,
                }}
                secondary={new Date(conversation.updated_at).toLocaleString()}
                secondaryTypographyProps={{ noWrap: true, fontSize: 11 }}
              />
              <Stack direction="row" spacing={0} className="conv-actions" sx={{ transition: 'opacity 0.15s' }}>
                <Box
                  component="span"
                  onClick={(event) => {
                    event.stopPropagation()
                    beginEdit(conversation)
                  }}
                >
                  <IconButton size="small" aria-label="Rename conversation">
                    <EditRoundedIcon fontSize="small" />
                  </IconButton>
                </Box>
                <Box
                  component="span"
                  onClick={(event) => {
                    event.stopPropagation()
                    onDelete(conversation.id)
                  }}
                >
                  <IconButton size="small" aria-label="Delete conversation">
                    <DeleteOutlineRoundedIcon fontSize="small" />
                  </IconButton>
                </Box>
              </Stack>
            </ListItemButton>
          )
        })}
      </List>
    </Paper>
  )
}
