import React from 'react';
import { createRoot } from 'react-dom/client';

const root = document.getElementById('root');
if (!root) throw new Error('Missing root element');

createRoot(root).render(
  <React.StrictMode>
    <main>
      <h1>Terps To Mars</h1>
      <p>Marswalk planning map is under construction.</p>
    </main>
  </React.StrictMode>,
);
