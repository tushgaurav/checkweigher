import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import App from '@/App'
import { TooltipProvider } from '@/components/ui/tooltip'
import { LiveProvider } from '@/lib/live'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1, staleTime: 10_000 } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <TooltipProvider delayDuration={300}>
          <LiveProvider>
            <App />
          </LiveProvider>
        </TooltipProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
