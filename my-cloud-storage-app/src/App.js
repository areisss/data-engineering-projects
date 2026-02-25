import React from 'react';
import { Routes, Route } from 'react-router-dom';
import { Authenticator } from '@aws-amplify/ui-react';
import '@aws-amplify/ui-react/styles.css';

import HomePage from './pages/HomePage';
import LibraryPage from './pages/LibraryPage';

export default function App() {
  return (
    <Authenticator>
      {({ signOut, user }) => (
        <Routes>
          <Route path="/" element={<HomePage signOut={signOut} user={user} />} />
          <Route path="/library" element={<LibraryPage />} />
        </Routes>
      )}
    </Authenticator>
  );
}
