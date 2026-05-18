import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from '@/components/Layout'
import FactorLab from '@/pages/FactorLab'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<FactorLab />} />
        <Route path="factors" element={<FactorLab />} />
        <Route path="factors/:name" element={<FactorLab />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
