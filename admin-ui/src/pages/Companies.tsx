import { Fragment, useCallback, useEffect, useState } from "react";
import {
  apiFetch,
  type Company,
  type CompanyAboutBackfillJobQueued,
  type CompanyAboutBackfillJobStatus,
  type CompanyAboutBackfillResponse,
} from "../api";

const emptyForm = {
  company_name: "",
  linkedin_url: "",
  blacklisted: false,
  industry: "",
  company_size: "",
  website: "",
  phone: "",
  about_us: "",
  displayed_description: "",
  displayed_keywords: "",
};

function companyToForm(c: Company) {
  return {
    company_name: c.company_name,
    linkedin_url: c.linkedin_url ?? "",
    blacklisted: c.blacklisted,
    industry: c.industry ?? "",
    company_size: c.company_size ?? "",
    website: c.website ?? "",
    phone: c.phone ?? "",
    about_us: c.about_us ?? "",
    displayed_description: c.displayed_description ?? "",
    displayed_keywords: c.displayed_keywords ?? "",
  };
}

export default function Companies() {
  const [rows, setRows] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState(emptyForm);
  const [processingAllMissing, setProcessingAllMissing] = useState(false);
  const [processingAllCompanies, setProcessingAllCompanies] = useState(false);
  const [processingCompanyIds, setProcessingCompanyIds] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const data = await apiFetch<Company[]>("/api/admin/companies");
      setRows(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function startEdit(c: Company) {
    setError(null);
    setSuccess(null);
    setEditingId(c.id);
    setEditForm(companyToForm(c));
  }

  function cancelEdit() {
    setEditingId(null);
    setEditForm(emptyForm);
  }

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    try {
      await apiFetch<Company>("/api/admin/companies", {
        method: "POST",
        body: JSON.stringify({
          company_name: form.company_name,
          linkedin_url: form.linkedin_url.trim() || null,
          blacklisted: form.blacklisted,
          industry: form.industry || null,
          company_size: form.company_size || null,
          website: form.website || null,
          phone: form.phone || null,
          about_us: form.about_us || null,
          displayed_description: form.displayed_description || null,
          displayed_keywords: form.displayed_keywords || null,
        }),
      });
      setSuccess("Company created.");
      setForm(emptyForm);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  }

  async function onSaveEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editingId) return;
    setError(null);
    setSuccess(null);
    try {
      await apiFetch<Company>(`/api/admin/companies/${encodeURIComponent(editingId)}`, {
        method: "PATCH",
        body: JSON.stringify({
          company_name: editForm.company_name,
          linkedin_url: editForm.linkedin_url.trim() || null,
          blacklisted: editForm.blacklisted,
          industry: editForm.industry || null,
          company_size: editForm.company_size || null,
          website: editForm.website || null,
          phone: editForm.phone || null,
          about_us: editForm.about_us || null,
          displayed_description: editForm.displayed_description || null,
          displayed_keywords: editForm.displayed_keywords || null,
        }),
      });
      setSuccess("Company updated.");
      cancelEdit();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function onDelete(c: Company) {
    if (
      !window.confirm(
        `Delete company “${c.company_name}”? Linked jobs will keep their rows but lose this company link (company_id cleared).`,
      )
    ) {
      return;
    }
    setError(null);
    setSuccess(null);
    try {
      await apiFetch<void>(`/api/admin/companies/${encodeURIComponent(c.id)}`, { method: "DELETE" });
      if (editingId === c.id) cancelEdit();
      setSuccess("Company deleted.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  function hasMissingAbout(c: Company): boolean {
    return !(c.about_us ?? "").trim();
  }

  async function runBackfill(companyIds: string[], onlyMissing = true): Promise<CompanyAboutBackfillResponse> {
    return apiFetch<CompanyAboutBackfillResponse>("/api/admin/companies/backfill-about", {
      method: "POST",
      body: JSON.stringify({
        company_ids: companyIds,
        only_missing: onlyMissing,
      }),
    });
  }

  async function enqueueBackfillJob(companyIds: string[], onlyMissing: boolean): Promise<CompanyAboutBackfillJobQueued> {
    return apiFetch<CompanyAboutBackfillJobQueued>("/api/admin/companies/backfill-about/jobs", {
      method: "POST",
      body: JSON.stringify({
        company_ids: companyIds,
        only_missing: onlyMissing,
      }),
    });
  }

  async function pollBackfillJob(jobId: string): Promise<CompanyAboutBackfillJobStatus> {
    // Poll backend job until completion/failure.
    while (true) {
      const status = await apiFetch<CompanyAboutBackfillJobStatus>(
        `/api/admin/companies/backfill-about/jobs/${encodeURIComponent(jobId)}`,
      );
      if (status.status === "completed" || status.status === "failed") {
        return status;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
    }
  }

  async function onFillAboutForCompany(c: Company) {
    setError(null);
    setSuccess(null);
    setProcessingCompanyIds((prev) => ({ ...prev, [c.id]: true }));
    try {
      const result = await runBackfill([c.id], true);
      const updated = result.updated;
      const skipped = result.skipped;
      const failed = result.failed;
      if (updated > 0) {
        setSuccess(`Filled About for ${updated} company.`);
      } else if (skipped > 0) {
        setSuccess("Company already has About or could not be updated.");
      } else if (failed > 0) {
        setError("Failed to generate About for this company.");
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fill company About");
    } finally {
      setProcessingCompanyIds((prev) => {
        const { [c.id]: _removed, ...rest } = prev;
        return rest;
      });
    }
  }

  async function onQueueAllMissingAbout() {
    setError(null);
    setSuccess(null);
    setProcessingAllMissing(true);
    try {
      const queued = await enqueueBackfillJob([], true);
      const finalStatus = await pollBackfillJob(queued.job_id);
      if (finalStatus.status === "failed") {
        setError(finalStatus.error || "Missing-about queue job failed");
      } else {
        setSuccess(
          `Queued missing About processing finished. Updated: ${finalStatus.updated}, skipped: ${finalStatus.skipped}, failed: ${finalStatus.failed}.`,
        );
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed while processing missing companies");
    } finally {
      setProcessingAllMissing(false);
    }
  }

  async function onQueueAllAbout() {
    setError(null);
    setSuccess(null);
    setProcessingAllCompanies(true);
    try {
      const queued = await enqueueBackfillJob([], false);
      const finalStatus = await pollBackfillJob(queued.job_id);
      if (finalStatus.status === "failed") {
        setError(finalStatus.error || "Full about queue job failed");
      } else {
        setSuccess(
          `Queued full About processing finished. Updated: ${finalStatus.updated}, skipped: ${finalStatus.skipped}, failed: ${finalStatus.failed}.`,
        );
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed while processing all companies");
    } finally {
      setProcessingAllCompanies(false);
    }
  }

  return (
    <>
      <h1>Companies</h1>

      <div className="card">
        <h2>Add company</h2>
        {error && <div className="error">{error}</div>}
        {success && <div className="success">{success}</div>}
        <form onSubmit={onCreate}>
          <div className="row">
            <div>
              <label htmlFor="company_name">Name</label>
              <input
                id="company_name"
                value={form.company_name}
                onChange={(e) => setForm((f) => ({ ...f, company_name: e.target.value }))}
                required
              />
            </div>
            <div>
              <label htmlFor="linkedin_url">LinkedIn URL (optional)</label>
              <input
                id="linkedin_url"
                value={form.linkedin_url}
                onChange={(e) => setForm((f) => ({ ...f, linkedin_url: e.target.value }))}
                placeholder="https://…"
              />
            </div>
          </div>
          <div className="row">
            <div>
              <label htmlFor="industry">Industry</label>
              <input
                id="industry"
                value={form.industry}
                onChange={(e) => setForm((f) => ({ ...f, industry: e.target.value }))}
              />
            </div>
            <div>
              <label htmlFor="company_size">Company size</label>
              <input
                id="company_size"
                value={form.company_size}
                onChange={(e) => setForm((f) => ({ ...f, company_size: e.target.value }))}
              />
            </div>
          </div>
          <div className="row">
            <div>
              <label htmlFor="website">Website</label>
              <input
                id="website"
                value={form.website}
                onChange={(e) => setForm((f) => ({ ...f, website: e.target.value }))}
              />
            </div>
            <div>
              <label htmlFor="phone">Phone</label>
              <input
                id="phone"
                value={form.phone}
                onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
              />
            </div>
          </div>
          <label htmlFor="about_us">About</label>
          <textarea
            id="about_us"
            value={form.about_us}
            onChange={(e) => setForm((f) => ({ ...f, about_us: e.target.value }))}
          />
          <label htmlFor="displayed_description">Displayed Description</label>
          <textarea
            id="displayed_description"
            value={form.displayed_description}
            onChange={(e) => setForm((f) => ({ ...f, displayed_description: e.target.value }))}
          />
          <label htmlFor="displayed_keywords">Displayed Keywords (comma-separated, no spaces)</label>
          <input
            id="displayed_keywords"
            value={form.displayed_keywords}
            onChange={(e) => setForm((f) => ({ ...f, displayed_keywords: e.target.value }))}
            placeholder="keyword1,keyword2,keyword3"
          />
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
            <input
              type="checkbox"
              checked={form.blacklisted}
              onChange={(e) => setForm((f) => ({ ...f, blacklisted: e.target.checked }))}
            />
            Blacklisted
          </label>
          <button type="submit">Create company</button>
        </form>
      </div>

      <div className="card">
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.75rem" }}>
          <h2 style={{ margin: 0 }}>All companies</h2>
          <button type="button" className="secondary" onClick={() => void load()} disabled={loading}>
            Refresh
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => void onQueueAllMissingAbout()}
            disabled={loading || processingAllMissing || processingAllCompanies}
          >
            {processingAllMissing ? "Processing missing About..." : "Queue Missing About"}
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => void onQueueAllAbout()}
            disabled={loading || processingAllMissing || processingAllCompanies}
          >
            {processingAllCompanies ? "Processing all About..." : "Queue All About"}
          </button>
        </div>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>LinkedIn</th>
                  <th>Flags</th>
                  <th>Scraped</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <Fragment key={c.id}>
                    <tr>
                      <td>{c.company_name}</td>
                      <td>
                        {c.linkedin_url ? (
                          <a href={c.linkedin_url} target="_blank" rel="noreferrer">
                            link
                          </a>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td>
                        {c.blacklisted ? <span className="badge warn">blacklisted</span> : <span className="badge ok">active</span>}
                      </td>
                      <td className="muted">{new Date(c.scraped_at).toLocaleString()}</td>
                      <td>
                        <div className="table-actions">
                          <button type="button" className="btn-sm" onClick={() => startEdit(c)}>
                            Edit
                          </button>
                          <button type="button" className="btn-sm secondary" onClick={() => void onDelete(c)}>
                            Delete
                          </button>
                          <button
                            type="button"
                            className="btn-sm secondary"
                            onClick={() => void onFillAboutForCompany(c)}
                            disabled={
                              !!processingCompanyIds[c.id] || processingAllMissing || processingAllCompanies || !hasMissingAbout(c)
                            }
                            title={hasMissingAbout(c) ? "Fill About using website/LinkedIn content" : "About already exists"}
                          >
                            {processingCompanyIds[c.id] ? "Filling..." : "Fill About"}
                          </button>
                        </div>
                      </td>
                    </tr>
                    {editingId === c.id && (
                      <tr>
                        <td colSpan={5}>
                          <div className="card" style={{ margin: 0 }}>
                            <h2 style={{ marginTop: 0 }}>Edit company</h2>
                            <p className="muted">Updating company id <code>{editingId}</code></p>
                            <form onSubmit={onSaveEdit}>
                              <div className="row">
                                <div>
                                  <label htmlFor="ec_name">Name</label>
                                  <input
                                    id="ec_name"
                                    value={editForm.company_name}
                                    onChange={(e) => setEditForm((f) => ({ ...f, company_name: e.target.value }))}
                                    required
                                  />
                                </div>
                                <div>
                                  <label htmlFor="ec_linkedin_url">LinkedIn URL (optional)</label>
                                  <input
                                    id="ec_linkedin_url"
                                    value={editForm.linkedin_url}
                                    onChange={(e) => setEditForm((f) => ({ ...f, linkedin_url: e.target.value }))}
                                  />
                                </div>
                              </div>
                              <div className="row">
                                <div>
                                  <label htmlFor="ec_industry">Industry</label>
                                  <input
                                    id="ec_industry"
                                    value={editForm.industry}
                                    onChange={(e) => setEditForm((f) => ({ ...f, industry: e.target.value }))}
                                  />
                                </div>
                                <div>
                                  <label htmlFor="ec_company_size">Company size</label>
                                  <input
                                    id="ec_company_size"
                                    value={editForm.company_size}
                                    onChange={(e) => setEditForm((f) => ({ ...f, company_size: e.target.value }))}
                                  />
                                </div>
                              </div>
                              <div className="row">
                                <div>
                                  <label htmlFor="ec_website">Website</label>
                                  <input
                                    id="ec_website"
                                    value={editForm.website}
                                    onChange={(e) => setEditForm((f) => ({ ...f, website: e.target.value }))}
                                  />
                                </div>
                                <div>
                                  <label htmlFor="ec_phone">Phone</label>
                                  <input
                                    id="ec_phone"
                                    value={editForm.phone}
                                    onChange={(e) => setEditForm((f) => ({ ...f, phone: e.target.value }))}
                                  />
                                </div>
                              </div>
                              <label htmlFor="ec_about_us">About</label>
                              <textarea
                                id="ec_about_us"
                                value={editForm.about_us}
                                onChange={(e) => setEditForm((f) => ({ ...f, about_us: e.target.value }))}
                              />
                              <label htmlFor="ec_displayed_description">Displayed Description</label>
                              <textarea
                                id="ec_displayed_description"
                                value={editForm.displayed_description}
                                onChange={(e) => setEditForm((f) => ({ ...f, displayed_description: e.target.value }))}
                              />
                              <label htmlFor="ec_displayed_keywords">Displayed Keywords (comma-separated, no spaces)</label>
                              <input
                                id="ec_displayed_keywords"
                                value={editForm.displayed_keywords}
                                onChange={(e) => setEditForm((f) => ({ ...f, displayed_keywords: e.target.value }))}
                                placeholder="keyword1,keyword2,keyword3"
                              />
                              <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
                                <input
                                  type="checkbox"
                                  checked={editForm.blacklisted}
                                  onChange={(e) => setEditForm((f) => ({ ...f, blacklisted: e.target.checked }))}
                                />
                                Blacklisted
                              </label>
                              <div className="table-actions">
                                <button type="submit">Save changes</button>
                                <button type="button" className="secondary" onClick={cancelEdit}>
                                  Cancel
                                </button>
                              </div>
                            </form>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
            {rows.length === 0 && <p className="muted">No companies yet.</p>}
          </div>
        )}
      </div>
    </>
  );
}
