import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from './App';
import HomePage from './pages/HomePage';
import LibraryPage from './pages/LibraryPage';
import PhotosPage from './pages/PhotosPage';
import WhatsAppPage from './pages/WhatsAppPage';
import OtherFilesPage from './pages/OtherFilesPage';

// ---------------------------------------------------------------------------
// Shared mocks
// ---------------------------------------------------------------------------

const mockRemove = jest.fn().mockResolvedValue({});

jest.mock('@aws-amplify/ui-react', () => ({
  Authenticator: ({ children }) =>
    children({ signOut: jest.fn(), user: { username: 'testuser' } }),
}));

jest.mock('aws-amplify/storage', () => ({
  uploadData: jest.fn(),
  list: jest.fn(() => Promise.resolve({ items: [] })),
  getUrl: jest.fn(() => Promise.resolve({ url: new URL('https://s3.example.com/file.zip') })),
  remove: (...args) => mockRemove(...args),
}));

// aws-amplify/auth mapped to src/__mocks__/amplifyAuthMock.js

// Helpers -------------------------------------------------------------------

const renderHomePage = (props = {}) =>
  render(
    <MemoryRouter>
      <HomePage signOut={jest.fn()} user={{ username: 'testuser' }} {...props} />
    </MemoryRouter>
  );

const renderLibraryPage = () =>
  render(
    <MemoryRouter>
      <LibraryPage />
    </MemoryRouter>
  );

const renderPhotosPage = () =>
  render(
    <MemoryRouter>
      <PhotosPage />
    </MemoryRouter>
  );

const renderWhatsAppPage = () =>
  render(
    <MemoryRouter>
      <WhatsAppPage />
    </MemoryRouter>
  );

const renderOtherFilesPage = () =>
  render(
    <MemoryRouter>
      <OtherFilesPage />
    </MemoryRouter>
  );

const renderApp = (initialPath = '/') =>
  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <App />
    </MemoryRouter>
  );

// ---------------------------------------------------------------------------
// App routing
// ---------------------------------------------------------------------------

describe('App routing', () => {
  test('renders home page at /', () => {
    renderApp('/');
    expect(screen.getByText('Artur Carvalho Reis')).toBeInTheDocument();
  });

  test('renders library page at /library', () => {
    renderApp('/library');
    expect(screen.getByRole('heading', { name: /library/i })).toBeInTheDocument();
  });

  test('renders photos page at /library/photos', async () => {
    process.env.REACT_APP_PHOTOS_API_URL = 'https://api.example.com/photos';
    global.fetch = jest.fn().mockResolvedValue({ json: () => Promise.resolve([]) });
    renderApp('/library/photos');
    expect(screen.getByRole('heading', { name: /photos/i })).toBeInTheDocument();
    delete process.env.REACT_APP_PHOTOS_API_URL;
    delete global.fetch;
  });

  test('renders whatsapp page at /library/whatsapp', async () => {
    process.env.REACT_APP_CHATS_API_URL = 'https://api.example.com/chats';
    global.fetch = jest.fn().mockResolvedValue({ json: () => Promise.resolve([]) });
    renderApp('/library/whatsapp');
    expect(screen.getByRole('heading', { name: /whatsapp messages/i })).toBeInTheDocument();
    delete process.env.REACT_APP_CHATS_API_URL;
    delete global.fetch;
  });

  test('renders other files page at /library/files', async () => {
    renderApp('/library/files');
    expect(screen.getByRole('heading', { name: /other files/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// HomePage — intro section
// ---------------------------------------------------------------------------

describe('HomePage intro', () => {
  test('shows name prominently', () => {
    renderHomePage();
    expect(screen.getByRole('heading', { name: 'Artur Carvalho Reis' })).toBeInTheDocument();
  });

  test('shows project description', () => {
    renderHomePage();
    expect(screen.getByText(/personal data engineering project/i)).toBeInTheDocument();
  });

  test('shows Open Library button', () => {
    renderHomePage();
    expect(screen.getByRole('button', { name: /open library/i })).toBeInTheDocument();
  });

  test('Open Library button navigates to /library', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole('button', { name: /open library/i }));
    expect(await screen.findByRole('heading', { name: /library/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// HomePage — upload section
// ---------------------------------------------------------------------------

describe('HomePage upload', () => {
  test('renders upload form', () => {
    renderHomePage();
    expect(screen.getByText(/upload a file/i)).toBeInTheDocument();
    expect(screen.getByText(/drag & drop/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /upload to cloud/i })).toBeInTheDocument();
  });

  test('does NOT show photo gallery on home page', () => {
    renderHomePage();
    expect(screen.queryByText(/photo gallery/i)).not.toBeInTheDocument();
  });

  test('does NOT show uploaded files table on home page', () => {
    renderHomePage();
    expect(screen.queryByText(/uploaded files/i)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// LibraryPage
// ---------------------------------------------------------------------------

describe('LibraryPage', () => {
  test('renders Library heading', () => {
    renderLibraryPage();
    expect(screen.getByRole('heading', { name: /library/i })).toBeInTheDocument();
  });

  test('shows Photos button', () => {
    renderLibraryPage();
    expect(screen.getByRole('button', { name: /photos/i })).toBeInTheDocument();
  });

  test('shows WhatsApp Messages button', () => {
    renderLibraryPage();
    expect(screen.getByRole('button', { name: /whatsapp messages/i })).toBeInTheDocument();
  });

  test('shows Other Files button', () => {
    renderLibraryPage();
    expect(screen.getByRole('button', { name: /other files/i })).toBeInTheDocument();
  });

  test('shows Back button', () => {
    renderLibraryPage();
    expect(screen.getByRole('button', { name: /back/i })).toBeInTheDocument();
  });

  test('Back button navigates to home page', async () => {
    render(
      <MemoryRouter initialEntries={['/library']}>
        <App />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole('button', { name: /back/i }));
    expect(await screen.findByText('Artur Carvalho Reis')).toBeInTheDocument();
  });

  test('Photos button navigates to /library/photos', async () => {
    process.env.REACT_APP_PHOTOS_API_URL = 'https://api.example.com/photos';
    global.fetch = jest.fn().mockResolvedValue({ json: () => Promise.resolve([]) });
    render(
      <MemoryRouter initialEntries={['/library']}>
        <App />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole('button', { name: /photos/i }));
    expect(await screen.findByRole('heading', { name: /^photos$/i })).toBeInTheDocument();
    delete process.env.REACT_APP_PHOTOS_API_URL;
    delete global.fetch;
  });

  test('WhatsApp Messages button navigates to /library/whatsapp', async () => {
    process.env.REACT_APP_CHATS_API_URL = 'https://api.example.com/chats';
    global.fetch = jest.fn().mockResolvedValue({ json: () => Promise.resolve([]) });
    render(
      <MemoryRouter initialEntries={['/library']}>
        <App />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole('button', { name: /whatsapp messages/i }));
    expect(await screen.findByRole('heading', { name: /whatsapp messages/i })).toBeInTheDocument();
    delete process.env.REACT_APP_CHATS_API_URL;
    delete global.fetch;
  });

  test('Other Files button navigates to /library/files', async () => {
    render(
      <MemoryRouter initialEntries={['/library']}>
        <App />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole('button', { name: /other files/i }));
    expect(await screen.findByRole('heading', { name: /other files/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// OtherFilesPage
// ---------------------------------------------------------------------------

import { list, getUrl } from 'aws-amplify/storage';

describe('OtherFilesPage', () => {
  beforeEach(() => {
    list.mockResolvedValue({ items: [] });
    getUrl.mockResolvedValue({ url: new URL('https://s3.example.com/file.zip') });
  });

  test('renders Other Files heading', () => {
    renderOtherFilesPage();
    expect(screen.getByRole('heading', { name: /other files/i })).toBeInTheDocument();
  });

  test('shows empty state when no files returned', async () => {
    renderOtherFilesPage();
    expect(await screen.findByText(/no files found/i)).toBeInTheDocument();
  });

  test('shows file rows when files returned', async () => {
    list
      .mockResolvedValueOnce({ items: [{ key: 'misc/report.pdf', size: 2048, lastModified: '2024-03-01T10:00:00Z' }] })
      .mockResolvedValueOnce({ items: [] });
    renderOtherFilesPage();
    expect(await screen.findByText('report.pdf')).toBeInTheDocument();
    expect(screen.getByText('2.0 KB')).toBeInTheDocument();
  });

  test('renders a Download link for each file', async () => {
    list
      .mockResolvedValueOnce({ items: [{ key: 'misc/notes.txt', size: 512, lastModified: '2024-03-01T10:00:00Z' }] })
      .mockResolvedValueOnce({ items: [] });
    renderOtherFilesPage();
    expect(await screen.findByRole('link', { name: /download/i })).toBeInTheDocument();
  });

  test('shows files from both misc/ and uploads-landing/ prefixes', async () => {
    list
      .mockResolvedValueOnce({ items: [{ key: 'misc/a.pdf', size: 100, lastModified: '2024-01-01' }] })
      .mockResolvedValueOnce({ items: [{ key: 'uploads-landing/b.zip', size: 200, lastModified: '2024-01-02' }] });
    renderOtherFilesPage();
    expect(await screen.findByText('a.pdf')).toBeInTheDocument();
    expect(screen.getByText('b.zip')).toBeInTheDocument();
  });

  test('back button navigates to /library', async () => {
    render(
      <MemoryRouter initialEntries={['/library/files']}>
        <App />
      </MemoryRouter>
    );
    expect(await screen.findByRole('heading', { name: /other files/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /library/i }));
    expect(await screen.findByRole('heading', { name: /^library$/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// PhotosPage
// ---------------------------------------------------------------------------

const makePhoto = (id = 'abc123', overrides = {}) => ({
  photo_id: id,
  filename: `${id}.jpg`,
  thumbnail_url: `https://s3.example.com/thumbnails/${id}.jpg`,
  original_url: `https://s3.example.com/originals/${id}.jpg`,
  width: 1920,
  height: 1080,
  uploaded_at: '2024-03-01T10:00:00Z',
  ...overrides,
});

describe('PhotosPage', () => {
  beforeEach(() => {
    process.env.REACT_APP_PHOTOS_API_URL = 'https://api.example.com/photos';
    global.fetch = jest.fn().mockResolvedValue({ json: () => Promise.resolve([]) });
  });

  afterEach(() => {
    delete process.env.REACT_APP_PHOTOS_API_URL;
    delete global.fetch;
  });

  test('renders Photos heading', () => {
    renderPhotosPage();
    expect(screen.getByRole('heading', { name: /^photos$/i })).toBeInTheDocument();
  });

  test('renders sort-by and tag-filter controls', () => {
    renderPhotosPage();
    expect(screen.getByRole('combobox', { name: /sort by/i })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: /filter by tag/i })).toBeInTheDocument();
  });

  test('shows empty state when no photos returned', async () => {
    renderPhotosPage();
    expect(await screen.findByText(/no photos yet/i)).toBeInTheDocument();
  });

  test('shows thumbnails for returned photos', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      json: () => Promise.resolve([makePhoto('p1')]),
    });
    renderPhotosPage();
    const img = await screen.findByAltText('p1.jpg');
    expect(img).toHaveAttribute('src', 'https://s3.example.com/thumbnails/p1.jpg');
  });

  test('shows taken_at when present', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      json: () => Promise.resolve([makePhoto('p2', { taken_at: '2023-07-04T12:00:00+00:00' })]),
    });
    renderPhotosPage();
    expect(await screen.findByText(/taken:/i)).toBeInTheDocument();
  });

  test('shows tag chips', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      json: () => Promise.resolve([makePhoto('p3', { tags: ['landscape', 'flash'] })]),
    });
    renderPhotosPage();
    expect(await screen.findByText('landscape')).toBeInTheDocument();
    expect(screen.getByText('flash')).toBeInTheDocument();
  });

  test('initial fetch includes sort_by param', async () => {
    renderPhotosPage();
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('sort_by=uploaded_at'),
        expect.any(Object),
      );
    });
  });

  test('changing sort refetches with sort_by=taken_at', async () => {
    renderPhotosPage();
    await screen.findByText(/no photos yet/i);
    fireEvent.change(screen.getByRole('combobox', { name: /sort by/i }), {
      target: { value: 'taken_at' },
    });
    await waitFor(() => {
      const urls = global.fetch.mock.calls.map(([url]) => url);
      expect(urls.some(u => u.includes('sort_by=taken_at'))).toBe(true);
    });
  });

  test('changing tag refetches with tag=landscape', async () => {
    renderPhotosPage();
    await screen.findByText(/no photos yet/i);
    fireEvent.change(screen.getByRole('combobox', { name: /filter by tag/i }), {
      target: { value: 'landscape' },
    });
    await waitFor(() => {
      const urls = global.fetch.mock.calls.map(([url]) => url);
      expect(urls.some(u => u.includes('tag=landscape'))).toBe(true);
    });
  });

  test('back button navigates to /library', async () => {
    render(
      <MemoryRouter initialEntries={['/library/photos']}>
        <App />
      </MemoryRouter>
    );
    expect(await screen.findByRole('heading', { name: /^photos$/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /library/i }));
    expect(await screen.findByRole('heading', { name: /^library$/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// WhatsAppPage
// ---------------------------------------------------------------------------

const makeMessage = (id = 'msg001', overrides = {}) => ({
  message_id: id,
  date: '2023-07-04',
  time: '10:00',
  sender: 'Alice',
  message: 'Hello there',
  word_count: '2',
  ...overrides,
});

describe('WhatsAppPage', () => {
  beforeEach(() => {
    process.env.REACT_APP_CHATS_API_URL = 'https://api.example.com/chats';
    global.fetch = jest.fn().mockResolvedValue({ json: () => Promise.resolve([]) });
  });

  afterEach(() => {
    delete process.env.REACT_APP_CHATS_API_URL;
    delete global.fetch;
  });

  test('renders WhatsApp Messages heading', () => {
    renderWhatsAppPage();
    expect(screen.getByRole('heading', { name: /whatsapp messages/i })).toBeInTheDocument();
  });

  test('renders filter controls', () => {
    renderWhatsAppPage();
    expect(screen.getByRole('textbox', { name: /filter by sender/i })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /search messages/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /apply/i })).toBeInTheDocument();
  });

  test('shows empty state when no messages returned', async () => {
    renderWhatsAppPage();
    expect(await screen.findByText(/no messages found/i)).toBeInTheDocument();
  });

  test('shows messages grouped by date', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      json: () => Promise.resolve([makeMessage('m1')]),
    });
    renderWhatsAppPage();
    expect(await screen.findByText('Hello there')).toBeInTheDocument();
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('2023-07-04')).toBeInTheDocument();
  });

  test('initial fetch includes limit param', async () => {
    renderWhatsAppPage();
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('limit=500'),
        expect.any(Object),
      );
    });
  });

  test('back button navigates to /library', async () => {
    render(
      <MemoryRouter initialEntries={['/library/whatsapp']}>
        <App />
      </MemoryRouter>
    );
    expect(await screen.findByRole('heading', { name: /whatsapp messages/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /library/i }));
    expect(await screen.findByRole('heading', { name: /^library$/i })).toBeInTheDocument();
  });
});
