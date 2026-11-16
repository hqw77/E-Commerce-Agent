import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { StatusTag } from './Common';

describe('StatusTag', () => {
  it('renders the backend status verbatim', () => {
    render(<StatusTag status="PENDING_REVIEW" />);
    expect(screen.getByText('PENDING_REVIEW')).toBeInTheDocument();
  });
});
