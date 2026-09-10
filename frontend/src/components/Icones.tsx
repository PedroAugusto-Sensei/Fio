interface Props {
  size?: number;
  className?: string;
}

/** A marca do Fio: um fio que sobe, desce e continua. */
export function Onda({ size = 24, className }: Props) {
  return (
    <svg
      width={size}
      height={size * 0.62}
      viewBox="0 0 40 25"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <path
        d="M5 16C7.5 16 9.5 4.5 17 4.5C24.5 4.5 26.5 20 33 20"
        stroke="var(--acento)"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <circle cx="5" cy="16" r="3.6" fill="var(--acento)" />
      <circle cx="33" cy="20" r="3.6" fill="var(--acento)" />
    </svg>
  );
}

export function Cadeado({ size = 12 }: Props) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <rect x="2.5" y="6" width="9" height="6.5" rx="1.4" stroke="currentColor" strokeWidth="1.2" />
      <path d="M4.6 6V4.4a2.4 2.4 0 0 1 4.8 0V6" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

export function Envelope({ size = 14 }: Props) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <rect x="1.5" y="3.5" width="13" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.2" />
      <path d="M2 4.5l6 4.2 6-4.2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  );
}

export function Lupa({ size = 14 }: Props) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.3" />
      <path d="M10.5 10.5L14 14" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

export function Papel({ size = 14 }: Props) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M4 1.5h5l3 3v10H4z"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      <path d="M9 1.5v3.2h3" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
    </svg>
  );
}

export function Olho({ size = 16, aberto = true }: Props & { aberto?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path
        d="M1.5 9S4.5 4 9 4s7.5 5 7.5 5-3 5-7.5 5S1.5 9 1.5 9z"
        stroke="currentColor"
        strokeWidth="1.2"
      />
      <circle cx="9" cy="9" r="2.1" stroke="currentColor" strokeWidth="1.2" />
      {!aberto && (
        <path d="M3 15L15 3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
      )}
    </svg>
  );
}
