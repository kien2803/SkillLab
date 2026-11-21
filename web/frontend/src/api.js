// Shared API client — bearer auth from localStorage, JSON everywhere,
// errors surface as readable strings/objects, never silently.
export const TOKEN_KEY = "skilllab_token";
export const tok = () => localStorage.getItem(TOKEN_KEY) || "";

export const api = (p, opts = {}) =>
  fetch("/api/v1" + p, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${tok()}`,
      ...(opts.headers || {}),
    },
  }).then((r) =>
    r.ok ? r.json()
         : r.json().then((e) => Promise.reject(e.detail || r.status)));

// authenticated GET returning the raw response (streams/downloads)
export const apiFetch = (p, opts = {}) =>
  fetch("/api/v1" + p, {
    ...opts,
    headers: { Authorization: `Bearer ${tok()}`,
               ...(opts.headers || {}) },
  });
