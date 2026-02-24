// Plain function mock — jest.fn() is not available in moduleNameMapper-loaded files.
// fetchPhotos in App.js only needs a resolved session; no per-test overrides required.
const fetchAuthSession = () =>
  Promise.resolve({
    tokens: { idToken: { toString: () => 'mock-id-token' } },
  });

module.exports = { fetchAuthSession };
