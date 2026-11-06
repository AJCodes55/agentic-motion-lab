const labels = {
  idle: 'Not started',
  pending: 'Pending',
  running: 'Running',
  complete: 'Complete',
  skipped: 'Skipped',
  failed: 'Failed',
} as const;

export default function StageStatus({ status }: { status: string }) {
  const state = Object.hasOwn(labels, status) ? status as keyof typeof labels : 'pending';
  return <span className="stage-status" data-state={state}>
    <span className="stage-indicator" aria-hidden="true" />
    {labels[state]}
  </span>;
}
