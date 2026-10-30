import { Route, Routes } from 'react-router'
import { AppShell } from '@/components/app-shell'
import { MachinePage } from '@/pages/machine'
import { OverviewPage } from '@/pages/overview'

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<OverviewPage />} />
        <Route path="machines/:id" element={<MachinePage />} />
        <Route path="*" element={<OverviewPage />} />
      </Route>
    </Routes>
  )
}
