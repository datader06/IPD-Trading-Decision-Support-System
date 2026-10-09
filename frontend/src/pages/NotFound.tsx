import { ArrowLeft } from '@phosphor-icons/react'
import { Link } from 'react-router-dom'
import Nav from '../components/Nav'

export default function NotFound() {
  return (
    <div className="min-h-dvh">
      <div className="ambient" aria-hidden="true" />
      <Nav />
      <main className="mx-auto flex min-h-[70dvh] max-w-[1400px] flex-col items-start justify-center px-4 sm:px-6">
        <p className="num mb-3 text-xs uppercase tracking-[0.22em] text-accent">404</p>
        <h1 className="max-w-[16ch] text-5xl font-semibold leading-[1.02] tracking-[-0.035em] sm:text-6xl">This page is not on the chart.</h1>
        <p className="mt-4 max-w-[52ch] text-dim">The address does not match anything here. Head back to the overview or open the desk.</p>
        <div className="mt-8 flex gap-3">
          <Link to="/" className="inline-flex items-center gap-2 rounded-xl bg-accent px-5 py-3 font-semibold text-on-accent">
            <ArrowLeft size={18} weight="bold" aria-hidden="true" /> Overview
          </Link>
          <Link to="/desk" className="glass rounded-xl px-5 py-3 text-fg/90 transition-colors duration-200 hover:bg-white/[0.08]">
            Open the desk
          </Link>
        </div>
      </main>
    </div>
  )
}
