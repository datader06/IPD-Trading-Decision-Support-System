import { Suspense, lazy } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { SmoothScroll } from './lib/smooth'

// Each page is its own chunk: the chart library only loads on the desk, the WebGL background only on the overview.
const Landing = lazy(() => import('./pages/Landing'))
const Desk = lazy(() => import('./pages/Desk'))
const NotFound = lazy(() => import('./pages/NotFound'))

export default function App() {
  return (
    <BrowserRouter>
      <SmoothScroll>
        <Suspense fallback={<div className="min-h-dvh" aria-busy="true" />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/desk" element={<Desk />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </SmoothScroll>
    </BrowserRouter>
  )
}
