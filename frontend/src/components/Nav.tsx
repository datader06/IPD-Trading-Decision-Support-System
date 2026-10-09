import { NavLink } from 'react-router-dom'
import LogoMark from './Logo'

const link = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-3 py-2 text-sm transition-colors duration-200 ${isActive ? 'bg-white/[0.07] text-fg' : 'text-dim hover:text-fg'}`

export default function Nav() {
  return (
    <header className="sticky top-0 z-40 border-b border-white/[0.07] bg-bg/55 backdrop-blur-xl backdrop-saturate-150">
      <nav className="mx-auto flex h-14 max-w-[1400px] items-center justify-between px-4 sm:px-6" aria-label="Main">
        <NavLink to="/" className="flex items-center gap-2.5 font-display text-[17px] font-semibold tracking-tight">
          <LogoMark />
          IPD Desk
        </NavLink>
        <div className="flex items-center gap-1">
          <NavLink to="/" end className={link}>
            Overview
          </NavLink>
          <NavLink to="/desk" className={link}>
            Desk
          </NavLink>
        </div>
      </nav>
    </header>
  )
}
