# Frontend

**Stack**: React 19 (Create React App), AWS Amplify v6, `@aws-amplify/ui-react` v6
**Entry point**: `my-cloud-storage-app/src/index.js`
**All UI**: `my-cloud-storage-app/src/App.js` (single file, no routing)

---

## Structure

The app is a single page with no client-side routing. The entire UI lives inside one `App` component wrapped by the Amplify `<Authenticator>`. Unauthenticated users see only the Amplify-hosted sign-in / sign-up form; the app renders after successful login.

```
index.js
└── Amplify.configure(aws-exports)   ← wires Cognito + S3 at startup
└── <App />
    └── <Authenticator>              ← gate: renders children only when signed in
        ├── Upload section
        ├── Photo Gallery section
        └── File List section
```

There are three logical sections rendered in sequence. All share the same component scope — state, handlers, and styles are defined at the `App` function level.

---

## Authentication

`index.js` calls `Amplify.configure(config)` once at startup using `src/aws-exports.js`. This file is gitignored and injected at CI build time from the `AWS_EXPORTS_CONTENT` GitHub secret. It configures the Cognito User Pool, Identity Pool, and S3 bucket that Amplify uses for all subsequent SDK calls.

The `<Authenticator>` component from `@aws-amplify/ui-react` renders a complete sign-in / sign-up / confirm flow with no custom UI code. Once authenticated it passes `{ signOut, user }` to its children. The `user.username` is displayed in the heading.

---

## Upload section

### File selection

Two paths lead to a file being selected:
1. **Click**: a transparent `<input type="file">` is positioned over the entire drop zone (`position: absolute; inset: 0; opacity: 0`). Clicking anywhere in the zone opens the OS file picker. The selected file is stored in `file` state via `onChange`.
2. **Drag and drop**: `onDragOver`, `onDragLeave`, and `onDrop` handlers are attached to the drop zone `<div>`. `onDrop` reads `e.dataTransfer.files[0]` and sets it into `file` state. `isDragging` state toggles a CSS highlight (`dropZoneActive` style) while a file is held over the zone.

Only single-file selection is supported. The most recently selected or dropped file replaces any previous one.

### Storage tier

A `<select>` maps to the `tier` state (default `Standard`). The selected value is passed as S3 object metadata at upload time — it does not affect the S3 storage class directly, but records the user's intent for downstream cost management.

| Option | Metadata value |
|---|---|
| Standard (Frequent Access) | `Standard` |
| Intelligent Tiering (Photos) | `Intelligent` |
| Glacier Deep Archive (Backups) | `DeepArchive` |

### Upload flow

`handleUpload` is called when the user clicks **Upload to Cloud**:

1. Guards against no file selected (shows an `alert`)
2. Derives the destination S3 prefix from the file extension:

   | Extension | S3 prefix |
   |---|---|
   | `.zip` | `uploads-landing/` |
   | `.txt` | `raw-whatsapp-uploads/` |
   | `.jpg`, `.jpeg`, `.png`, `.webp` | `raw-photos/` |
   | anything else | `misc/` |

3. Calls `uploadData()` from `aws-amplify/storage` with:
   - `key`: the full S3 path
   - `data`: the `File` object
   - `options.contentType`: `file.type`
   - `options.metadata`: `{ tier: <selected tier> }`
   - `options.onProgress`: updates `progress` state (0–100) to drive the progress bar

4. On success: clears `progress`, sets `uploadStatus` to "Upload successful!", calls `fetchFiles()` to refresh the file list
5. On error: clears `progress`, sets `uploadStatus` to "Upload failed. Check console."

The progress bar is only shown while `progress !== null`. It is a pure CSS bar (`width: ${progress}%` on an inner div) with a percentage label centred over it.

Uploading an image to `raw-photos/` automatically triggers the `photo_processor` Lambda (via an S3 event notification) — the frontend is unaware of this; the photo appears in the gallery the next time **Refresh** is clicked.

---

## Photo Gallery section

### Data fetching

`fetchPhotos` is called on mount (inside `useEffect`) and when the user clicks **Refresh**.

```
fetchPhotos()
  1. Read process.env.REACT_APP_PHOTOS_API_URL
     └── if missing/empty: return immediately (no-op)
  2. fetchAuthSession()  ← aws-amplify/auth
     └── extract session.tokens.idToken.toString()
  3. fetch(apiUrl, { headers: { Authorization: idToken } })
     └── GET /photos on API Gateway (Cognito authorizer validates idToken)
  4. setPhotos(await res.json())
```

`photosLoading` state drives the Refresh button label ("Loading..." while in-flight) and shows a loading paragraph in place of the grid.

`REACT_APP_PHOTOS_API_URL` is baked into the bundle at CI build time from the `PHOTOS_API_URL` GitHub secret. If the env var is absent the gallery section renders silently with no API call.

### Pre-signed URLs

The API returns pre-signed S3 URLs in every photo object:

| Field | TTL | Used for |
|---|---|---|
| `thumbnail_url` | 1 hour | `<img src>` in the gallery grid |
| `original_url` | 24 hours | `<a href>` Download link |

The browser fetches thumbnails directly from S3 using these URLs — no Lambda or API Gateway is involved in serving the image bytes. The `original_url` is used as an anchor `href` with `download` and `target="_blank"` so the browser downloads the full-size image directly from S3.

### Gallery grid

Photos are sorted newest-first by `uploaded_at` (sorting done in the Lambda, not the frontend). They are rendered in a CSS grid:

```css
display: grid;
grid-template-columns: repeat(auto-fill, minmax(175px, 1fr));
gap: 16px;
```

Each card shows:
- Thumbnail image (`width: 100%; aspect-ratio: 1/1; object-fit: cover`)
- Filename (truncated with ellipsis if too long)
- Dimensions (`width × height`)
- Upload date (`toLocaleDateString()`)
- **Download** button (anchor tag, opens original in new tab)

---

## File List section

`fetchFiles` calls `list()` from `aws-amplify/storage` with `{ prefix: '', options: { listAll: true } }` to retrieve all objects in the Amplify-managed S3 bucket visible to the authenticated user. Results are sorted by `lastModified` descending.

Each row shows the full S3 key, size (formatted by `formatBytes`), last-modified date, and a **Delete** button. Clicking Delete shows a `window.confirm` prompt; on confirmation calls `remove({ key })` from `aws-amplify/storage` then refreshes the list.

`fetchFiles` is called on mount and after every upload or delete.

---

## State summary

| State variable | Type | Purpose |
|---|---|---|
| `file` | `File \| null` | Currently selected file |
| `tier` | `string` | Selected storage tier |
| `uploadStatus` | `string` | Success/error message below the upload button |
| `isDragging` | `boolean` | Controls drop zone highlight style |
| `progress` | `number \| null` | Upload progress 0–100; `null` hides the bar |
| `uploadedFiles` | `array` | Items from `list()` for the file table |
| `photos` | `array` | Photo objects from `GET /photos` for the gallery |
| `photosLoading` | `boolean` | Disables Refresh button and shows loading text |

---

## Testing

Tests are in `src/App.test.js` using React Testing Library and Jest. All AWS SDK calls are mocked:

- `aws-amplify/storage` (`uploadData`, `list`, `remove`) — mocked via `jest.mock` in the test file
- `aws-amplify/auth` (`fetchAuthSession`) — mocked via `moduleNameMapper` pointing to `src/__mocks__/amplifyAuthMock.js` (a plain function, not `jest.fn()`, because `jest` global is unavailable in mapper-loaded files)
- `@aws-amplify/ui-react` (`Authenticator`) — mocked to render children directly, bypassing the Cognito login wall
- `global.fetch` — set per gallery test via `beforeEach`

`REACT_APP_PHOTOS_API_URL` is set/cleaned in `beforeEach`/`afterEach` within the gallery test block to control whether `fetchPhotos` makes a fetch call.
