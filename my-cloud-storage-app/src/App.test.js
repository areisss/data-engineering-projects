import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from './App';

const mockRemove = jest.fn().mockResolvedValue({});

jest.mock('@aws-amplify/ui-react', () => ({
  Authenticator: ({ children }) => children({ signOut: jest.fn(), user: { username: 'testuser' } }),
}));

jest.mock('aws-amplify/storage', () => ({
  uploadData: jest.fn(),
  list: jest.fn().mockResolvedValue({ items: [] }),
  remove: (...args) => mockRemove(...args),
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

test('delete button calls remove with the file key', async () => {
  const { list } = require('aws-amplify/storage');
  list.mockResolvedValueOnce({
    items: [{ key: 'misc/test.pdf', size: 1024, lastModified: new Date() }],
  });

  render(<App />);

  const deleteBtn = await screen.findByText(/delete/i);
  fireEvent.click(deleteBtn);

  await waitFor(() => {
    expect(mockRemove).toHaveBeenCalledWith({ key: 'misc/test.pdf' });
  });
});
