import { useCallback, useEffect, useState } from "react";
import {
  apiFetch,
  type ImportUrlsResponse,
  type LinkedInScrapeJob,
  type LinkedInScrapeJobStatus,
  type StartLinkedInScrapeResponse,
} from "../api";

const SCRAPE_BASE = "/api/v1/linkedin_scrape";

function splitTerms(raw: string): string[] {
  return raw
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** Job URLs: one per line, or several on one line as ``url_1, url_2, …`` (comma/semicolon before the next ``http``). */
function splitImportUrls(raw: string): string[] {
  const out: string[] = [];
  for (const line of raw.split(/\r?\n/)) {
    const piece = line.trim();
    if (!piece) continue;
    const byComma = piece.split(/,\s*(?=https?:\/\/)/i).map((p) => p.trim()).filter(Boolean);
    for (const chunk of byComma) {
      out.push(...chunk.split(/;\s*(?=https?:\/\/)/i).map((p) => p.trim()).filter(Boolean));
    }
  }
  return out;
}

function statusLabel(status: LinkedInScrapeJobStatus): string {
  return status;
}

function isActiveStatus(status: LinkedInScrapeJobStatus): boolean {
  return status === "queued" || status === "running" || status === "cancelling";
}

export default function LinkedInScraper() {
  const [keywordsText, setKeywordsText] = useState("Python");
  const [locationsText, setLocationsText] = useState("");
  const [jobsCap, setJobsCap] = useState("");
  const [delaySeconds, setDelaySeconds] = useState("2");
  const [verbose, setVerbose] = useState(true);
  const [sessionPath, setSessionPath] = useState("");

  const [jobs, setJobs] = useState<LinkedInScrapeJob[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<LinkedInScrapeJob | null>(null);

  const [listError, setListError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const [importText, setImportText] = useState("");
  const [importBusy, setImportBusy] = useState(false);
  const [importResult, setImportResult] = useState<ImportUrlsResponse | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setListError(null);
    try {
      const data = await apiFetch<LinkedInScrapeJob[]>(SCRAPE_BASE);
      setJobs(data);
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Failed to load jobs");
    }
  }, []);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }

    const jobId = selectedId;
    let cancelled = false;

    async function pull() {
      try {
        const j = await apiFetch<LinkedInScrapeJob>(`${SCRAPE_BASE}/${encodeURIComponent(jobId)}`);
        if (cancelled) return;
        setDetail(j);
        setJobs((prev) => {
          const i = prev.findIndex((x) => x.id === j.id);
          if (i === -1) return [j, ...prev];
          const next = [...prev];
          next[i] = j;
          return next;
        });
      } catch {
        /* ignore transient errors while polling */
      }
    }

    void pull();
    const id = window.setInterval(() => void pull(), 2000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [selectedId]);

  async function onStart(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setFormSuccess(null);
    const delay = Number(delaySeconds);
    if (!Number.isFinite(delay) || delay < 0 || delay > 30) {
      setFormError("Delay must be between 0 and 30 seconds.");
      return;
    }

    let jobsPerLocation: number | null = null;
    if (jobsCap.trim()) {
      const n = parseInt(jobsCap, 10);
      if (!Number.isFinite(n) || n < 1 || n > 1000) {
        setFormError("Jobs per location must be between 1 and 1000, or leave empty for no cap.");
        return;
      }
      jobsPerLocation = n;
    }

    const keywords = splitTerms(keywordsText);
    const locations = splitTerms(locationsText);

    const body: Record<string, unknown> = {
      keywords: keywords.length ? keywords : [],
      locations,
      jobs_per_location: jobsPerLocation,
      delay_seconds: delay,
      verbose,
    };
    if (sessionPath.trim()) body.session_path = sessionPath.trim();

    setStarting(true);
    try {
      const res = await apiFetch<StartLinkedInScrapeResponse>(SCRAPE_BASE, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setFormSuccess(`Started job ${res.job_id}`);
      setSelectedId(res.job_id);
      await loadList();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Start failed");
    } finally {
      setStarting(false);
    }
  }

  async function onCancel() {
    if (!selectedId) return;
    setFormError(null);
    try {
      await apiFetch<LinkedInScrapeJob>(`${SCRAPE_BASE}/${encodeURIComponent(selectedId)}/cancel`, {
        method: "POST",
      });
      await loadList();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Cancel failed");
    }
  }

  async function onImport(e: React.FormEvent) {
    e.preventDefault();
    setImportError(null);
    setImportResult(null);
    const urls = splitImportUrls(importText);
    if (!urls.length) {
      setImportError("Enter at least one LinkedIn job URL.");
      return;
    }
    const body: Record<string, unknown> = { urls, delay_seconds: 1.5, verbose: true };
    if (sessionPath.trim()) body.session_path = sessionPath.trim();

    setImportBusy(true);
    try {
      const res = await apiFetch<ImportUrlsResponse>(`${SCRAPE_BASE}/import-urls`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setImportResult(res);
    } catch (err) {
      setImportError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImportBusy(false);
    }
  }

  const shown = detail ?? jobs.find((j) => j.id === selectedId) ?? null;

  return (
    <>
      <h1>LinkedIn scraper</h1>
      <p className="muted">
        Runs on the API server (Playwright). Browser visibility and login follow server{" "}
        <code>HEADLESS_MODE</code>, <code>MANUAL_LOGIN</code>, and <code>LINKEDIN_*</code> settings.
      </p>

      <div className="card">
        <h2>Start search job</h2>
        {formError && <div className="error">{formError}</div>}
        {formSuccess && <div className="success">{formSuccess}</div>}
        <form onSubmit={onStart}>
          <div className="row">
            <div>
              <label htmlFor="sc_keywords">Keywords (one per line or comma-separated)</label>
              <textarea
                id="sc_keywords"
                value={keywordsText}
                onChange={(e) => setKeywordsText(e.target.value)}
                placeholder={"Python\nData engineer"}
              />
            </div>
            <div>
              <label htmlFor="sc_locations">Locations (optional)</label>
              <textarea
                id="sc_locations"
                value={locationsText}
                onChange={(e) => setLocationsText(e.target.value)}
                placeholder="United States"
              />
            </div>
          </div>
          <div className="row">
            <div>
              <label htmlFor="sc_cap">Jobs per location cap (optional)</label>
              <input
                id="sc_cap"
                type="number"
                min={1}
                max={1000}
                placeholder="Unlimited if empty"
                value={jobsCap}
                onChange={(e) => setJobsCap(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="sc_delay">Delay between requests (seconds)</label>
              <input
                id="sc_delay"
                type="number"
                min={0}
                max={30}
                step={0.5}
                value={delaySeconds}
                onChange={(e) => setDelaySeconds(e.target.value)}
              />
            </div>
          </div>
          <div className="row">
            <div>
              <label htmlFor="sc_session">Session file path (optional)</label>
              <input
                id="sc_session"
                value={sessionPath}
                onChange={(e) => setSessionPath(e.target.value)}
                placeholder="Server default if empty"
              />
            </div>
            <div className="checkbox-row">
              <label htmlFor="sc_verbose">
                <input
                  id="sc_verbose"
                  type="checkbox"
                  checked={verbose}
                  onChange={(e) => setVerbose(e.target.checked)}
                />{" "}
                Verbose server logging
              </label>
            </div>
          </div>
          <button type="submit" disabled={starting}>
            {starting ? "Starting…" : "Start scrape job"}
          </button>
        </form>
      </div>

      <div className="card">
        <h2>Import job URLs</h2>
        <p className="muted">
          Each URL must contain <code>/jobs/view/</code>. Paste one URL per line, or several on one line separated by
          commas or semicolons: <code>url_1, url_2, url_3</code>.
        </p>
        {importError && <div className="error">{importError}</div>}
        <form onSubmit={onImport}>
          <label htmlFor="sc_import">URLs</label>
          <textarea
            id="sc_import"
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            placeholder={
              "https://www.linkedin.com/jobs/view/111/, https://www.linkedin.com/jobs/view/222/\n" +
              "https://www.linkedin.com/jobs/view/333/"
            }
          />
          <button type="submit" disabled={importBusy} className="secondary">
            {importBusy ? "Importing…" : "Import URLs"}
          </button>
        </form>
        {importResult && (
          <div className="import-summary muted">
            Saved: {importResult.saved}, skipped: {importResult.skipped}, errors: {importResult.errors}
          </div>
        )}
        {importResult && importResult.results.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>URL</th>
                <th>Status</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {importResult.results.map((r) => (
                <tr key={r.url}>
                  <td>
                    <a href={r.url} target="_blank" rel="noreferrer">
                      {r.url}
                    </a>
                  </td>
                  <td>{r.status}</td>
                  <td className="muted">{r.reason ?? r.job_title ?? r.job_id ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <div className="card-toolbar">
          <h2>Jobs</h2>
          <button type="button" className="secondary" onClick={() => void loadList()}>
            Refresh list
          </button>
        </div>
        {listError && <div className="error">{listError}</div>}
        {jobs.length === 0 ? (
          <p className="muted">No scrape jobs in this server process yet.</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Progress</th>
                  <th>Jobs saved</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr
                    key={j.id}
                    className={`clickable-row${j.id === selectedId ? " row-selected" : ""}`}
                    onClick={() => setSelectedId(j.id === selectedId ? null : j.id)}
                  >
                    <td>
                      <span className={`badge status-${j.status}`}>{statusLabel(j.status)}</span>
                    </td>
                    <td className="muted">{new Date(j.created_at).toLocaleString()}</td>
                    <td>{j.progress.last_message}</td>
                    <td>{j.progress.jobs_scraped}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted">Click a row to select it and stream logs. Click again to clear.</p>
      </div>

      {shown && (
        <div className="card">
          <div className="card-toolbar">
            <h2>Job detail</h2>
            {selectedId && isActiveStatus(shown.status) && (
              <button type="button" className="secondary" onClick={() => void onCancel()}>
                Cancel job
              </button>
            )}
          </div>
          <p className="muted mono small">ID: {shown.id}</p>
          {shown.error && <div className="error">{shown.error}</div>}
          <div className="row">
            <div>
              <h3>Status</h3>
              <ul className="stat-list muted">
                <li>State: {shown.status}</li>
                <li>Targets: {shown.progress.locations_completed} / {shown.progress.total_locations}</li>
                <li>Current location: {shown.progress.current_location ?? "—"}</li>
                <li>Pages processed: {shown.progress.pages_processed}</li>
                <li>Job URLs found: {shown.progress.job_urls_found}</li>
                <li>Jobs scraped (this run): {shown.progress.jobs_scraped}</li>
                <li>Companies discovered: {shown.progress.companies_discovered}</li>
                <li>Companies scraped: {shown.progress.companies_scraped}</li>
              </ul>
            </div>
            <div>
              <h3>Request</h3>
              <ul className="stat-list muted">
                <li>Keywords: {shown.request.keywords.join(", ") || "(none)"}</li>
                <li>Locations: {shown.request.locations.length ? shown.request.locations.join(", ") : "(none)"}</li>
                <li>Cap: {shown.request.jobs_per_location ?? "none"}</li>
                <li>Delay: {shown.request.delay_seconds}s</li>
                <li>Verbose: {shown.request.verbose ? "yes" : "no"}</li>
              </ul>
            </div>
          </div>
          <h3>Logs</h3>
          <pre className="log-panel" aria-live="polite">
            {shown.progress.logs.length
              ? shown.progress.logs.join("\n")
              : "No log lines yet. Enable activity by starting a job; progress messages appear here."}
          </pre>
        </div>
      )}
    </>
  );
}
