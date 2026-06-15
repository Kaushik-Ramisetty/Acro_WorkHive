import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import AppRoutes from './routes/AppRoutes.jsx'
import { ThemeProvider } from './context/ThemeContext.jsx'
import { PayrollPeriodProvider } from './context/PayrollPeriodContext.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ThemeProvider>
      <PayrollPeriodProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </PayrollPeriodProvider>
    </ThemeProvider>
  </StrictMode>,
)
