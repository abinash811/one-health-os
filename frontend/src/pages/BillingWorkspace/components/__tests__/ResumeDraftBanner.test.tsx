import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ResumeDraftBanner from '../ResumeDraftBanner';

const DRAFT = { customerName: 'Asha', customerPhone: '', doctorName: '', items: [{}, {}], draftNumber: 1, savedAt: Date.now() };

describe('ResumeDraftBanner', () => {
  it('says what is waiting and lets you resume or discard', async () => {
    const onResume = jest.fn();
    const onDiscard = jest.fn();
    render(<ResumeDraftBanner draft={DRAFT} onResume={onResume} onDiscard={onDiscard} />);
    expect(screen.getByTestId('resume-draft-banner')).toHaveTextContent('unfinished bill for Asha · 2 items');
    await userEvent.click(screen.getByTestId('resume-draft-btn'));
    await userEvent.click(screen.getByTestId('discard-draft-btn'));
    expect(onResume).toHaveBeenCalledTimes(1);
    expect(onDiscard).toHaveBeenCalledTimes(1);
  });

  it('leaves the name out for a walk-in and says "1 item"', () => {
    render(<ResumeDraftBanner draft={{ ...DRAFT, customerName: 'Walk-in Customer', items: [{}] }}
      onResume={jest.fn()} onDiscard={jest.fn()} />);
    expect(screen.getByTestId('resume-draft-banner')).toHaveTextContent('You have an unfinished bill · 1 item');
  });
});
