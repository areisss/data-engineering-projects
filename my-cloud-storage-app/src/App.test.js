import { render, screen } from '@testing-library/react';
import App from './App';

jest.mock('@aws-amplify/ui-react', () => ({
  Authenticator: ({ children }) => children({ signOut: jest.fn(), user: { username: 'testuser' } }),
}));

jest.mock('aws-amplify/storage', () => ({
  uploadData: jest.fn(),
  list: jest.fn().mockResolvedValue({ items: [] }),
}));

test('renders upload form', () => {
  render(<App />);
  expect(screen.getByText(/welcome, testuser/i)).toBeInTheDocument();
  expect(screen.getByText(/upload a file/i)).toBeInTheDocument();
  expect(screen.getByText(/drag & drop/i)).toBeInTheDocument();
  expect(screen.getByText(/upload to cloud/i)).toBeInTheDocument();
});

test('renders uploaded files section', () => {
  render(<App />);
  expect(screen.getByText(/uploaded files/i)).toBeInTheDocument();
  expect(screen.getByText(/no files uploaded yet/i)).toBeInTheDocument();
});
