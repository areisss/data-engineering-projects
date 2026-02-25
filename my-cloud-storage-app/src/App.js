import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Authenticator } from '@aws-amplify/ui-react';
import '@aws-amplify/ui-react/styles.css';

import HomePage from './pages/HomePage';
import LibraryPage from './pages/LibraryPage';
import PhotosPage from './pages/PhotosPage';
import WhatsAppPage from './pages/WhatsAppPage';

export default function App() {
  return (
    <Authenticator>
      {({ signOut, user }) => (
        <Routes>
          <Route path="/" element={<HomePage signOut={signOut} user={user} />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/library/photos" element={<PhotosPage />} />
          <Route path="/library/whatsapp" element={<WhatsAppPage />} />
          <Route path="*" element={<Navigate to="/library" replace />} />
        </Routes>
      )}
    </Authenticator>
  );
}
