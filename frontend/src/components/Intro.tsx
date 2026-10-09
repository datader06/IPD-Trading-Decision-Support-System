import { useGSAP } from '@gsap/react'
import gsap from 'gsap'
import { useRef } from 'react'
import LogoMark from './Logo'

/** One-time cinematic opener: logo and counter build up, then two shutters part to reveal the page.
 *  `onReveal` fires as the shutters start to move (the hero begins animating under them); `onDone` when it is safe to unmount. */
export default function Intro({ onReveal, onDone }: { onReveal: () => void; onDone: () => void }) {
  const root = useRef<HTMLDivElement>(null)
  const count = useRef<HTMLSpanElement>(null)

  useGSAP(
    () => {
      const n = { v: 0 }
      const tl = gsap.timeline({ onComplete: onDone })
      tl.fromTo('.in-logo', { scale: 0.5, opacity: 0, rotate: -12 }, { scale: 1, opacity: 1, rotate: 0, duration: 0.9, ease: 'expo.out' })
        .fromTo('.in-word', { yPercent: 115 }, { yPercent: 0, duration: 0.8, stagger: 0.09, ease: 'expo.out' }, 0.25)
        .fromTo('.in-line', { scaleX: 0 }, { scaleX: 1, duration: 1.5, ease: 'power2.inOut' }, 0.2)
        .to(
          n,
          {
            v: 100,
            duration: 1.5,
            ease: 'power2.inOut',
            onUpdate: () => {
              if (count.current) count.current.textContent = String(Math.round(n.v)).padStart(3, '0')
            },
          },
          0.2,
        )
        .to('.in-content', { opacity: 0, y: -24, scale: 0.96, duration: 0.45, ease: 'power2.in' }, '+=0.15')
        .call(onReveal, [], '>-0.05')
        .to('.in-top', { yPercent: -101, duration: 1.1, ease: 'expo.inOut' }, '<')
        .to('.in-bot', { yPercent: 101, duration: 1.1, ease: 'expo.inOut' }, '<')
    },
    { scope: root },
  )

  return (
    <div ref={root} className="fixed inset-0 z-[100] overflow-hidden" aria-hidden="true">
      <div className="in-top absolute inset-x-0 top-0 h-1/2 bg-bg" />
      <div className="in-bot absolute inset-x-0 bottom-0 h-1/2 bg-bg" />
      <div className="in-content absolute inset-0 flex flex-col items-center justify-center gap-6">
        <LogoMark size={64} className="in-logo drop-shadow-[0_0_28px_rgba(52,211,153,0.35)]" />
        <div className="overflow-hidden">
          <div className="flex gap-3 font-display text-3xl font-semibold tracking-tight sm:text-4xl">
            {['IPD', 'Trading', 'Desk'].map((w) => (
              <span key={w} className="in-word inline-block">
                {w}
              </span>
            ))}
          </div>
        </div>
        <div className="w-56">
          <div className="h-px w-full bg-white/10">
            <div className="in-line h-px origin-left bg-accent" />
          </div>
          <div className="mt-3 flex justify-between font-mono text-xs tracking-widest text-dim">
            <span>LOADING ZONES</span>
            <span ref={count}>000</span>
          </div>
        </div>
      </div>
    </div>
  )
}
