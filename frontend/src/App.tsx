import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from '@/components/Layout'
import FactorCorrelation from '@/pages/FactorCorrelation'
import FactorLab from '@/pages/FactorLab'
import PortfolioBacktest from '@/pages/PortfolioBacktest'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<FactorLab />} />
        <Route path="factors" element={<FactorLab />} />
        <Route path="factors/:name" element={<FactorLab />} />
        <Route path="correlation" element={<FactorCorrelation />} />
        <Route path="portfolio" element={<PortfolioBacktest />} />
        <Route path="portfolio/runs/:runId" element={<PortfolioBacktest />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
