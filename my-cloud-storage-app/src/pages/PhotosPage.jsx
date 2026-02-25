import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchAuthSession } from 'aws-amplify/auth';

export default function PhotosPage() {
  const navigate = useNavigate();

  const [photos, setPhotos] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sortBy, setSortBy] = useState('uploaded_at');
  const [tagFilter, setTagFilter] = useState('');

  const fetchPhotos = async (sort = sortBy, tag = tagFilter) => {
    const apiUrl = process.env.REACT_APP_PHOTOS_API_URL;
    if (!apiUrl) return;
    setLoading(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      const params = new URLSearchParams({ sort_by: sort });
      if (tag) params.set('tag', tag);
      const res = await fetch(`${apiUrl}?${params}`, {
        headers: { Authorization: token },
      });
      setPhotos(await res.json());
    } catch (err) {
      console.error('Error fetching photos:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPhotos();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <main style={styles.container}>
      <button onClick={() => navigate('/library')} style={styles.backBtn}>
        ← Library
      </button>

      <div style={styles.header}>
        <h1 style={styles.heading}>Photos</h1>
        <button onClick={() => fetchPhotos()} style={styles.refreshBtn} disabled={loading}>
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      <div style={styles.controls}>
        <label style={styles.controlLabel}>
          Sort by{' '}
          <select
            value={sortBy}
            onChange={e => { setSortBy(e.target.value); fetchPhotos(e.target.value, tagFilter); }}
            style={styles.controlSelect}
            aria-label="Sort by"
          >
            <option value="uploaded_at">Date uploaded</option>
            <option value="taken_at">Date taken</option>
          </select>
        </label>
        <label style={styles.controlLabel}>
          Tag{' '}
          <select
            value={tagFilter}
            onChange={e => { setTagFilter(e.target.value); fetchPhotos(sortBy, e.target.value); }}
            style={styles.controlSelect}
            aria-label="Filter by tag"
          >
            <option value="">All</option>
            <option value="landscape">landscape</option>
            <option value="portrait">portrait</option>
            <option value="square">square</option>
            <option value="flash">flash</option>
            <option value="gps">gps</option>
          </select>
        </label>
      </div>

      {loading ? (
        <p style={styles.muted}>Loading photos…</p>
      ) : photos.length === 0 ? (
        <p style={styles.muted}>No photos yet. Upload an image to get started.</p>
      ) : (() => {
        const groupKey = photo => {
          const d = new Date(photo.taken_at || photo.uploaded_at);
          return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
        };
        const grouped = photos.reduce((acc, p) => {
          const k = groupKey(p);
          if (!acc[k]) acc[k] = [];
          acc[k].push(p);
          return acc;
        }, {});
        const sortedKeys = Object.keys(grouped).sort((a, b) => b.localeCompare(a));
        const formatKey = k => new Date(k + '-02').toLocaleString('default', { month: 'long', year: 'numeric' });
        return sortedKeys.map(k => (
          <section key={k} style={styles.section}>
            <h2 style={styles.sectionHeading}>{formatKey(k)}</h2>
            <div style={styles.grid}>
              {grouped[k].map(photo => (
                <div key={photo.photo_id} style={styles.card}>
                  <img
                    src={photo.thumbnail_url}
                    alt={photo.filename}
                    style={styles.thumb}
                  />
                  <div style={styles.info}>
                    {photo.tags && photo.tags.length > 0 && (
                      <div style={styles.tagRow}>
                        {photo.tags.map(tag => (
                          <span key={tag} style={styles.tagChip}>{tag}</span>
                        ))}
                      </div>
                    )}
                    <a
                      href={photo.original_url}
                      download={photo.filename}
                      target="_blank"
                      rel="noreferrer"
                      style={styles.downloadLink}
                    >
                      Download
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </section>
        ));
      })()}
    </main>
  );
}

const styles = {
  container:    { maxWidth: '900px', margin: '40px auto', fontFamily: 'Arial, sans-serif', padding: '0 16px' },
  backBtn:      { background: 'none', border: 'none', color: '#0073e6', fontSize: '14px', cursor: 'pointer', padding: '0 0 16px', display: 'block' },
  header:       { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' },
  heading:      { fontSize: '1.8rem', fontWeight: '700', margin: 0, color: '#111' },
  refreshBtn:   { backgroundColor: '#f0f0f0', border: '1px solid #ccc', borderRadius: '4px', padding: '4px 12px', cursor: 'pointer', fontSize: '13px' },
  controls:     { display: 'flex', gap: '16px', alignItems: 'center', marginBottom: '20px', fontSize: '13px' },
  controlLabel: { display: 'flex', alignItems: 'center', gap: '6px', color: '#555' },
  controlSelect: { padding: '3px 6px', fontSize: '13px', borderRadius: '4px', border: '1px solid #ccc' },
  muted:        { color: '#999' },
  section:      { marginBottom: '32px' },
  sectionHeading: { fontSize: '1rem', fontWeight: '600', color: '#555', margin: '0 0 12px', textTransform: 'uppercase', letterSpacing: '0.05em' },
  grid:         { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(175px, 1fr))', gap: '16px' },
  card:         { border: '1px solid #e8e8e8', borderRadius: '6px', overflow: 'hidden' },
  thumb:        { width: '100%', aspectRatio: '1 / 1', objectFit: 'cover', display: 'block', background: '#f5f5f5' },
  info:         { padding: '8px', fontSize: '12px', textAlign: 'center' },
  tagRow:       { display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: '3px', marginBottom: '6px' },
  tagChip:      { backgroundColor: '#e8f0fe', color: '#1a56db', borderRadius: '10px', padding: '1px 7px', fontSize: '10px', fontWeight: '500' },
  downloadLink: { display: 'inline-block', padding: '4px 10px', backgroundColor: '#0073e6', color: 'white', borderRadius: '4px', textDecoration: 'none', fontSize: '11px' },
};
