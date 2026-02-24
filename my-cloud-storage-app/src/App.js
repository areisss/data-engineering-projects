import React, { useState, useEffect } from 'react';
import { Authenticator } from '@aws-amplify/ui-react';
import { uploadData, list, remove } from 'aws-amplify/storage';
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

  const fetchFiles = async () => {
    try {
      const { items } = await list({ prefix: '', options: { listAll: true } });
      setUploadedFiles(items.sort((a, b) => b.lastModified - a.lastModified));
    } catch (error) {
      console.error('Error listing files:', error);
    }
  };

  useEffect(() => { fetchFiles(); }, []);

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

      // 1. Logic to determine the S3 path
      // Remove "public/" from the strings below
      let storagePath = `misc/${fileName}`;

      if (extension === 'zip') {
        storagePath = `uploads-landing/${fileName}`;
      } else if (extension === 'txt') {
        storagePath = `raw-whatsapp-uploads/${fileName}`;
      } else if (['jpg', 'jpeg', 'png', 'webp'].includes(extension)) {
        storagePath = `raw-photos/${fileName}`;
      }

      // 2. The S3 Upload with Metadata
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
  }; // End of handleUpload

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
} // End of App Component

const styles = {
  container: { width: '650px', margin: '50px auto', fontFamily: 'Arial, sans-serif', textAlign: 'center' },
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
  fileListBox: { border: '1px solid #ddd', padding: '20px', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)', marginBottom: '20px', textAlign: 'left' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: '14px' },
  th: { borderBottom: '2px solid #ddd', padding: '8px', textAlign: 'left', color: '#555' },
  td: { borderBottom: '1px solid #f0f0f0', padding: '8px', wordBreak: 'break-all' },
  deleteBtn: { backgroundColor: '#ff4d4d', color: 'white', border: 'none', borderRadius: '4px', padding: '4px 10px', cursor: 'pointer', fontSize: '12px' }
};