import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from './App';
import HomePage from './pages/HomePage';
import LibraryPage from './pages/LibraryPage';

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
});
