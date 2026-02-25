import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchAuthSession } from 'aws-amplify/auth';

export default function WhatsAppPage() {
  const navigate = useNavigate();

  const [messages, setMessages] = useState([]);
  const [loading, setLoading]   = useState(false);
  const [sender, setSender]     = useState('');
  const [search, setSearch]     = useState('');
  const [date, setDate]         = useState('');

  const fetchMessages = async (s = sender, q = search, d = date) => {
    const apiUrl = process.env.REACT_APP_CHATS_API_URL;
    if (!apiUrl) return;
    setLoading(true);
    try {
      const session = await fetchAuthSession();
      const token   = session.tokens?.idToken?.toString();
      const params  = new URLSearchParams({ limit: '500' });
      if (s) params.set('sender', s);
      if (q) params.set('search', q);
      if (d) params.set('date',   d);
      const res = await fetch(`${apiUrl}?${params}`, {
        headers: { Authorization: token },
      });
      const data = await res.json();
      setMessages(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Error fetching messages:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMessages();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Group messages by date for display
  const grouped = messages.reduce((acc, msg) => {
    const key = msg.date || 'Unknown date';
    if (!acc[key]) acc[key] = [];
    acc[key].push(msg);
    return acc;
  }, {});
  const sortedDates = Object.keys(grouped).sort((a, b) => b.localeCompare(a));

  return (
    <main style={styles.container}>
      <button onClick={() => navigate('/library')} style={styles.backBtn}>
        ← Library
      </button>

      <div style={styles.header}>
        <h1 style={styles.heading}>WhatsApp Messages</h1>
        <button onClick={() => fetchMessages()} style={styles.refreshBtn} disabled={loading}>
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      <div style={styles.controls}>
        <input
          type="text"
          placeholder="Filter by sender…"
          value={sender}
          onChange={e => setSender(e.target.value)}
          style={styles.input}
          aria-label="Filter by sender"
        />
        <input
          type="text"
          placeholder="Search messages…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={styles.input}
          aria-label="Search messages"
        />
        <input
          type="date"
          value={date}
          onChange={e => setDate(e.target.value)}
          style={styles.input}
          aria-label="Filter by date"
        />
        <button
          onClick={() => fetchMessages()}
          style={styles.applyBtn}
          disabled={loading}
        >
          Apply
        </button>
      </div>

      {loading ? (
        <p style={styles.muted}>Loading messages…</p>
      ) : messages.length === 0 ? (
        <p style={styles.muted}>No messages found.</p>
      ) : (
        <div>
          {sortedDates.map(d => (
            <div key={d} style={styles.dateGroup}>
              <div style={styles.dateLabel}>{d}</div>
              {grouped[d].map(msg => (
                <div key={msg.message_id} style={styles.msgRow}>
                  <span style={styles.time}>{msg.time}</span>
                  <span style={styles.msgSender}>{msg.sender}</span>
                  <span style={styles.msgText}>{msg.message}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </main>
  );
}

const styles = {
  container:  { maxWidth: '900px', margin: '40px auto', fontFamily: 'Arial, sans-serif', padding: '0 16px' },
  backBtn:    { background: 'none', border: 'none', color: '#0073e6', fontSize: '14px', cursor: 'pointer', padding: '0 0 16px', display: 'block' },
  header:     { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' },
  heading:    { fontSize: '1.8rem', fontWeight: '700', margin: 0, color: '#111' },
  refreshBtn: { backgroundColor: '#f0f0f0', border: '1px solid #ccc', borderRadius: '4px', padding: '4px 12px', cursor: 'pointer', fontSize: '13px' },
  controls:   { display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap' },
  input:      { padding: '5px 8px', fontSize: '13px', borderRadius: '4px', border: '1px solid #ccc', flex: '1 1 160px' },
  applyBtn:   { backgroundColor: '#0073e6', color: 'white', border: 'none', borderRadius: '4px', padding: '5px 14px', cursor: 'pointer', fontSize: '13px' },
  muted:      { color: '#999' },
  dateGroup:  { marginBottom: '20px' },
  dateLabel:  { fontSize: '13px', fontWeight: '700', color: '#555', padding: '4px 0', borderBottom: '1px solid #eee', marginBottom: '8px' },
  msgRow:     { display: 'flex', gap: '8px', padding: '4px 0', fontSize: '13px', borderBottom: '1px solid #f5f5f5' },
  time:       { color: '#aaa', minWidth: '50px', flexShrink: 0 },
  msgSender:  { fontWeight: '600', color: '#333', minWidth: '100px', flexShrink: 0 },
  msgText:    { color: '#444', flex: 1 },
};
