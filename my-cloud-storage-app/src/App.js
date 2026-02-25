import React, { useState, useEffect } from 'react';
import { Authenticator } from '@aws-amplify/ui-react';
import { uploadData, list, remove } from 'aws-amplify/storage';
import { fetchAuthSession } from 'aws-amplify/auth';
import '@aws-amplify/ui-react/styles.css';

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function App() {
  const [file, setFile] = useState(null);
  const [tier, setTier] = useState('Standard');
  const [uploadStatus, setUploadStatus] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [progress, setProgress] = useState(null);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [photos, setPhotos] = useState([]);
  const [photosLoading, setPhotosLoading] = useState(false);
  const [sortBy, setSortBy] = useState('uploaded_at');
  const [tagFilter, setTagFilter] = useState('');

  const fetchFiles = async () => {
    try {
      const { items } = await list({ prefix: '', options: { listAll: true } });
      setUploadedFiles(items.sort((a, b) => b.lastModified - a.lastModified));
    } catch (error) {
      console.error('Error listing files:', error);
    }
  };

  // sort and tag are passed explicitly so onChange handlers can pass the
  // new value before React state has flushed.
  const fetchPhotos = async (sort = sortBy, tag = tagFilter) => {
    const apiUrl = process.env.REACT_APP_PHOTOS_API_URL;
    if (!apiUrl) return;
    setPhotosLoading(true);
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
      setPhotosLoading(false);
    }
  };

  useEffect(() => {
    fetchFiles();
    fetchPhotos();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleDelete = async (key) => {
    if (!window.confirm(`Delete "${key}"?`)) return;
    try {
      await remove({ key });
      fetchFiles();
    } catch (error) {
      console.error('Error deleting file:', error);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) setFile(dropped);
  };

  const handleUpload = async () => {
    if (!file) {
      alert("Please select a file first!");
      return;
    }

    try {
      setUploadStatus("Uploading...");
      setProgress(0);

      const fileName = file.name;
      const extension = fileName.split('.').pop().toLowerCase();

      let storagePath = `misc/${fileName}`;

      if (extension === 'zip') {
        storagePath = `uploads-landing/${fileName}`;
      } else if (extension === 'txt') {
        storagePath = `raw-whatsapp-uploads/${fileName}`;
      } else if (['jpg', 'jpeg', 'png', 'webp'].includes(extension)) {
        storagePath = `raw-photos/${fileName}`;
      }

      const result = await uploadData({
        key: storagePath,
        data: file,
        options: {
          contentType: file.type,
          metadata: { tier: tier },
          onProgress: ({ transferredBytes, totalBytes }) => {
            if (totalBytes) {
              setProgress(Math.round((transferredBytes / totalBytes) * 100));
            }
          }
        }
      }).result;

      console.log('File successfully uploaded to:', result.key);
      setProgress(null);
      setUploadStatus("Upload successful!");
      fetchFiles();

    } catch (error) {
      console.error('Error uploading file:', error);
      setProgress(null);
      setUploadStatus("Upload failed. Check console.");
    }
  };

  return (
    <Authenticator>
      {({ signOut, user }) => (
        <main style={styles.container}>
          <h1>Welcome, {user.username}</h1>

          <div style={styles.uploadBox}>
            <h2>Upload a File</h2>

            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              style={{ ...styles.dropZone, ...(isDragging ? styles.dropZoneActive : {}) }}
            >
              {file ? file.name : 'Drag & drop a file here, or click to select'}
              <input
                type="file"
                onChange={(e) => setFile(e.target.files[0])}
                style={styles.fileInput}
              />
            </div>

            <div style={styles.tierSelector}>
              <label>Choose Cost Tier: </label>
              <select value={tier} onChange={(e) => setTier(e.target.value)} style={styles.select}>
                <option value="Standard">Standard (Frequent Access)</option>
                <option value="Intelligent">Intelligent Tiering (Photos)</option>
                <option value="DeepArchive">Glacier Deep Archive (Backups)</option>
              </select>
            </div>

            <button onClick={handleUpload} style={styles.button}>
              Upload to Cloud
            </button>

            {progress !== null && (
              <div style={styles.progressTrack}>
                <div style={{ ...styles.progressBar, width: `${progress}%` }} />
                <span style={styles.progressLabel}>{progress}%</span>
              </div>
            )}

            {uploadStatus && <p style={styles.status}>{uploadStatus}</p>}
          </div>

          <div style={styles.galleryBox}>
            <div style={styles.galleryHeader}>
              <h2 style={{ margin: 0 }}>Photo Gallery</h2>
              <button
                onClick={() => fetchPhotos()}
                style={styles.refreshBtn}
                disabled={photosLoading}
              >
                {photosLoading ? 'Loading...' : 'Refresh'}
              </button>
            </div>

            <div style={styles.galleryControls}>
              <label style={styles.controlLabel}>
                Sort by{' '}
                <select
                  value={sortBy}
                  onChange={e => {
                    setSortBy(e.target.value);
                    fetchPhotos(e.target.value, tagFilter);
                  }}
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
                  onChange={e => {
                    setTagFilter(e.target.value);
                    fetchPhotos(sortBy, e.target.value);
                  }}
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

            {photosLoading ? (
              <p style={{ color: '#999' }}>Loading photos...</p>
            ) : photos.length === 0 ? (
              <p style={{ color: '#999' }}>No photos yet. Upload an image to get started.</p>
            ) : (
              <div style={styles.galleryGrid}>
                {photos.map((photo) => (
                  <div key={photo.photo_id} style={styles.photoCard}>
                    <img
                      src={photo.thumbnail_url}
                      alt={photo.filename}
                      style={styles.photoThumb}
                    />
                    <div style={styles.photoInfo}>
                      <div style={styles.photoName} title={photo.filename}>{photo.filename}</div>
                      <div style={styles.photoDims}>{photo.width} &times; {photo.height}</div>
                      <div style={styles.photoDate}>
                        {photo.taken_at
                          ? `Taken: ${new Date(photo.taken_at).toLocaleDateString()}`
                          : new Date(photo.uploaded_at).toLocaleDateString()}
                      </div>
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
            )}
          </div>

          <div style={styles.fileListBox}>
            <h2>Uploaded Files</h2>
            {uploadedFiles.length === 0 ? (
              <p style={{ color: '#999' }}>No files uploaded yet.</p>
            ) : (
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>File</th>
                    <th style={styles.th}>Size</th>
                    <th style={styles.th}>Date</th>
                    <th style={styles.th}></th>
                  </tr>
                </thead>
                <tbody>
                  {uploadedFiles.map((item) => (
                    <tr key={item.key}>
                      <td style={styles.td}>{item.key}</td>
                      <td style={styles.td}>{formatBytes(item.size)}</td>
                      <td style={styles.td}>{item.lastModified?.toLocaleDateString()}</td>
                      <td style={styles.td}>
                        <button onClick={() => handleDelete(item.key)} style={styles.deleteBtn}>Delete</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <button onClick={signOut} style={styles.signOutBtn}>Sign out</button>
        </main>
      )}
    </Authenticator>
  );
}

const styles = {
  container: { width: '700px', margin: '50px auto', fontFamily: 'Arial, sans-serif', textAlign: 'center' },
  uploadBox: { border: '1px solid #ddd', padding: '20px', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)', marginBottom: '20px' },
  dropZone: { position: 'relative', border: '2px dashed #aaa', borderRadius: '6px', padding: '20px', marginBottom: '15px', color: '#666', cursor: 'pointer', transition: 'border-color 0.2s, background 0.2s' },
  dropZoneActive: { borderColor: '#0073e6', background: '#e8f3ff', color: '#0073e6' },
  fileInput: { position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer', width: '100%', height: '100%' },
  tierSelector: { marginBottom: '15px', textAlign: 'left' },
  select: { marginLeft: '10px', padding: '5px' },
  button: { backgroundColor: '#0073e6', color: 'white', padding: '10px 20px', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '16px' },
  signOutBtn: { backgroundColor: '#f0f0f0', border: '1px solid #ccc', padding: '8px 16px', cursor: 'pointer' },
  progressTrack: { position: 'relative', background: '#e0e0e0', borderRadius: '4px', height: '20px', marginTop: '15px', overflow: 'hidden' },
  progressBar: { height: '100%', background: '#0073e6', borderRadius: '4px', transition: 'width 0.2s ease' },
  progressLabel: { position: 'absolute', top: 0, left: 0, right: 0, lineHeight: '20px', fontSize: '12px', fontWeight: 'bold', color: 'white', textAlign: 'center' },
  status: { marginTop: '10px', fontWeight: 'bold', color: 'green' },
  galleryBox: { border: '1px solid #ddd', padding: '20px', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)', marginBottom: '20px', textAlign: 'left' },
  galleryHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' },
  galleryControls: { display: 'flex', gap: '16px', alignItems: 'center', marginBottom: '14px', fontSize: '13px' },
  controlLabel: { display: 'flex', alignItems: 'center', gap: '6px', color: '#555' },
  controlSelect: { padding: '3px 6px', fontSize: '13px', borderRadius: '4px', border: '1px solid #ccc' },
  refreshBtn: { backgroundColor: '#f0f0f0', border: '1px solid #ccc', borderRadius: '4px', padding: '4px 12px', cursor: 'pointer', fontSize: '13px' },
  galleryGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(175px, 1fr))', gap: '16px' },
  photoCard: { border: '1px solid #e8e8e8', borderRadius: '6px', overflow: 'hidden' },
  photoThumb: { width: '100%', aspectRatio: '1 / 1', objectFit: 'cover', display: 'block', background: '#f5f5f5' },
  photoInfo: { padding: '8px', fontSize: '12px', textAlign: 'center' },
  photoName: { fontWeight: 'bold', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginBottom: '2px' },
  photoDims: { color: '#888', marginBottom: '2px' },
  photoDate: { color: '#888', marginBottom: '4px' },
  tagRow: { display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: '3px', marginBottom: '6px' },
  tagChip: { backgroundColor: '#e8f0fe', color: '#1a56db', borderRadius: '10px', padding: '1px 7px', fontSize: '10px', fontWeight: '500' },
  downloadLink: { display: 'inline-block', padding: '4px 10px', backgroundColor: '#0073e6', color: 'white', borderRadius: '4px', textDecoration: 'none', fontSize: '11px' },
  fileListBox: { border: '1px solid #ddd', padding: '20px', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)', marginBottom: '20px', textAlign: 'left' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: '14px' },
  th: { borderBottom: '2px solid #ddd', padding: '8px', textAlign: 'left', color: '#555' },
  td: { borderBottom: '1px solid #f0f0f0', padding: '8px', wordBreak: 'break-all' },
  deleteBtn: { backgroundColor: '#ff4d4d', color: 'white', border: 'none', borderRadius: '4px', padding: '4px 10px', cursor: 'pointer', fontSize: '12px' },
};
