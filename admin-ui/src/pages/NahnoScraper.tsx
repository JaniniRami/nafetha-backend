import { useCallback, useEffect, useState } from "react";
import { apiFetch, type NahnoImportResponse, type VolunteeringEvent } from "../api";

const NAHNO_BASE = "/api/v1/nahno_scrape";

export default function NahnoScraper() {
  const [maxPages, setMaxPages] = useState("");
  const [delaySeconds, setDelaySeconds] = useState("2.5");
  const [lang, setLang] = useState("ar");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [result, setResult] = useState<NahnoImportResponse | null>(null);

  const [recentEvents, setRecentEvents] = useState<VolunteeringEvent[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  const loadRecentEvents = useCallback(async () => {
    setListError(null);
    try {
      const all = await apiFetch<VolunteeringEvent[]>("/api/volunteering-events");
      const sorted = [...all]
        .sort((a, b) => new Date(b.scraped_at).getTime() - new Date(a.scraped_at).getTime())
        .slice(0, 200);
      setRecentEvents(sorted);
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Failed to load events");
    }
  }, []);

  useEffect(() => {
    void loadRecentEvents();
  }, [loadRecentEvents]);

  async function onStartImport(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setResult(null);

    const delay = parseFloat(delaySeconds);
    if (!Number.isFinite(delay) || delay < 0 || delay > 30) {
      setError("Delay must be between 0 and 30 seconds.");
      return;
    }

    const body: Record<string, unknown> = {
      delay_seconds: delay,
      lang: lang.trim() || "ar",
    };

    const maxPagesTrimmed = maxPages.trim();
    if (maxPagesTrimmed) {
      const parsed = parseInt(maxPagesTrimmed, 10);
      if (!Number.isFinite(parsed) || parsed < 1 || parsed > 500) {
        setError("Max pages must be between 1 and 500 (or leave empty).");
        return;
      }
      body.max_pages = parsed;
    }

    setBusy(true);
    try {
      const res = await apiFetch<NahnoImportResponse>(`${NAHNO_BASE}/import-events`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setResult(res);
      setSuccess(`Finished: saved ${res.saved}, skipped ${res.skipped}, errors ${res.errors}.`);
      await loadRecentEvents();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nahno import failed");
    } finally {
      setBusy(false);
    }
  }

  function renderResultTable(res: NahnoImportResponse) {
    if (res.results.length === 0) return null;
    return (
      <table>
        <thead>
          <tr>
            <th>Event URL</th>
            <th>Status</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          {res.results.map((r) => (
            <tr key={r.event_url}>
              <td>
                <a href={r.event_url} target="_blank" rel="noreferrer">
                  {r.event_url}
                </a>
              </td>
              <td>{r.status}</td>
              <td className="muted">{r.reason ?? r.title ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  const selectedEvent = selectedId ? recentEvents.find((e) => e.id === selectedId) ?? null : null;

  return (
    <>
      <h1>Nahno scraper</h1>
      <p className="muted">
        Runs on the API server and imports volunteering events from Nahno into the{" "}
        <code>volunteering_events</code> table.
      </p>

      <div className="card">
        <h2>Start event import</h2>
        <p className="muted">
          Similar to Tanqeeb import: one run fetches volunteer listings, opens each event page, then persists each row.
          This can take several minutes.
        </p>
        {error && <div className="error">{error}</div>}
        {success && <div className="success">{success}</div>}
        <form onSubmit={onStartImport}>
          <div className="row">
            <div>
              <label htmlFor="nahno_max_pages">Max pages (optional)</label>
              <input
                id="nahno_max_pages"
                type="number"
                min={1}
                max={500}
                value={maxPages}
                onChange={(e) => setMaxPages(e.target.value)}
                placeholder="empty = all available"
              />
            </div>
            <div>
              <label htmlFor="nahno_delay">Delay between requests (seconds)</label>
              <input
                id="nahno_delay"
                type="number"
                min={0}
                max={30}
                step={0.1}
                value={delaySeconds}
                onChange={(e) => setDelaySeconds(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="nahno_lang">Language</label>
              <input id="nahno_lang" value={lang} onChange={(e) => setLang(e.target.value)} placeholder="ar" />
            </div>
          </div>
          <button type="submit" disabled={busy}>
            {busy ? "Running import…" : "Run Nahno import"}
          </button>
        </form>
        {result && (
          <div className="import-summary muted">
            Saved: {result.saved}, skipped: {result.skipped}, errors: {result.errors}
          </div>
        )}
        {result && renderResultTable(result)}
      </div>

      <div className="card">
        <div className="card-toolbar">
          <h2>Recent Nahno events (database)</h2>
          <button type="button" className="secondary" onClick={() => void loadRecentEvents()}>
            Refresh list
          </button>
        </div>
        {listError && <div className="error">{listError}</div>}
        {recentEvents.length === 0 ? (
          <p className="muted">No Nahno events in the database yet.</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Title</th>
                  <th>URL</th>
                  <th>Organizer</th>
                  <th>Duration</th>
                  <th>Scraped</th>
                </tr>
              </thead>
              <tbody>
                {recentEvents.map((event) => (
                  <tr
                    key={event.id}
                    className={`clickable-row${event.id === selectedId ? " row-selected" : ""}`}
                    onClick={() => setSelectedId(event.id === selectedId ? null : event.id)}
                  >
                    <td>{event.title ?? "—"}</td>
                    <td>
                      <a href={event.event_url} target="_blank" rel="noreferrer" className="small">
                        link
                      </a>
                    </td>
                    <td className="muted small">{event.organizer ?? "—"}</td>
                    <td className="muted small">{event.duration_dates ?? "—"}</td>
                    <td className="muted small">{new Date(event.scraped_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted">Click a row for full detail. Click again to clear.</p>
      </div>

      {selectedEvent && (
        <div className="card">
          <div className="card-toolbar">
            <h2>Event detail</h2>
          </div>
          <p className="muted mono small">Row id: {selectedEvent.id}</p>
          <ul className="stat-list muted">
            <li>
              event_url:{" "}
              <a href={selectedEvent.event_url} target="_blank" rel="noreferrer">
                {selectedEvent.event_url}
              </a>
            </li>
            <li>title: {selectedEvent.title ?? "—"}</li>
            <li>subtitle: {selectedEvent.subtitle ?? "—"}</li>
            <li>organizer: {selectedEvent.organizer ?? "—"}</li>
            <li>
              organizer_website:{" "}
              {selectedEvent.organizer_website ? (
                <a href={selectedEvent.organizer_website} target="_blank" rel="noreferrer">
                  {selectedEvent.organizer_website}
                </a>
              ) : (
                "—"
              )}
            </li>
            <li>duration_dates: {selectedEvent.duration_dates ?? "—"}</li>
            <li>days: {selectedEvent.days ?? "—"}</li>
          </ul>
          <h3>Description</h3>
          <pre className="log-panel" aria-live="polite">
            {selectedEvent.description?.trim() ? selectedEvent.description : "No description stored."}
          </pre>
        </div>
      )}
    </>
  );
}
