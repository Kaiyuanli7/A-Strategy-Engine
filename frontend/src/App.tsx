import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from '@/components/Layout'
import Dashboard from '@/pages/Dashboard'
import RunsList from '@/pages/RunsList'
import Screener from '@/pages/Screener'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<RunsList />} />
        <Route path="runs/:runId" element={<Dashboard />} />
        <Route path="screener" element={<Screener />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
