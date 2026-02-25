import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { uploadData } from 'aws-amplify/storage';


export default function HomePage({ signOut, user }) {
  const navigate = useNavigate();

  const [file, setFile] = useState(null);
  const [tier, setTier] = useState('Standard');
  const [uploadStatus, setUploadStatus] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [progress, setProgress] = useState(null);

  const handleDragOver = (e) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = (e) => { e.preventDefault(); setIsDragging(false); };
  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) setFile(dropped);
  };

  const handleUpload = async () => {
    if (!file) { alert('Please select a file first!'); return; }

    try {
      setUploadStatus('Uploading...');
      setProgress(0);

      const fileName = file.name;
      const extension = fileName.split('.').pop().toLowerCase();
      let storagePath = `misc/${fileName}`;
      if (extension === 'zip')                                  storagePath = `uploads-landing/${fileName}`;
      else if (extension === 'txt')                             storagePath = `raw-whatsapp-uploads/${fileName}`;
      else if (['jpg', 'jpeg', 'png', 'webp'].includes(extension)) storagePath = `raw-photos/${fileName}`;

      const result = await uploadData({
        key: storagePath,
        data: file,
        options: {
          contentType: file.type,
          metadata: { tier },
          onProgress: ({ transferredBytes, totalBytes }) => {
            if (totalBytes) setProgress(Math.round((transferredBytes / totalBytes) * 100));
          },
        },
      }).result;

      console.log('Uploaded to:', result.key);
      setProgress(null);
      setUploadStatus('Upload successful!');
      setFile(null);
    } catch (error) {
      console.error('Upload error:', error);
      setProgress(null);
      setUploadStatus('Upload failed. Check console.');
    }
  };

  return (
    <main style={styles.container}>

      {/* ── Intro ── */}
      <section style={styles.introBox}>
        <h1 style={styles.name}>Artur Carvalho Reis</h1>
        <p style={styles.bio}>
          Senior analytics and data engineer with a focus on cloud-native pipelines,
          event-driven architectures, and making data actually useful.
          I build things that process, store, and surface information — mostly on AWS.
        </p>
        <p style={styles.projectDesc}>
          This is a personal data engineering project that serves as a low-cost personal
          backup and organiser for my photos, WhatsApp chat exports, and other files.
          Files are stored in S3, photos are processed through a Lambda pipeline that
          extracts EXIF metadata, and WhatsApp chats flow through a Glue PySpark job
          into a queryable silver layer on Athena.
        </p>
      </section>

      {/* ── Upload ── */}
      <section style={styles.uploadBox}>
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

        <button onClick={handleUpload} style={styles.button}>Upload to Cloud</button>

        {progress !== null && (
          <div style={styles.progressTrack}>
            <div style={{ ...styles.progressBar, width: `${progress}%` }} />
            <span style={styles.progressLabel}>{progress}%</span>
          </div>
        )}

        {uploadStatus && <p style={styles.status}>{uploadStatus}</p>}
      </section>

      {/* ── Navigation ── */}
      <button onClick={() => navigate('/library')} style={styles.libraryBtn}>
        Open Library
      </button>

      <button onClick={signOut} style={styles.signOutBtn}>Sign out</button>
    </main>
  );
}

const styles = {
  container:    { maxWidth: '680px', margin: '50px auto', fontFamily: 'Arial, sans-serif', textAlign: 'center', padding: '0 16px' },

  introBox:     { marginBottom: '28px', textAlign: 'left' },
  name:         { fontSize: '2rem', fontWeight: '700', margin: '0 0 12px', color: '#111' },
  bio:          { fontSize: '15px', color: '#444', lineHeight: '1.6', margin: '0 0 10px' },
  projectDesc:  { fontSize: '14px', color: '#666', lineHeight: '1.6', margin: 0, padding: '12px 16px', background: '#f8f9fa', borderLeft: '3px solid #0073e6', borderRadius: '0 4px 4px 0' },

  uploadBox:    { border: '1px solid #ddd', padding: '20px', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.08)', marginBottom: '20px', textAlign: 'left' },
  dropZone:     { position: 'relative', border: '2px dashed #aaa', borderRadius: '6px', padding: '20px', marginBottom: '15px', color: '#666', cursor: 'pointer', transition: 'border-color 0.2s, background 0.2s', textAlign: 'center' },
  dropZoneActive: { borderColor: '#0073e6', background: '#e8f3ff', color: '#0073e6' },
  fileInput:    { position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer', width: '100%', height: '100%' },
  tierSelector: { marginBottom: '15px' },
  select:       { marginLeft: '10px', padding: '5px' },
  button:       { backgroundColor: '#0073e6', color: 'white', padding: '10px 20px', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '16px' },
  progressTrack: { position: 'relative', background: '#e0e0e0', borderRadius: '4px', height: '20px', marginTop: '15px', overflow: 'hidden' },
  progressBar:  { height: '100%', background: '#0073e6', borderRadius: '4px', transition: 'width 0.2s ease' },
  progressLabel: { position: 'absolute', top: 0, left: 0, right: 0, lineHeight: '20px', fontSize: '12px', fontWeight: 'bold', color: 'white', textAlign: 'center' },
  status:       { marginTop: '10px', fontWeight: 'bold', color: 'green' },

  libraryBtn:   { display: 'block', width: '100%', padding: '14px', marginBottom: '12px', backgroundColor: '#111', color: 'white', border: 'none', borderRadius: '6px', fontSize: '16px', fontWeight: '600', cursor: 'pointer', letterSpacing: '0.02em' },
  signOutBtn:   { backgroundColor: '#f0f0f0', border: '1px solid #ccc', padding: '8px 16px', cursor: 'pointer', borderRadius: '4px' },
};
