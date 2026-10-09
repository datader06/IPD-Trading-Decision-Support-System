/** Brand mark: two candles standing on a translucent zone band, inside a glass tile. Drawn on a 32px grid with optical
 *  spacing (wicks 1.2px, bodies 5px, one radius family) rather than an icon-font glyph. */
export default function LogoMark({ size = 28, className = '' }: { size?: number; className?: string }) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} className={className} aria-hidden="true">
      <defs>
        <linearGradient id="lm-up" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#8af0c6" />
          <stop offset="1" stopColor="#10b981" />
        </linearGradient>
        <linearGradient id="lm-tile" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffffff" stopOpacity="0.14" />
          <stop offset="1" stopColor="#ffffff" stopOpacity="0.03" />
        </linearGradient>
      </defs>
      <rect x="0.75" y="0.75" width="30.5" height="30.5" rx="9.5" fill="url(#lm-tile)" stroke="#ffffff" strokeOpacity="0.16" strokeWidth="1" />
      <rect x="4.5" y="18.5" width="23" height="5.5" rx="2" fill="#34d399" fillOpacity="0.22" stroke="#34d399" strokeOpacity="0.5" strokeWidth="0.75" />
      <path d="M11 7.5v17M21 5.5v13" stroke="#ffffff" strokeOpacity="0.55" strokeWidth="1.2" strokeLinecap="round" />
      <rect x="8.5" y="11.5" width="5" height="9" rx="1.4" fill="#fb7185" />
      <rect x="18.5" y="8.5" width="5" height="8.5" rx="1.4" fill="url(#lm-up)" />
    </svg>
  )
}
