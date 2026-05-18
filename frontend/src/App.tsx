import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from '@/components/Layout'
import Builder from '@/pages/Builder'
import Dashboard from '@/pages/Dashboard'
import RunsList from '@/pages/RunsList'
import Screener from '@/pages/Screener'
import WalkForward from '@/pages/WalkForward'
import WalkForwardResult from '@/pages/WalkForwardResult'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<RunsList />} />
        <Route path="builder" element={<Builder />} />
        <Route path="walkforward" element={<WalkForward />} />
        <Route path="walkforward/:runId" element={<WalkForwardResult />} />
        <Route path="runs/:runId" element={<Dashboard />} />
        <Route path="screener" element={<Screener />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
