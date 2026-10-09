import { useGSAP } from '@gsap/react'
import { ArrowRight, Crosshair, Stack, Target } from '@phosphor-icons/react'
import gsap from 'gsap'
import { SplitText as GsapSplit } from 'gsap/SplitText'
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { Link } from 'react-router-dom'
import Intro from '../components/Intro'
import Nav from '../components/Nav'
import ZoneArt from '../components/ZoneArt'
import CountUp from '../components/reactbits/CountUp'
import DotGrid from '../components/reactbits/DotGrid'
import LightRays from '../components/reactbits/LightRays'
import ShinyText from '../components/reactbits/ShinyText'
import SpotlightCard from '../components/reactbits/SpotlightCard'
import SplitText from '../components/reactbits/SplitText'
import { prefersReducedMotion } from '../lib/motion'

gsap.registerPlugin(GsapSplit)

const STEPS = [
  {
    icon: Stack,
    title: 'Find the daily zone',
    body: 'A quiet base followed by a strong departure marks where large orders were absorbed. The higher timeframe sets the area that matters.',
  },
  {
    icon: Crosshair,
    title: 'Match a 15-minute zone inside it',
    body: 'A lower-timeframe zone must overlap the daily one by at least 30 percent. That is what narrows the entry and the risk.',
  },
  {
    icon: Target,
    title: 'Size it, then let it play out',
    body: 'Entry at the near edge, stop at the far edge, target at two times the risk. Shares are capped so the planned loss never exceeds Rs 1,000.',
  },
]

const FACTS: { to: number; prefix?: string; suffix?: string; label: string; note: string }[] = [
  { to: 503, label: 'NSE tickers scanned', note: 'The legacy live universe, minus one Kite cannot list.' },
  { to: 3, label: 'timeframe combos', note: 'Daily + 15m, weekly + 60m, monthly + daily.' },
  { to: 2, suffix: ':1', label: 'reward to risk', note: 'Fixed target on every trade, no time exit.' },
  { to: 1000, prefix: 'Rs ', label: 'max loss per trade', note: 'Position size is derived from the stop distance.' },
]

const TICKER = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'SBIN', 'ITC', 'LT', 'BHARTIARTL', 'HINDUNILVR', 'AXISBANK', 'MARUTI', 'SUNPHARMA', 'TITAN', 'NTPC']

const STATEMENT =
  'Every exit is replayed candle by candle. Fifteen minutes first, one minute when a bar cannot decide. Nothing ambiguous is quietly counted as a win.'

const INTRO_KEY = 'ipd-intro-seen'
const introWanted = () => {
  if (prefersReducedMotion()) return false
  try {
    return sessionStorage.getItem(INTRO_KEY) !== '1'
  } catch {
    return true
  }
}

export default function Landing() {
  const root = useRef<HTMLDivElement>(null)
  const heroRef = useRef<HTMLElement>(null)
  const [showIntro, setShowIntro] = useState(introWanted)
  const [ready, setReady] = useState(!showIntro)

  // Hold the page still while the opener plays.
  useEffect(() => {
    if (!showIntro) return
    const prev = document.documentElement.style.overflow
    document.documentElement.style.overflow = 'hidden'
    return () => {
      document.documentElement.style.overflow = prev
    }
  }, [showIntro])

  /* ---- hero: runs once the shutters start to open ---- */
  useGSAP(
    () => {
      if (!ready) return
      const mm = gsap.matchMedia()
      mm.add('(prefers-reduced-motion: no-preference)', () => {
        const split = new GsapSplit('.hero-h1 .line', { type: 'words,chars', mask: 'chars' })
        const tl = gsap.timeline({ defaults: { ease: 'expo.out' }, delay: showIntro ? 0.15 : 0.05 })
        tl.fromTo('.hero-glow', { opacity: 0 }, { opacity: 1, duration: 1.6, ease: 'power2.out' }, 0)
          .fromTo('.hero-badge', { opacity: 0, y: -16, filter: 'blur(6px)' }, { opacity: 1, y: 0, filter: 'blur(0px)', duration: 0.9 }, 0.1)
          .fromTo(split.chars, { yPercent: 125, rotate: 8, opacity: 0 }, { yPercent: 0, rotate: 0, opacity: 1, duration: 1.2, stagger: 0.028 }, 0.2)
          .fromTo('.hero-sub, .hero-cta', { opacity: 0, y: 26, filter: 'blur(8px)' }, { opacity: 1, y: 0, filter: 'blur(0px)', duration: 1, stagger: 0.12 }, 0.75)
          .fromTo('.hero-stage', { opacity: 0, y: 70, rotationX: 22, scale: 0.92 }, { opacity: 1, y: 0, rotationX: 0, scale: 1, duration: 1.5 }, 0.35)
          .from('.hero-stage .cndl', { scaleY: 0, opacity: 0, duration: 0.6, stagger: 0.035, ease: 'power3.out' }, 0.9)
          .from('.hero-stage .zone-htf', { opacity: 0, scaleY: 0.2, duration: 0.8, ease: 'power3.out' }, '-=0.5')
          .from('.hero-stage .zone-ltf', { opacity: 0, scaleX: 0, duration: 0.7, ease: 'power3.out' }, '-=0.5')
          .from('.hero-stage [class^="lvl-"]', { opacity: 0, scaleX: 0, duration: 0.6, stagger: 0.14, ease: 'power3.out' }, '-=0.35')
          .fromTo('.hero-chip', { opacity: 0, scale: 0.6, y: 14 }, { opacity: 1, scale: 1, y: 0, duration: 0.8, stagger: 0.12, ease: 'back.out(1.7)' }, '-=0.4')
          .fromTo('.hero-ticker', { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 1 }, '-=0.6')

        // Idle float on the glass chips.
        gsap.utils.toArray<HTMLElement>('.hero-chip-float').forEach((el, i) => {
          gsap.to(el, { y: i % 2 ? 9 : -9, duration: 2.4 + i * 0.4, ease: 'sine.inOut', yoyo: true, repeat: -1 })
        })

        // Pointer parallax: the stage tilts, chips drift at their own depth, a soft light follows the cursor.
        const hero = heroRef.current
        if (!hero) return
        const stageRX = gsap.quickTo('.hero-tilt', 'rotationX', { duration: 0.8, ease: 'power3.out' })
        const stageRY = gsap.quickTo('.hero-tilt', 'rotationY', { duration: 0.8, ease: 'power3.out' })
        const glowX = gsap.quickTo('.hero-follow', 'x', { duration: 0.9, ease: 'power3.out' })
        const glowY = gsap.quickTo('.hero-follow', 'y', { duration: 0.9, ease: 'power3.out' })
        const chips = gsap.utils.toArray<HTMLElement>('.hero-chip').map((el) => ({
          depth: parseFloat(el.dataset.depth ?? '1'),
          x: gsap.quickTo(el, 'x', { duration: 0.9, ease: 'power3.out' }),
          y: gsap.quickTo(el, 'y', { duration: 0.9, ease: 'power3.out' }),
        }))
        const onMove = (e: PointerEvent) => {
          const r = hero.getBoundingClientRect()
          const nx = (e.clientX - r.left) / r.width - 0.5
          const ny = (e.clientY - r.top) / r.height - 0.5
          stageRY(nx * 9)
          stageRX(-ny * 7)
          glowX(e.clientX - r.left - 300)
          glowY(e.clientY - r.top - 300)
          chips.forEach((c) => {
            c.x(nx * 34 * c.depth)
            c.y(ny * 24 * c.depth)
          })
        }
        hero.addEventListener('pointermove', onMove)
        return () => {
          hero.removeEventListener('pointermove', onMove)
          split.revert()
        }
      })
      return () => mm.revert()
    },
    { scope: root, dependencies: [ready] },
  )

  /* ---- sections below the hero ---- */
  useGSAP(
    () => {
      const mm = gsap.matchMedia()
      mm.add(
        { wide: '(min-width: 1024px)', ok: '(prefers-reduced-motion: no-preference)' },
        (ctx) => {
          const { wide, ok } = ctx.conditions as { wide: boolean; ok: boolean }
          if (!ok) return

          // Scroll-driven statement: words light up in sequence.
          gsap.fromTo(
            '.statement .word',
            { opacity: 0.14 },
            { opacity: 1, stagger: 0.1, ease: 'none', scrollTrigger: { trigger: '.statement', start: 'top 78%', end: 'bottom 52%', scrub: true } },
          )

          gsap.from('.fact', {
            opacity: 0,
            y: 40,
            scale: 0.96,
            duration: 0.9,
            stagger: 0.1,
            ease: 'expo.out',
            scrollTrigger: { trigger: '.facts', start: 'top 80%' },
          })

          gsap.utils.toArray<HTMLElement>('.parallax-slow').forEach((el) => {
            gsap.to(el, { yPercent: -12, ease: 'none', scrollTrigger: { trigger: el, scrub: true, start: 'top bottom', end: 'bottom top' } })
          })

          if (wide) {
            // Pinned walkthrough: one scrubbed timeline drives the steps and the chart together.
            gsap.set('.how .zone-htf, .how .zone-ltf, .how [class^="lvl-"]', { opacity: 0 })
            gsap.set('.step', { opacity: 0.28 })
            gsap.set('.step-0', { opacity: 1 })
            const tl = gsap.timeline({
              defaults: { ease: 'none' },
              scrollTrigger: { trigger: '.how', start: 'top top', end: '+=2400', pin: true, scrub: 0.7, anticipatePin: 1 },
            })
            tl.fromTo('.how .zone-htf', { opacity: 0, scaleY: 0.2 }, { opacity: 1, scaleY: 1, duration: 0.9 })
              .to('.step-0', { opacity: 0.28, duration: 0.3 }, '>0.4')
              .to('.step-1', { opacity: 1, duration: 0.3 }, '<')
              .fromTo('.how .zone-ltf', { opacity: 0, scaleX: 0 }, { opacity: 1, scaleX: 1, duration: 0.8 }, '<')
              .to('.step-1', { opacity: 0.28, duration: 0.3 }, '>0.5')
              .to('.step-2', { opacity: 1, duration: 0.3 }, '<')
              .fromTo('.how [class^="lvl-"]', { opacity: 0, scaleX: 0 }, { opacity: 1, scaleX: 1, duration: 0.8, stagger: 0.3 }, '<')
              .to({}, { duration: 0.6 })
          } else {
            // Narrow screens: no pin (the content is taller than the viewport); each step reveals as it scrolls in.
            gsap.utils.toArray<HTMLElement>('.step').forEach((el) => {
              gsap.from(el, { opacity: 0, y: 30, duration: 0.8, ease: 'expo.out', scrollTrigger: { trigger: el, start: 'top 88%' } })
            })
          }
        },
      )
      return () => mm.revert()
    },
    { scope: root },
  )

  // Magnetic pull on the primary button.
  const magnet = (e: ReactPointerEvent<HTMLElement>) => {
    if (prefersReducedMotion()) return
    const el = e.currentTarget
    const r = el.getBoundingClientRect()
    gsap.to(el, { x: (e.clientX - (r.left + r.width / 2)) * 0.28, y: (e.clientY - (r.top + r.height / 2)) * 0.4, duration: 0.4, ease: 'power3.out' })
  }
  const unmagnet = (e: ReactPointerEvent<HTMLElement>) => {
    gsap.to(e.currentTarget, { x: 0, y: 0, duration: 0.9, ease: 'elastic.out(1, 0.4)' })
  }

  return (
    <div ref={root}>
      {showIntro && (
        <Intro
          onReveal={() => {
            try {
              sessionStorage.setItem(INTRO_KEY, '1')
            } catch {
              /* private mode: the opener just plays again next visit */
            }
            setReady(true)
          }}
          onDone={() => {
            setShowIntro(false)
            requestAnimationFrame(() => import('gsap/ScrollTrigger').then((m) => m.ScrollTrigger.refresh()))
          }}
        />
      )}
      <div className="ambient" aria-hidden="true" />
      <Nav />

      {/* HERO */}
      <section ref={heroRef} className="relative isolate overflow-hidden">
        <div className="hero-glow absolute inset-0 -z-10" aria-hidden="true">
          <LightRays raysOrigin="top-left" raysColor="#34d399" raysSpeed={0.6} lightSpread={0.8} rayLength={1.7} followMouse mouseInfluence={0.06} fadeDistance={0.9} />
        </div>
        <div className="hero-follow pointer-events-none absolute left-0 top-0 -z-10 hidden h-[600px] w-[600px] rounded-full opacity-70 lg:block" aria-hidden="true"
          style={{ background: 'radial-gradient(closest-side, rgba(52,211,153,0.13), transparent)' }} />

        <div className="mx-auto grid min-h-[calc(100dvh-3.5rem)] max-w-[1400px] items-center gap-12 px-4 py-16 sm:px-6 lg:grid-cols-[1.08fr_0.92fr]">
          <div>
            <div className="hero-badge glass mb-7 inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 text-xs">
              <span className="relative flex h-1.5 w-1.5" aria-hidden="true">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-accent" />
              </span>
              <ShinyText text="NSE supply and demand research" speed={4} color="#8af0c6" shineColor="#ffffff" />
            </div>

            <h1 className="hero-h1 glow-text text-[clamp(2.7rem,5.4vw,5.2rem)] font-semibold leading-[1] tracking-[-0.035em]" aria-label="Trade the zones, not the noise.">
              <span className="line block pb-[0.08em]">Trade the zones,</span>
              <span className="line block pb-[0.08em] text-accent">not the noise.</span>
            </h1>

            <p className="hero-sub mt-7 max-w-[54ch] text-lg leading-relaxed text-dim">
              A research desk that matches daily and 15-minute demand and supply zones, then sizes every trade to a fixed Rs 1,000 risk. Built on a backtest engine
              that replays each exit candle by candle.
            </p>

            <div className="hero-cta mt-10 flex flex-wrap items-center gap-3">
              <Link
                to="/desk"
                onPointerMove={magnet}
                onPointerLeave={unmagnet}
                className="group relative inline-flex items-center gap-2 overflow-hidden rounded-xl bg-accent px-6 py-3.5 font-semibold text-on-accent shadow-[0_10px_40px_-8px_rgba(52,211,153,0.55)]"
              >
                <span className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/45 to-transparent transition-transform duration-700 group-hover:translate-x-full" aria-hidden="true" />
                <span className="relative">Open the desk</span>
                <ArrowRight size={18} weight="bold" className="relative transition-transform duration-300 group-hover:translate-x-1" aria-hidden="true" />
              </Link>
              <a href="#how" className="glass rounded-xl px-6 py-3.5 text-fg/90 transition-colors duration-200 hover:bg-white/[0.08]">
                How it works
              </a>
            </div>
          </div>

          <div className="relative [perspective:1400px]">
            <div className="hero-stage">
              <div className="hero-tilt relative [transform-style:preserve-3d]">
                <div className="glass rounded-2xl p-3 sm:p-5">
                  <div className="mb-3 flex items-center justify-between px-1 text-xs text-dim">
                    <span className="num tracking-widest">ILLUSTRATION</span>
                    <span className="flex gap-1.5" aria-hidden="true">
                      <i className="h-2 w-2 rounded-full bg-white/15" />
                      <i className="h-2 w-2 rounded-full bg-white/15" />
                      <i className="h-2 w-2 rounded-full bg-white/15" />
                    </span>
                  </div>
                  <ZoneArt className="h-auto w-full" />
                </div>
                <div className="hero-chip glass absolute -left-4 top-[18%] hidden rounded-xl px-3.5 py-2.5 text-xs sm:block" data-depth="1.4">
                  <div className="hero-chip-float">
                    <div className="num text-xs tracking-widest text-dim">RISK / TRADE</div>
                    <div className="num mt-0.5 text-base text-fg">Rs 1,000</div>
                  </div>
                </div>
                <div className="hero-chip glass absolute -bottom-5 right-6 hidden rounded-xl px-3.5 py-2.5 text-xs sm:block" data-depth="1.9">
                  <div className="hero-chip-float">
                    <div className="num text-xs tracking-widest text-dim">REWARD : RISK</div>
                    <div className="num mt-0.5 text-base text-accent">2 : 1</div>
                  </div>
                </div>
                <div className="hero-chip glass absolute -right-3 top-[8%] hidden rounded-xl px-3.5 py-2.5 text-xs md:block" data-depth="0.9">
                  <div className="hero-chip-float">
                    <div className="num text-xs tracking-widest text-dim">ZONE OVERLAP</div>
                    <div className="num mt-0.5 text-base text-fg">&ge; 30%</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* TICKER */}
        <div className="hero-ticker relative border-y border-white/[0.07] bg-white/[0.02] py-3.5 backdrop-blur-md [mask-image:linear-gradient(90deg,transparent,#000_12%,#000_88%,transparent)]" aria-hidden="true">
          <div className="flex w-max animate-[marquee_46s_linear_infinite] gap-10 whitespace-nowrap font-mono text-xs tracking-[0.2em] text-dim">
            {[0, 1].map((k) => (
              <div key={k} className="flex gap-10">
                {TICKER.map((t) => (
                  <span key={`${k}-${t}`} className="flex items-center gap-10">
                    {t}
                    <i className="h-1 w-1 rounded-full bg-accent/60" />
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* STATEMENT */}
      <section className="statement mx-auto max-w-[1100px] px-4 py-32 sm:px-6 sm:py-44">
        <p className="font-display text-[clamp(1.7rem,4.2vw,3.4rem)] font-medium leading-[1.12] tracking-[-0.025em]">
          {STATEMENT.split(' ').map((w, i) => (
            <span key={i} className="word inline-block">
              {w}&nbsp;
            </span>
          ))}
        </p>
      </section>

      {/* PINNED WALKTHROUGH */}
      <section id="how" className="how relative isolate flex min-h-dvh items-center overflow-hidden border-y border-white/[0.06]">
        <div className="mx-auto grid w-full max-w-[1400px] items-center gap-12 px-4 py-20 sm:px-6 lg:grid-cols-[0.9fr_1.1fr]">
          <div>
            <p className="num mb-3 text-xs uppercase tracking-[0.22em] text-accent">How a trade is built</p>
            <SplitText
              text="Three rules, applied in order."
              tag="h2"
              splitType="words"
              delay={60}
              duration={0.9}
              textAlign="left"
              rootMargin="0px"
              className="mb-12 max-w-[16ch] text-4xl font-semibold leading-[1.05] tracking-[-0.03em] sm:text-5xl"
            />
            <ol className="space-y-9">
              {STEPS.map(({ icon: Icon, title, body }, i) => (
                <li key={title} className={`step step-${i} flex gap-4`}>
                  <span className="glass mt-0.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-accent">
                    <Icon size={22} weight="duotone" aria-hidden="true" />
                  </span>
                  <div>
                    <h3 className="text-xl font-semibold tracking-tight">
                      <span className="num mr-2 text-sm text-dim">0{i + 1}</span>
                      {title}
                    </h3>
                    <p className="mt-1.5 max-w-[50ch] leading-relaxed text-dim">{body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
          <div className="glass rounded-2xl p-3 sm:p-5">
            <ZoneArt className="h-auto w-full" />
          </div>
        </div>
      </section>

      {/* NUMBERS */}
      <section className="facts relative mx-auto max-w-[1400px] px-4 py-28 sm:px-6">
        <SplitText
          text="Fixed rules, so results can be compared."
          tag="h2"
          splitType="words"
          delay={55}
          duration={0.9}
          textAlign="left"
          rootMargin="0px"
          className="mb-12 max-w-[18ch] text-4xl font-semibold leading-[1.05] tracking-[-0.03em] sm:text-5xl"
        />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FACTS.map((f) => (
            <SpotlightCard key={f.label} className="fact glass !rounded-2xl !p-6" spotlightColor="#34d399" intensity={0.14}>
              <div className="num text-4xl font-medium tracking-tight">
                {f.prefix}
                <CountUp to={f.to} duration={1.8} separator="," />
                {f.suffix}
              </div>
              <div className="mt-3 font-semibold">{f.label}</div>
              <p className="mt-1 text-sm leading-relaxed text-dim">{f.note}</p>
            </SpotlightCard>
          ))}
        </div>
      </section>

      {/* CLOSING */}
      <section className="relative isolate overflow-hidden border-t border-white/[0.06]">
        <div className="absolute inset-0 -z-10 opacity-60" aria-hidden="true">
          <DotGrid dotSize={3} gap={28} baseColor="#103423" activeColor="#34d399" proximity={110} shockRadius={180} shockStrength={3} />
        </div>
        <div className="parallax-slow mx-auto max-w-[1400px] px-4 py-32 sm:px-6">
          <h2 className="max-w-[18ch] text-5xl font-semibold leading-[1.02] tracking-[-0.035em] sm:text-6xl">
            Check the levels <span className="text-accent">before</span> you click.
          </h2>
          <p className="mt-5 max-w-[58ch] text-dim">Load any NSE stock, set an entry and a stop, and see the target, share count and worst-case loss on the chart.</p>
          <Link
            to="/desk"
            onPointerMove={magnet}
            onPointerLeave={unmagnet}
            className="mt-9 inline-flex items-center gap-2 rounded-xl bg-accent px-6 py-3.5 font-semibold text-on-accent shadow-[0_10px_40px_-8px_rgba(52,211,153,0.55)]"
          >
            Open the desk <ArrowRight size={18} weight="bold" aria-hidden="true" />
          </Link>
          <p className="mt-20 max-w-[80ch] text-xs leading-relaxed text-dim">
            Research tool, not investment advice. Backtest figures are gross of brokerage, tax and slippage, and the baselines are not yet confirmed. Past results do
            not predict future results.
          </p>
        </div>
      </section>
    </div>
  )
}
