import { useState } from 'react'
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import StarBorderRoundedIcon from '@mui/icons-material/StarBorderRounded'
import StarRoundedIcon from '@mui/icons-material/StarRounded'
import { api } from '../services/api'

export default function FavoriteButton({ title, url, itemId }) {
  const [open, setOpen] = useState(false)
  const [addingDefault, setAddingDefault] = useState(false)
  const [addingFolder, setAddingFolder] = useState(false)
  const [error, setError] = useState('')
  const [folders, setFolders] = useState([])
  const [selectedFolderId, setSelectedFolderId] = useState('favorites')
  const [newFolderName, setNewFolderName] = useState('')
  const [favoritesItems, setFavoritesItems] = useState([])
  const [starred, setStarred] = useState(false)

  const loadFoldersAndItems = async () => {
    const [folderRows, favoritePayload] = await Promise.all([
      api.listFavoriteFolders(),
      api.listFavoriteItems({ folder_id: 'favorites' }),
    ])
    setFolders(folderRows || [])
    setFavoritesItems((favoritePayload?.items || []).slice(0, 25))
  }

  const openModal = async () => {
    try {
      setAddingDefault(true)
      setError('')
      await api.addFavoriteItem({
        title: title || url || '(untitled)',
        url,
        item_id: itemId || null,
      })
      setStarred(true)
      await loadFoldersAndItems()
      setOpen(true)
    } catch (err) {
      setError(err.message || 'Failed to add favorite.')
      setOpen(true)
    } finally {
      setAddingDefault(false)
    }
  }

  const addToFolder = async () => {
    try {
      setAddingFolder(true)
      setError('')
      let folderId = selectedFolderId || 'favorites'
      const trimmed = newFolderName.trim()
      if (trimmed) {
        const created = await api.createFavoriteFolder({ name: trimmed })
        folderId = created.folder_id
        setSelectedFolderId(folderId)
        setNewFolderName('')
      }
      await api.addFavoriteItem({
        title: title || url || '(untitled)',
        url,
        item_id: itemId || null,
        folder_id: folderId,
      })
      await loadFoldersAndItems()
    } catch (err) {
      setError(err.message || 'Failed to add to folder.')
    } finally {
      setAddingFolder(false)
    }
  }

  return (
    <>
      <IconButton
        size="small"
        color={starred ? 'warning' : 'default'}
        onClick={openModal}
        disabled={!url || addingDefault}
        aria-label="Favorite"
      >
        {starred ? <StarRoundedIcon fontSize="small" /> : <StarBorderRoundedIcon fontSize="small" />}
      </IconButton>
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Add To Folder</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 0.5 }}>
            <Typography variant="body2" color="text.secondary">
              This link is saved in the default `favorites` folder.
            </Typography>
            {error ? <Typography color="error" variant="body2">{error}</Typography> : null}
            <FormControl fullWidth>
              <InputLabel>Folder</InputLabel>
              <Select
                value={selectedFolderId}
                label="Folder"
                onChange={(event) => setSelectedFolderId(event.target.value)}
              >
                {(folders || []).map((folder) => (
                  <MenuItem key={folder.folder_id} value={folder.folder_id}>
                    {folder.name} ({folder.count || 0})
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              fullWidth
              label="Create New Folder"
              value={newFolderName}
              onChange={(event) => setNewFolderName(event.target.value)}
              placeholder="Folder name"
            />
            <Button variant="contained" onClick={addToFolder} disabled={addingFolder}>
              Add To Folder
            </Button>
            <div>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>Favorites</Typography>
              {favoritesItems.length ? (
                <ol style={{ margin: 0, paddingLeft: '1.5rem' }}>
                  {favoritesItems.map((item) => (
                    <li key={item.favorite_id} style={{ marginBottom: '0.35rem' }}>
                      <Typography
                        component="a"
                        href={item.url}
                        target="_blank"
                        rel="noreferrer"
                        variant="body2"
                        sx={{ color: 'primary.main' }}
                      >
                        {item.title}
                      </Typography>
                    </li>
                  ))}
                </ol>
              ) : (
                <Typography variant="body2" color="text.secondary">No favorites yet.</Typography>
              )}
            </div>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </>
  )
}
