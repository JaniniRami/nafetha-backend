import { useCallback, useEffect, useState } from "react";
import { apiFetch, type ImportUrlsResponse, type Job } from "../api";

const TANQEEB_BASE = "/api/v1/tanqeeb_scrape";

/** Same URL parsing as LinkedIn scraper: one per line, or comma/semicolon before next ``http``. */
function splitImportUrls(raw: string): string[] {
  const out: string[] = [];
  for (const line of raw.split(/\r?\n/)) {
    const piece = line.trim();
    if (!piece) continue;
    const byComma = piece
      .split(/,\s*(?=https?:\/\/)/i)
      .map((p) => p.trim())
      .filter(Boolean);
    for (const chunk of byComma) {
      out.push(...chunk.split(/;\s*(?=https?:\/\/)/i).map((p) => p.trim()).filter(Boolean));
    }
  }
  return out;
}

const DEFAULT_SEARCH_PLACEHOLDER =
  "https://jordan.tanqeeb.com/jobs/search?keywords=intern&countries[]=24&page_no=1&dictionary=1&";

export default function TanqeebScraper() {
  const [searchUrl, setSearchUrl] = useState("");
  const [timeoutSeconds, setTimeoutSeconds] = useState("20");

  const [searchBusy, setSearchBusy] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchSuccess, setSearchSuccess] = useState<string | null>(null);
  const [searchResult, setSearchResult] = useState<ImportUrlsResponse | null>(null);

  const [importText, setImportText] = useState("");
  const [importBusy, setImportBusy] = useState(false);
  const [importResult, setImportResult] = useState<ImportUrlsResponse | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  const [recentJobs, setRecentJobs] = useState<Job[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  const loadRecentTanqeebJobs = useCallback(async () => {
    setListError(null);
    try {
      const all = await apiFetch<Job[]>("/api/admin/jobs");
      const tanqeeb = all
        .filter((j) => (j.keyword ?? "").toLowerCase() === "tanqeeb")
        .sort((a, b) => new Date(b.scraped_at).getTime() - new Date(a.scraped_at).getTime())
        .slice(0, 200);
      setRecentJobs(tanqeeb);
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Failed to load jobs");
    }
  }, []);

  useEffect(() => {
    void loadRecentTanqeebJobs();
  }, [loadRecentTanqeebJobs]);

  async function onStartSearch(e: React.FormEvent) {
    e.preventDefault();
    setSearchError(null);
    setSearchSuccess(null);
    setSearchResult(null);

    const timeout = parseInt(timeoutSeconds, 10);
    if (!Number.isFinite(timeout) || timeout < 5 || timeout > 120) {
      setSearchError("Timeout must be between 5 and 120 seconds.");
      return;
    }

    const body: Record<string, unknown> = { timeout_seconds: timeout };
    const trimmed = searchUrl.trim();
    if (trimmed) body.search_url = trimmed;

    setSearchBusy(true);
    try {
      const res = await apiFetch<ImportUrlsResponse>(`${TANQEEB_BASE}/import-search`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setSearchResult(res);
      setSearchSuccess(
        `Finished: saved ${res.saved}, skipped ${res.skipped}, errors ${res.errors}.`,
      );
      await loadRecentTanqeebJobs();
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : "Import search failed");
    } finally {
      setSearchBusy(false);
    }
  }

  async function onImport(e: React.FormEvent) {
    e.preventDefault();
    setImportError(null);
    setImportResult(null);
    const urls = splitImportUrls(importText);
    if (!urls.length) {
      setImportError("Enter at least one Tanqeeb job URL.");
      return;
    }

    const timeout = parseInt(timeoutSeconds, 10);
    if (!Number.isFinite(timeout) || timeout < 5 || timeout > 120) {
      setImportError("Timeout must be between 5 and 120 seconds.");
      return;
    }

    setImportBusy(true);
    try {
      const res = await apiFetch<ImportUrlsResponse>(`${TANQEEB_BASE}/import-urls`, {
        method: "POST",
        body: JSON.stringify({ urls, timeout_seconds: timeout }),
      });
      setImportResult(res);
      await loadRecentTanqeebJobs();
    } catch (err) {
      setImportError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImportBusy(false);
    }
  }

  const selectedJob = selectedId ? recentJobs.find((j) => j.id === selectedId) ?? null : null;

  function renderResultTable(res: ImportUrlsResponse) {
    if (res.results.length === 0) return null;
    return (
      <table>
        <thead>
          <tr>
            <th>URL</th>
            <th>Status</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          {res.results.map((r) => (
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
    );
  }

  let extraDetailsPretty = "";
  if (selectedJob?.extra_details) {
    try {
      extraDetailsPretty = JSON.stringify(JSON.parse(selectedJob.extra_details), null, 2);
    } catch {
      extraDetailsPretty = selectedJob.extra_details;
    }
  }

  return (
    <>
      <h1>Tanqeeb scraper</h1>
      <p className="muted">
        Runs on the API server (HTTP fetch, no browser). Search import crawls all result pages until empty; URL import
        scrapes each page you list. Rows are stored in the same <code>jobs</code> table with <code>keyword=tanqeeb</code>.
      </p>

      <div className="card">
        <h2>Start search import</h2>
        <p className="muted">
          Same idea as LinkedIn &quot;Start scrape job&quot;: one run over a Tanqeeb search URL. Leave URL empty to use
          the server default search. This can take several minutes.
        </p>
        {searchError && <div className="error">{searchError}</div>}
        {searchSuccess && <div className="success">{searchSuccess}</div>}
        <form onSubmit={onStartSearch}>
          <div className="row">
            <div>
              <label htmlFor="tq_search_url">Search URL (optional)</label>
              <textarea
                id="tq_search_url"
                value={searchUrl}
                onChange={(e) => setSearchUrl(e.target.value)}
                placeholder={DEFAULT_SEARCH_PLACEHOLDER}
              />
            </div>
            <div>
              <label htmlFor="tq_timeout">HTTP timeout per request (seconds)</label>
              <input
                id="tq_timeout"
                type="number"
                min={5}
                max={120}
                value={timeoutSeconds}
                onChange={(e) => setTimeoutSeconds(e.target.value)}
              />
            </div>
          </div>
          <button type="submit" disabled={searchBusy}>
            {searchBusy ? "Running import…" : "Run search import"}
          </button>
        </form>
        {searchResult && (
          <div className="import-summary muted">
            Saved: {searchResult.saved}, skipped: {searchResult.skipped}, errors: {searchResult.errors}
          </div>
        )}
        {searchResult && renderResultTable(searchResult)}
      </div>

      <div className="card">
        <h2>Import job URLs</h2>
        <p className="muted">
          Each URL must be a Tanqeeb job page (<code>tanqeeb.com</code> and <code>.html</code>). Paste one URL per line,
          or several on one line separated by commas or semicolons: <code>url_1, url_2, url_3</code>.
        </p>
        {importError && <div className="error">{importError}</div>}
        <form onSubmit={onImport}>
          <label htmlFor="tq_import">URLs</label>
          <textarea
            id="tq_import"
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            placeholder={
              "https://jordan.tanqeeb.com/jobs-in-middle-east/all/jobs/020916285.html\n" +
              "https://jordan.tanqeeb.com/jobs-in-jordan/all/jobs/020911795.html"
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
        {importResult && renderResultTable(importResult)}
      </div>

      <div className="card">
        <div className="card-toolbar">
          <h2>Recent Tanqeeb jobs (database)</h2>
          <button type="button" className="secondary" onClick={() => void loadRecentTanqeebJobs()}>
            Refresh list
          </button>
        </div>
        {listError && <div className="error">{listError}</div>}
        {recentJobs.length === 0 ? (
          <p className="muted">No Tanqeeb jobs in the database yet (keyword <code>tanqeeb</code>).</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Job id</th>
                  <th>URL</th>
                  <th>Posted</th>
                  <th>Scraped</th>
                </tr>
              </thead>
              <tbody>
                {recentJobs.map((j) => (
                  <tr
                    key={j.id}
                    className={`clickable-row${j.id === selectedId ? " row-selected" : ""}`}
                    onClick={() => setSelectedId(j.id === selectedId ? null : j.id)}
                  >
                    <td>{j.job_title ?? "—"}</td>
                    <td className="mono small">{j.job_id}</td>
                    <td>
                      <a href={j.job_url} target="_blank" rel="noreferrer" className="small">
                        link
                      </a>
                    </td>
                    <td className="muted small">{j.posted_date ?? "—"}</td>
                    <td className="muted small">{new Date(j.scraped_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted">Click a row for full detail. Click again to clear.</p>
      </div>

      {selectedJob && (
        <div className="card">
          <div className="card-toolbar">
            <h2>Job detail</h2>
          </div>
          <p className="muted mono small">Row id: {selectedJob.id}</p>
          <div className="row">
            <div>
              <h3>Fields</h3>
              <ul className="stat-list muted">
                <li>job_id: {selectedJob.job_id}</li>
                <li>keyword: {selectedJob.keyword ?? "—"}</li>
                <li>posted_date: {selectedJob.posted_date ?? "—"}</li>
                <li>
                  job_url:{" "}
                  <a href={selectedJob.job_url} target="_blank" rel="noreferrer">
                    {selectedJob.job_url}
                  </a>
                </li>
                <li>company_id: {selectedJob.company_id ?? "—"}</li>
                <li>company_name: {selectedJob.company_name ?? "—"}</li>
              </ul>
            </div>
            <div>
              <h3>Title</h3>
              <p>{selectedJob.job_title ?? "—"}</p>
            </div>
          </div>
          <h3>Description</h3>
          <pre className="log-panel" aria-live="polite">
            {selectedJob.job_description?.trim()
              ? selectedJob.job_description
              : "No description stored."}
          </pre>
          <h3>extra_details (JSON)</h3>
          <pre className="log-panel" aria-live="polite">
            {extraDetailsPretty || "—"}
          </pre>
        </div>
      )}
    </>
  );
}
