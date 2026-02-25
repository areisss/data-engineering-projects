import React from 'react';
import { Routes, Route } from 'react-router-dom';
import { Authenticator } from '@aws-amplify/ui-react';
import '@aws-amplify/ui-react/styles.css';

import HomePage from './pages/HomePage';
import LibraryPage from './pages/LibraryPage';
import PhotosPage from './pages/PhotosPage';

export default function App() {
  return (
    <Authenticator>
      {({ signOut, user }) => (
        <Routes>
          <Route path="/" element={<HomePage signOut={signOut} user={user} />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/library/photos" element={<PhotosPage />} />
        </Routes>
      )}
    </Authenticator>
  );
}
