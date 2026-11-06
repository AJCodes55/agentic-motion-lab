import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import WheelButton from '../components/wheel-button';

test('only the clicked asynchronous button spins until its action finishes', async () => {
  let finish!: () => void;
  const action = vi.fn(() => new Promise<void>(resolve => { finish = resolve; }));
  render(<><WheelButton onAction={action}>Open report</WheelButton><WheelButton onAction={action}>Other report</WheelButton></>);
  const selected = screen.getByRole('button', {name:'Open report'});
  fireEvent.click(selected);
  expect(selected).toBeEnabled();
  expect(selected).toHaveAttribute('aria-busy','true');
  expect(selected.querySelector('svg')).toHaveAttribute('data-active','true');
  expect(screen.getByRole('button', {name:'Other report'}).querySelector('svg')).toHaveAttribute('data-active','false');
  finish();
  await waitFor(() => expect(selected).toHaveAttribute('aria-busy','false'));
  expect(selected.querySelector('svg')).toHaveAttribute('data-active','false');
});

test('preserves native form submission and ignores disabled clicks', () => {
  const submit = vi.fn(event => event.preventDefault());
  const action = vi.fn();
  render(<form onSubmit={submit}><WheelButton type="submit" busy={false}>Submit</WheelButton><WheelButton disabled onAction={action}>Unavailable</WheelButton></form>);
  fireEvent.click(screen.getByRole('button', {name:'Submit'}));
  expect(submit).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole('button', {name:'Unavailable'}));
  expect(action).not.toHaveBeenCalled();
  expect(screen.getByRole('button', {name:'Unavailable'}).querySelector('svg')).toHaveAttribute('data-active','false');
});
