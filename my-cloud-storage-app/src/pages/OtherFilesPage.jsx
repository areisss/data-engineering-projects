import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { list, getUrl } from 'aws-amplify/storage';

function formatBytes(bytes) {
  if (!bytes) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function basename(key) {
  return key.split('/').pop();
}

export default function OtherFilesPage() {
  const navigate = useNavigate();
  const [files, setFiles]     = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchFiles = async () => {
    setLoading(true);
    try {
      const [misc, landing] = await Promise.all([
        list({ prefix: 'misc/' }),
        list({ prefix: 'uploads-landing/' }),
      ]);
      const items = [...(misc.items || []), ...(landing.items || [])]
        .filter(item => basename(item.key))          // drop bare prefix entries
        .sort((a, b) => new Date(b.lastModified) - new Date(a.lastModified));

      const withUrls = await Promise.all(
        items.map(async item => {
          const { url } = await getUrl({ key: item.key });
          return { ...item, url: url.toString() };
        })
      );
      setFiles(withUrls);
    } catch (err) {
      console.error('Error fetching files:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFiles();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <main style={styles.container}>
      <button onClick={() => navigate('/library')} style={styles.backBtn}>
        ← Library
      </button>

      <div style={styles.header}>
        <h1 style={styles.heading}>Other Files</h1>
        <button onClick={fetchFiles} style={styles.refreshBtn} disabled={loading}>
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      {loading ? (
        <p style={styles.muted}>Loading files…</p>
      ) : files.length === 0 ? (
        <p style={styles.muted}>No files found. Upload a file from the home page to get started.</p>
      ) : (() => {
        const grouped = files.reduce((acc, f) => {
          const folder = f.key.split('/')[0] || 'other';
          if (!acc[folder]) acc[folder] = [];
          acc[folder].push(f);
          return acc;
        }, {});
        const formatFolder = f => f.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        return Object.keys(grouped).map(folder => (
          <section key={folder} style={styles.section}>
            <h2 style={styles.sectionHeading}>{formatFolder(folder)}</h2>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>File</th>
                  <th style={styles.th}>Size</th>
                  <th style={styles.th}>Uploaded</th>
                  <th style={styles.th}></th>
                </tr>
              </thead>
              <tbody>
                {grouped[folder].map(file => (
                  <tr key={file.key} style={styles.tr}>
                    <td style={styles.td}>{basename(file.key)}</td>
                    <td style={{ ...styles.td, ...styles.tdMuted }}>{formatBytes(file.size)}</td>
                    <td style={{ ...styles.td, ...styles.tdMuted }}>
                      {file.lastModified ? new Date(file.lastModified).toLocaleDateString() : '—'}
                    </td>
                    <td style={styles.td}>
                      <a href={file.url} download={basename(file.key)} style={styles.downloadLink}>
                        Download
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ));
      })()}
    </main>
  );
}

const styles = {
  container:    { maxWidth: '800px', margin: '40px auto', fontFamily: 'Arial, sans-serif', padding: '0 16px' },
  backBtn:      { background: 'none', border: 'none', color: '#0073e6', fontSize: '14px', cursor: 'pointer', padding: '0 0 16px', display: 'block' },
  header:       { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' },
  heading:      { fontSize: '1.8rem', fontWeight: '700', margin: 0, color: '#111' },
  refreshBtn:   { backgroundColor: '#f0f0f0', border: '1px solid #ccc', borderRadius: '4px', padding: '4px 12px', cursor: 'pointer', fontSize: '13px' },
  muted:        { color: '#999' },
  section:      { marginBottom: '32px' },
  sectionHeading: { fontSize: '1rem', fontWeight: '600', color: '#555', margin: '0 0 10px', textTransform: 'uppercase', letterSpacing: '0.05em' },
  table:        { width: '100%', borderCollapse: 'collapse', fontSize: '13px' },
  th:           { textAlign: 'left', padding: '8px 12px', borderBottom: '2px solid #eee', color: '#555', fontWeight: '600' },
  tr:           { borderBottom: '1px solid #f0f0f0' },
  td:           { padding: '10px 12px', color: '#333' },
  tdMuted:      { color: '#888' },
  downloadLink: { display: 'inline-block', padding: '3px 10px', backgroundColor: '#0073e6', color: 'white', borderRadius: '4px', textDecoration: 'none', fontSize: '11px' },
};
