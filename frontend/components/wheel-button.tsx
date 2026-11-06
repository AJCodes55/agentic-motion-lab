'use client';

import { useEffect, useRef, useState, type ButtonHTMLAttributes, type MouseEvent } from 'react';
import MobilityWheel from './mobility-wheel';

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  busy?: boolean;
  onAction?: () => Promise<void>;
};

export default function WheelButton({ children, className = '', busy, disabled, onClick, onAction, ...props }: Props) {
  const [pending, setPending] = useState(false);
  const [clicked, setClicked] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  const active = busy ?? (pending || clicked);

  async function handleClick(event: MouseEvent<HTMLButtonElement>) {
    onClick?.(event);
    if (event.defaultPrevented) return;
    if (onAction) {
      setPending(true);
      try { await onAction(); }
      finally { setPending(false); }
    } else if (busy === undefined) {
      if (timer.current) clearTimeout(timer.current);
      setClicked(true);
      timer.current = setTimeout(() => setClicked(false), 600);
    }
  }

  return <button {...props} className={`wheel-action ${className}`} disabled={disabled}
    aria-busy={busy ?? pending} onClick={handleClick}>
    <span>{children}</span><MobilityWheel variant="button" active={active} />
  </button>;
}
