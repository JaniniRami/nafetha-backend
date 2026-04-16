import { useState } from "react";
import { useNavigate, Navigate } from "react-router-dom";
import { apiFetch } from "../api";

type AuthSession = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: { role: string };
};

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (localStorage.getItem("access_token")) {
    return <Navigate to="/companies" replace />;
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const session = await apiFetch<AuthSession>("/api/login", {
        method: "POST",
        body: JSON.stringify({
          email,
          password,
          use_session_cookie: false,
        }),
      });
      localStorage.setItem("access_token", session.access_token);
      localStorage.setItem("refresh_token", session.refresh_token);
      navigate("/companies", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="layout">
      <main style={{ maxWidth: 420 }}>
        <div className="card">
          <h1>Admin sign in</h1>
          {error && <div className="error">{error}</div>}
          <form onSubmit={onSubmit}>
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <button type="submit" disabled={loading}>
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>
          <p className="muted" style={{ marginTop: "1rem", marginBottom: 0 }}>
            Use a user with <code>superadmin</code> role to manage companies and jobs.
          </p>
        </div>
      </main>
    </div>
  );
}
