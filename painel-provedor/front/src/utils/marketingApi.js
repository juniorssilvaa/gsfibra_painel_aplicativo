export function authHeaders() {
  const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
  return token ? { Authorization: `Token ${token}` } : {};
}

export function errorText(err, fallback) {
  return err?.response?.data?.error || fallback;
}
