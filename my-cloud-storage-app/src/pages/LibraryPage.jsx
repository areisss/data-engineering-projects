import React from 'react';
import { useNavigate } from 'react-router-dom';

const SECTIONS = [
  {
    key: 'photos',
    label: 'Photos',
    icon: '🖼',
    description: 'Browse and filter your photo library.',
  },
  {
    key: 'whatsapp',
    label: 'WhatsApp Messages',
    icon: '💬',
    description: 'Search and explore your chat exports.',
  },
  {
    key: 'files',
    label: 'Other Files',
    icon: '📁',
    description: 'View and manage all other uploaded files.',
  },
];

export default function LibraryPage() {
  const navigate = useNavigate();

  return (
    <main style={styles.container}>
      <button onClick={() => navigate('/')} style={styles.backBtn}>
        ← Back
      </button>

      <h1 style={styles.heading}>Library</h1>
      <p style={styles.subheading}>Choose a section to browse.</p>

      <div style={styles.grid}>
        {SECTIONS.map(({ key, label, icon, description }) => (
          <button
            key={key}
            style={styles.card}
            onClick={() => navigate(`/library/${key}`)}
            aria-label={label}
          >
            <span style={styles.icon}>{icon}</span>
            <span style={styles.cardLabel}>{label}</span>
            <span style={styles.cardDesc}>{description}</span>
          </button>
        ))}
      </div>
    </main>
  );
}

const styles = {
  container:   { maxWidth: '680px', margin: '50px auto', fontFamily: 'Arial, sans-serif', padding: '0 16px' },
  backBtn:     { background: 'none', border: 'none', color: '#0073e6', fontSize: '14px', cursor: 'pointer', padding: '0 0 24px', display: 'block' },
  heading:     { fontSize: '2rem', fontWeight: '700', margin: '0 0 8px', color: '#111' },
  subheading:  { fontSize: '15px', color: '#666', margin: '0 0 32px' },
  grid:        { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '16px' },
  card:        { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px', padding: '28px 16px', border: '1px solid #e0e0e0', borderRadius: '10px', background: 'white', cursor: 'pointer', textAlign: 'center', boxShadow: '0 1px 4px rgba(0,0,0,0.06)', transition: 'box-shadow 0.15s, border-color 0.15s' },
  icon:        { fontSize: '2.2rem', lineHeight: 1 },
  cardLabel:   { fontSize: '15px', fontWeight: '600', color: '#111' },
  cardDesc:    { fontSize: '12px', color: '#888', lineHeight: '1.4' },
};
