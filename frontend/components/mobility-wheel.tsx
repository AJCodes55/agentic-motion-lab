export default function MobilityWheel({ active, variant = 'header' }: { active: boolean; variant?: 'header' | 'page' | 'button' }) {
  const compact = variant === 'button';
  return (
    <svg className={`mobility-wheel mobility-wheel--${variant}`} data-testid={variant === 'header' ? 'mobility-wheel' : `mobility-wheel-${variant}`} data-active={active}
      aria-hidden="true" focusable="false" viewBox="0 0 400 400" fill="none">
      <circle cx="200" cy="200" r="184" strokeWidth={compact ? 22 : 5} />
      {!compact && <circle cx="200" cy="200" r="174" strokeWidth="1" />}
      {Array.from({ length: compact ? 8 : 24 }, (_, index) => (
        <path key={index} d="M200 26 211 200" strokeWidth={compact ? 12 : 1}
          transform={`rotate(${index * (compact ? 45 : 15)} 200 200)`} />
      ))}
      <circle cx="200" cy="200" r="12" strokeWidth={compact ? 16 : 3} />
      <circle cx="200" cy="200" r="4" strokeWidth="2" />
      <path d="M200 12v9" strokeWidth="5" strokeLinecap="round" />
    </svg>
  );
}
