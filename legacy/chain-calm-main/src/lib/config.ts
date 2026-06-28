const detectApiBaseUrl = (): string => {
  if (typeof window === 'undefined') {
    return 'http://127.0.0.1:8000';
  }

  const { protocol, hostname } = window.location;
  return `${protocol}//${hostname}:8000`;
};

/** Trim trailing slashes so paths like `/suppliers/...` never become `//suppliers/...`. */
const normalizeBaseUrl = (url: string) => url.replace(/\/+$/, '');

export const API_BASE_URL = normalizeBaseUrl(
  import.meta.env.VITE_API_BASE_URL ?? detectApiBaseUrl()
);
