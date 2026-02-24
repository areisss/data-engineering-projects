import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from './App';

const mockRemove = jest.fn().mockResolvedValue({});

jest.mock('@aws-amplify/ui-react', () => ({
  Authenticator: ({ children }) => children({ signOut: jest.fn(), user: { username: 'testuser' } }),
}));

jest.mock('aws-amplify/storage', () => ({
  uploadData: jest.fn(),
  list: jest.fn(() => Promise.resolve({ items: [] })),
  remove: (...args) => mockRemove(...args),
}));

// aws-amplify/auth is mapped to src/__mocks__/amplifyAuthMock.js via moduleNameMapper

// ---------------------------------------------------------------------------
// Upload & file list
// ---------------------------------------------------------------------------

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

test('delete button calls remove after confirmation', async () => {
  window.confirm = jest.fn().mockReturnValue(true);
  const { list } = require('aws-amplify/storage');
  list.mockImplementationOnce(() => Promise.resolve({
    items: [{ key: 'misc/test.pdf', size: 1024, lastModified: new Date() }],
  }));

  render(<App />);

  const deleteBtn = await screen.findByText(/delete/i);
  fireEvent.click(deleteBtn);

  await waitFor(() => {
    expect(window.confirm).toHaveBeenCalledWith('Delete "misc/test.pdf"?');
    expect(mockRemove).toHaveBeenCalledWith({ key: 'misc/test.pdf' });
  });
});

test('delete button does not remove when confirmation is cancelled', async () => {
  window.confirm = jest.fn().mockReturnValue(false);
  const { list } = require('aws-amplify/storage');
  list.mockImplementationOnce(() => Promise.resolve({
    items: [{ key: 'misc/test.pdf', size: 1024, lastModified: new Date() }],
  }));

  render(<App />);

  const deleteBtn = await screen.findByText(/delete/i);
  fireEvent.click(deleteBtn);

  expect(window.confirm).toHaveBeenCalled();
  expect(mockRemove).not.toHaveBeenCalled();
});

// ---------------------------------------------------------------------------
// Photo Gallery
// ---------------------------------------------------------------------------

const makePhoto = (id = 'abc123') => ({
  photo_id: id,
  filename: `${id}.jpg`,
  thumbnail_url: `https://s3.example.com/thumbnails/${id}.jpg`,
  original_url: `https://s3.example.com/originals/${id}.jpg`,
  width: 1920,
  height: 1080,
  uploaded_at: '2024-03-01T10:00:00Z',
});

describe('Photo Gallery', () => {
  beforeEach(() => {
    process.env.REACT_APP_PHOTOS_API_URL = 'https://api.example.com/photos';
    global.fetch = jest.fn().mockResolvedValue({
      json: () => Promise.resolve([]),
    });
  });

  afterEach(() => {
    delete process.env.REACT_APP_PHOTOS_API_URL;
    delete global.fetch;
  });

  test('renders gallery section heading', () => {
    render(<App />);
    expect(screen.getByText(/photo gallery/i)).toBeInTheDocument();
  });

  test('shows empty state when no photos are returned', async () => {
    render(<App />);
    expect(
      await screen.findByText(/no photos yet/i)
    ).toBeInTheDocument();
  });

  test('shows thumbnail for each photo returned by the API', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      json: () => Promise.resolve([makePhoto('sun01')]),
    });

    render(<App />);

    const img = await screen.findByAltText('sun01.jpg');
    expect(img).toHaveAttribute('src', 'https://s3.example.com/thumbnails/sun01.jpg');
  });

  test('shows filename in photo card', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      json: () => Promise.resolve([makePhoto('beach02')]),
    });

    render(<App />);

    expect(await screen.findByTitle('beach02.jpg')).toBeInTheDocument();
  });

  test('download link points to original URL', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      json: () => Promise.resolve([makePhoto('sky03')]),
    });

    render(<App />);

    const link = await screen.findByText('Download');
    expect(link).toHaveAttribute('href', 'https://s3.example.com/originals/sky03.jpg');
  });

  test('refresh button re-fetches photos', async () => {
    render(<App />);

    // Wait for initial fetch to settle
    await screen.findByText(/no photos yet/i);

    fireEvent.click(screen.getByRole('button', { name: /refresh/i }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledTimes(2);
    });
  });
});
