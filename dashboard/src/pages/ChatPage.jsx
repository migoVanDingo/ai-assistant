import { Alert, Box, Chip, Grid2 as Grid, Stack, Typography } from '@mui/material'
import SmartToyRoundedIcon from '@mui/icons-material/SmartToyRounded'
import { useCallback, useEffect, useRef, useState } from 'react'
import ChatComposer from '../components/ChatComposer'
import ChatMessage from '../components/ChatMessage'
import ConversationSidebar from '../components/ConversationSidebar'
import { api } from '../services/api'

const SAMPLE_PROMPTS = [
  "What's trending in AI this week?",
  'Summarize the latest paper on agents',
  'Show me recent security news',
  'Find stories related to inference scaling',
]

let tempCounter = 0
const tempId = () => `local-${Date.now()}-${tempCounter++}`

export default function ChatPage() {
  const [conversations, setConversations] = useState([])
  const [listLoading, setListLoading] = useState(true)
  const [activeId, setActiveId] = useState(null)
  const [messages, setMessages] = useState([])
  const [streaming, setStreaming] = useState(false)
  const [streamText, setStreamText] = useState('')
  const [streamTools, setStreamTools] = useState([])
  const [error, setError] = useState('')
  const abortRef = useRef(null)
  const scrollRef = useRef(null)

  const refreshConversations = useCallback(async () => {
    try {
      const items = await api.listConversations({ limit: 100 })
      setConversations(items)
      return items
    } catch (err) {
      console.warn('failed to load conversations', err)
      return []
    } finally {
      setListLoading(false)
    }
  }, [])

  const loadConversation = useCallback(async (id) => {
    try {
      setError('')
      const conv = await api.getConversation(id)
      setActiveId(id)
      setMessages(
        (conv.messages || []).map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          tool_calls: (m.tool_calls || []).map((c) => ({ ...c, status: 'done' })),
        })),
      )
      setStreamText('')
      setStreamTools([])
    } catch (err) {
      setError(err.message || 'Failed to load conversation.')
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const items = await refreshConversations()
      if (!cancelled && items.length > 0) {
        loadConversation(items[0].id)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [refreshConversations, loadConversation])

  useEffect(() => {
    const node = scrollRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [messages, streamText, streamTools])

  const startNewChat = useCallback(() => {
    abortRef.current?.abort()
    setActiveId(null)
    setMessages([])
    setStreamText('')
    setStreamTools([])
    setError('')
  }, [])

  const handleDelete = useCallback(
    async (id) => {
      try {
        await api.deleteConversation(id)
      } catch (err) {
        console.warn('failed to delete conversation', err)
      }
      const items = await refreshConversations()
      if (id === activeId) {
        if (items.length > 0) {
          loadConversation(items[0].id)
        } else {
          startNewChat()
        }
      }
    },
    [activeId, refreshConversations, loadConversation, startNewChat],
  )

  const handleSend = useCallback(
    async (text) => {
      if (streaming) return
      setError('')

      let convId = activeId
      if (!convId) {
        try {
          const conv = await api.createConversation()
          convId = conv.id
          setActiveId(conv.id)
          setConversations((prev) => [conv, ...prev])
        } catch (err) {
          setError(err.message || 'Failed to start conversation.')
          return
        }
      }

      setMessages((prev) => [...prev, { id: tempId(), role: 'user', content: text }])
      setStreaming(true)
      setStreamText('')
      setStreamTools([])

      const controller = new AbortController()
      abortRef.current = controller
      let acc = ''
      let tools = []

      try {
        await api.streamChatMessage(convId, text, {
          signal: controller.signal,
          onEvent: (event) => {
            if (event.type === 'token') {
              acc += event.text
              setStreamText(acc)
            } else if (event.type === 'tool_start') {
              tools = [...tools, { id: event.id, name: event.name, status: 'running' }]
              setStreamTools(tools)
            } else if (event.type === 'tool_end') {
              tools = tools.map((t) =>
                t.id === event.id ? { ...t, status: 'done', summary: event.summary } : t,
              )
              setStreamTools(tools)
            } else if (event.type === 'title') {
              setConversations((prev) =>
                prev.map((c) => (c.id === convId ? { ...c, title: event.title } : c)),
              )
            } else if (event.type === 'error') {
              setError(event.message || 'Chat failed.')
            }
          },
        })
      } catch (err) {
        if (err.name !== 'AbortError') setError(err.message || 'Chat failed.')
      } finally {
        if (acc.trim() || tools.length) {
          setMessages((prev) => [
            ...prev,
            { id: tempId(), role: 'assistant', content: acc, tool_calls: tools },
          ])
        }
        setStreamText('')
        setStreamTools([])
        setStreaming(false)
        abortRef.current = null
        refreshConversations()
      }
    },
    [activeId, streaming, refreshConversations],
  )

  const handleRename = useCallback(async (id, title) => {
    setConversations((prev) => prev.map((c) => (c.id === id ? { ...c, title } : c)))
    try {
      await api.renameConversation(id, title)
    } catch (err) {
      console.warn('failed to rename conversation', err)
      refreshConversations()
    }
  }, [refreshConversations])

  const handleStop = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const showEmptyState = messages.length === 0 && !streaming

  return (
    <Grid container spacing={2.5} alignItems="stretch" sx={{ height: { md: 'calc(100vh - 200px)' } }}>
      <Grid size={{ xs: 12, md: 3 }} sx={{ height: { xs: 'auto', md: '100%' } }}>
        <ConversationSidebar
          conversations={conversations}
          activeId={activeId}
          loading={listLoading}
          onSelect={loadConversation}
          onNew={startNewChat}
          onDelete={handleDelete}
          onRename={handleRename}
        />
      </Grid>

      <Grid size={{ xs: 12, md: 9 }} sx={{ height: '100%' }}>
        <Stack spacing={1.5} sx={{ height: '100%' }}>
          {error ? <Alert severity="error" onClose={() => setError('')}>{error}</Alert> : null}

          <Box
            ref={scrollRef}
            sx={{
              flex: 1,
              overflowY: 'auto',
              minHeight: 320,
              px: { xs: 0, md: 1 },
              py: 1,
            }}
          >
            {showEmptyState ? (
              <Stack spacing={2.5} sx={{ height: '100%', justifyContent: 'center', alignItems: 'center', textAlign: 'center', px: 2 }}>
                <SmartToyRoundedIcon sx={{ fontSize: 48, color: 'primary.main' }} />
                <Box>
                  <Typography variant="h5">Ask Briefbot</Typography>
                  <Typography color="text.secondary" sx={{ mt: 0.5, maxWidth: 460 }}>
                    Chat with your research archive. Ask about trends, dig into related stories, or
                    have an article summarized.
                  </Typography>
                </Box>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" justifyContent="center">
                  {SAMPLE_PROMPTS.map((prompt) => (
                    <Chip key={prompt} label={prompt} onClick={() => handleSend(prompt)} />
                  ))}
                </Stack>
              </Stack>
            ) : (
              <Stack spacing={2.5}>
                {messages.map((message) => (
                  <ChatMessage
                    key={message.id}
                    role={message.role}
                    content={message.content}
                    toolCalls={message.tool_calls}
                  />
                ))}
                {streaming ? (
                  <ChatMessage role="assistant" content={streamText} toolCalls={streamTools} pending />
                ) : null}
              </Stack>
            )}
          </Box>

          <ChatComposer onSend={handleSend} onStop={handleStop} busy={streaming} />
        </Stack>
      </Grid>
    </Grid>
  )
}
