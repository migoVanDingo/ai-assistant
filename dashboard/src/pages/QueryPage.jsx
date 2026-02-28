import { useState } from 'react'
import QueryPanel from '../components/QueryPanel'
import QueryResult from '../components/QueryResult'
import { api } from '../services/api'

export default function QueryPage() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  const handleSubmit = async (query) => {
    try {
      setLoading(true)
      setError('')
      const payload = await api.query({ query })
      setResult(payload)
    } catch (err) {
      setError(err.message || 'Query failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <QueryPanel onSubmit={handleSubmit} loading={loading} error={error} />
      <QueryResult result={result} />
    </>
  )
}
