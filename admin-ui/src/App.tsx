import { Navigate, Route, Routes, NavLink, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import Login from "./pages/Login";
import Companies from "./pages/Companies";
import Communities from "./pages/Communities";
import LinkedInScraper from "./pages/LinkedInScraper";
import NahnoScraper from "./pages/NahnoScraper";
import TanqeebScraper from "./pages/TanqeebScraper";
import Jobs from "./pages/Jobs";
import Volunteering from "./pages/Volunteering";
import { apiFetch, type MeResponse } from "./api";

function useSession() {
  const token = localStorage.getItem("access_token");
  return !!token;
}

function Layout({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();

  function logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    navigate("/login", { replace: true });
  }

  return (
    <div className="layout">
      <header className="app-header">
        <span className="app-header__brand">Nafetha Admin</span>
        <nav className="app-header__nav" aria-label="Main">
          <NavLink
            to="/companies"
            className={({ isActive }) => `app-header__link${isActive ? " app-header__link--active" : ""}`}
          >
            Companies
          </NavLink>
          <NavLink to="/jobs" className={({ isActive }) => `app-header__link${isActive ? " app-header__link--active" : ""}`}>
            Jobs
          </NavLink>
          <NavLink
            to="/volunteering"
            className={({ isActive }) => `app-header__link${isActive ? " app-header__link--active" : ""}`}
          >
            Volunteering
          </NavLink>
          <NavLink
            to="/communities"
            className={({ isActive }) => `app-header__link${isActive ? " app-header__link--active" : ""}`}
          >
            Communities
          </NavLink>
          <NavLink
            to="/linkedin-scraper"
            className={({ isActive }) => `app-header__link${isActive ? " app-header__link--active" : ""}`}
          >
            LinkedIn scraper
          </NavLink>
          <NavLink
            to="/tanqeeb-scraper"
            className={({ isActive }) => `app-header__link${isActive ? " app-header__link--active" : ""}`}
          >
            Tanqeeb scraper
          </NavLink>
          <NavLink
            to="/nahno-scraper"
            className={({ isActive }) => `app-header__link${isActive ? " app-header__link--active" : ""}`}
          >
            Nahno scraper
          </NavLink>
        </nav>
        <span className="spacer" />
        <button type="button" className="app-header__logout" onClick={logout}>
          Log out
        </button>
      </header>
      <main>{children}</main>
    </div>
  );
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const authed = useSession();
  const [me, setMe] = useState<MeResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!authed) return;
    let cancelled = false;
    (async () => {
      try {
        const u = await apiFetch<MeResponse>("/api/me");
        if (!cancelled) setMe(u);
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : "Session invalid");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [authed]);

  if (!authed) return <Navigate to="/login" replace />;

  if (err) {
    return (
      <Layout>
        <div className="card">
          <p className="error">{err}</p>
          <p className="muted">Try logging in again.</p>
        </div>
      </Layout>
    );
  }

  if (!me) {
    return (
      <Layout>
        <div className="card muted">Loading…</div>
      </Layout>
    );
  }

  if (me.role !== "superadmin") {
    return (
      <Layout>
        <div className="card">
          <p className="error">This account is not a superadmin.</p>
          <p className="muted">Admin API requires role <code>superadmin</code> in the database.</p>
        </div>
      </Layout>
    );
  }

  return <Layout>{children}</Layout>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/companies"
        element={
          <RequireAuth>
            <Companies />
          </RequireAuth>
        }
      />
      <Route
        path="/jobs"
        element={
          <RequireAuth>
            <Jobs />
          </RequireAuth>
        }
      />
      <Route
        path="/volunteering"
        element={
          <RequireAuth>
            <Volunteering />
          </RequireAuth>
        }
      />
      <Route
        path="/communities"
        element={
          <RequireAuth>
            <Communities />
          </RequireAuth>
        }
      />
      <Route
        path="/linkedin-scraper"
        element={
          <RequireAuth>
            <LinkedInScraper />
          </RequireAuth>
        }
      />
      <Route
        path="/tanqeeb-scraper"
        element={
          <RequireAuth>
            <TanqeebScraper />
          </RequireAuth>
        }
      />
      <Route
        path="/nahno-scraper"
        element={
          <RequireAuth>
            <NahnoScraper />
          </RequireAuth>
        }
      />
      <Route path="/" element={<Navigate to="/companies" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
