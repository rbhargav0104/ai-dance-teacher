/**
 * Illustrative line figure with motion arcs. Purely decorative: it is not pose output and
 * carries no scores. Real skeletons come from MediaPipe landmarks in the studio.
 */
export function HeroFigure() {
  return (
    <svg viewBox="0 0 400 480" className="h-full w-full" aria-hidden focusable="false">
      <defs>
        <radialGradient id="glow" cx="50%" cy="40%" r="60%">
          <stop offset="0%" stopColor="var(--color-lime)" stopOpacity="0.18" />
          <stop offset="100%" stopColor="var(--color-lime)" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="trail" x1="0" x2="1">
          <stop offset="0%" stopColor="var(--color-lime)" stopOpacity="0" />
          <stop offset="100%" stopColor="var(--color-lime)" stopOpacity="0.9" />
        </linearGradient>
      </defs>
      <rect width="400" height="480" fill="url(#glow)" />
      {/* floor line */}
      <line x1="40" x2="360" y1="430" y2="430" stroke="var(--color-line)" strokeWidth="1" />
      {/* movement arcs */}
      <g fill="none" strokeLinecap="round">
        <path d="M70 150 C 120 60, 230 50, 300 120" stroke="url(#trail)" strokeWidth="2.5" strokeDasharray="2 9" />
        <path d="M120 330 C 160 400, 250 410, 300 360" stroke="url(#trail)" strokeWidth="2" strokeDasharray="2 9" opacity="0.7" />
        <path d="M300 120 C 330 160, 335 200, 320 240" stroke="var(--color-track)" strokeWidth="1.5" opacity="0.45" />
      </g>
      <g className="origin-center animate-drift">
        <g stroke="var(--color-ink)" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none">
          {/* torso */}
          <path d="M200 150 L 196 250" />
          {/* shoulders and hips */}
          <path d="M168 160 L 230 154" />
          <path d="M178 252 L 214 248" />
          {/* raised right arm */}
          <path d="M230 154 L 268 118 L 300 120" />
          {/* left arm out */}
          <path d="M168 160 L 128 186 L 92 168" />
          {/* legs: one planted, one extended */}
          <path d="M178 252 L 162 330 L 150 420" />
          <path d="M214 248 L 252 316 L 300 360" />
        </g>
        <g fill="var(--color-lime)">
          {[
            [200, 112, 15],
            [168, 160, 6],
            [230, 154, 6],
            [268, 118, 6],
            [300, 120, 7],
            [128, 186, 6],
            [92, 168, 7],
            [178, 252, 6],
            [214, 248, 6],
            [162, 330, 6],
            [150, 420, 7],
            [252, 316, 6],
            [300, 360, 7],
          ].map(([cx, cy, r]) => (
            <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r={r} />
          ))}
        </g>
      </g>
    </svg>
  );
}
