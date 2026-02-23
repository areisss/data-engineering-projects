import React, { useState } from 'react';
import { Authenticator } from '@aws-amplify/ui-react';
import { uploadData } from 'aws-amplify/storage'; // New v6 import
import '@aws-amplify/ui-react/styles.css';

export default function App() {
  const [file, setFile] = useState(null);
  const [tier, setTier] = useState('Standard'); // Default to Standard
  const [uploadStatus, setUploadStatus] = useState('');

  const handleUpload = async () => {
    if (!file) {
      alert("Please select a file first!");
      return;
    }

    try {
      setUploadStatus("Uploading...");

      // We add the 'tier' as Metadata. 
      // Later, we will tell S3 to look for this metadata to move the file.
      const isPhoto = file.type.startsWith('image/');
      const folder = isPhoto ? 'raw-photos' : 'raw-whatsapp-uploads';
      const customKey = `${folder}/${file.name}`;

      const result = await uploadData({
        key: customKey,
        data: file,
        options: {
          metadata: {
            tier: tier // This adds x-amz-meta-tier: "DeepArchive" to the file
          }
        }
      }).result;

      console.log("Success:", result);
      setUploadStatus(`Success! Uploaded to ${tier} tier.`);
      setFile(null); // Reset file input
    } catch (error) {
      console.error("Error uploading file:", error);
      setUploadStatus("Error uploading file. Check console.");
    }
  };

  return (
    <Authenticator>
      {({ signOut, user }) => (
        <main style={styles.container}>
          <h1>Welcome, {user.username}</h1>

          {/* File Upload Section */}
          <div style={styles.uploadBox}>
            <h2>Upload a File</h2>

            <input
              type="file"
              onChange={(e) => setFile(e.target.files[0])}
              style={styles.input}
            />

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

            {uploadStatus && <p style={styles.status}>{uploadStatus}</p>}
          </div>

          <button onClick={signOut} style={styles.signOutBtn}>Sign out</button>
        </main>
      )}
    </Authenticator>
  );
}

// Simple CSS Styles to make it look decent
const styles = {
  container: { width: '400px', margin: '50px auto', fontFamily: 'Arial, sans-serif', textAlign: 'center' },
  uploadBox: { border: '1px solid #ddd', padding: '20px', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)', marginBottom: '20px' },
  input: { marginBottom: '15px', display: 'block', width: '100%' },
  tierSelector: { marginBottom: '15px', textAlign: 'left' },
  select: { marginLeft: '10px', padding: '5px' },
  button: { backgroundColor: '#0073e6', color: 'white', padding: '10px 20px', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '16px' },
  signOutBtn: { backgroundColor: '#f0f0f0', border: '1px solid #ccc', padding: '8px 16px', cursor: 'pointer' },
  status: { marginTop: '10px', fontWeight: 'bold', color: 'green' }
};