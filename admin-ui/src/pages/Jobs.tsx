import { useCallback, useEffect, useState } from "react";
import { apiFetch, type Job, type Company } from "../api";

const emptyForm = {
  linkedin_url: "",
  company_id: "",
  job_id: "",
  job_title: "",
  company_linkedin_url: "",
  posted_date: "",
  job_description: "",
  seed_location: "",
  keyword: "",
};

function jobToForm(j: Job) {
  return {
    linkedin_url: j.linkedin_url,
    company_id: j.company_id ?? "",
    job_id: j.job_id,
    job_title: j.job_title ?? "",
    company_linkedin_url: j.company_linkedin_url ?? "",
    posted_date: j.posted_date ?? "",
    job_description: j.job_description ?? "",
    seed_location: j.seed_location ?? "",
    keyword: j.keyword ?? "",
  };
}

export default function Jobs() {
  const [rows, setRows] = useState<Job[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState(emptyForm);

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const [jobData, companyData] = await Promise.all([
        apiFetch<Job[]>("/api/admin/jobs"),
        apiFetch<Company[]>("/api/admin/companies"),
      ]);
      setRows(jobData);
      setCompanies(companyData);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function startEdit(j: Job) {
    setError(null);
    setSuccess(null);
    setEditingId(j.id);
    setEditForm(jobToForm(j));
  }

  function cancelEdit() {
    setEditingId(null);
    setEditForm(emptyForm);
  }

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    const companyId = form.company_id.trim();
    try {
      await apiFetch<Job>("/api/admin/jobs", {
        method: "POST",
        body: JSON.stringify({
          linkedin_url: form.linkedin_url,
          company_id: companyId ? companyId : null,
          job_id: form.job_id.trim() || null,
          job_title: form.job_title || null,
          company_linkedin_url: form.company_linkedin_url || null,
          posted_date: form.posted_date || null,
          job_description: form.job_description || null,
          seed_location: form.seed_location || null,
          keyword: form.keyword || null,
        }),
      });
      setSuccess("Job created.");
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
    const companyId = editForm.company_id.trim();
    try {
      await apiFetch<Job>(`/api/admin/jobs/${encodeURIComponent(editingId)}`, {
        method: "PATCH",
        body: JSON.stringify({
          job_id: editForm.job_id.trim(),
          linkedin_url: editForm.linkedin_url.trim(),
          company_id: companyId ? companyId : null,
          job_title: editForm.job_title.trim() || null,
          company_linkedin_url: editForm.company_linkedin_url.trim() || null,
          posted_date: editForm.posted_date.trim() || null,
          job_description: editForm.job_description.trim() || null,
          seed_location: editForm.seed_location.trim() || null,
          keyword: editForm.keyword.trim() || null,
        }),
      });
      setSuccess("Job updated.");
      cancelEdit();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function onDelete(j: Job) {
    const label = j.job_title || j.job_id;
    if (!window.confirm(`Delete job “${label}”? This cannot be undone.`)) return;
    setError(null);
    setSuccess(null);
    try {
      await apiFetch<void>(`/api/admin/jobs/${encodeURIComponent(j.id)}`, { method: "DELETE" });
      if (editingId === j.id) cancelEdit();
      setSuccess("Job deleted.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  return (
    <>
      <h1>Jobs</h1>

      <div className="card">
        <h2>Add job</h2>
        {error && <div className="error">{error}</div>}
        {success && <div className="success">{success}</div>}
        <form onSubmit={onCreate}>
          <label htmlFor="j_linkedin_url">Job LinkedIn URL</label>
          <input
            id="j_linkedin_url"
            value={form.linkedin_url}
            onChange={(e) => setForm((f) => ({ ...f, linkedin_url: e.target.value }))}
            required
          />
          <label htmlFor="company_id">Company (optional)</label>
          <select
            id="company_id"
            value={form.company_id}
            onChange={(e) => setForm((f) => ({ ...f, company_id: e.target.value }))}
          >
            <option value="">— None —</option>
            {companies.map((c) => (
              <option key={c.id} value={c.id}>
                {c.company_name}
              </option>
            ))}
          </select>
          <div className="row">
            <div>
              <label htmlFor="ext_job_id">External job id (optional)</label>
              <input
                id="ext_job_id"
                value={form.job_id}
                onChange={(e) => setForm((f) => ({ ...f, job_id: e.target.value }))}
                placeholder="Leave empty to auto-assign"
              />
            </div>
            <div>
              <label htmlFor="job_title">Title</label>
              <input
                id="job_title"
                value={form.job_title}
                onChange={(e) => setForm((f) => ({ ...f, job_title: e.target.value }))}
              />
            </div>
          </div>
          <div className="row">
            <div>
              <label htmlFor="company_linkedin_url">Company LinkedIn URL</label>
              <input
                id="company_linkedin_url"
                value={form.company_linkedin_url}
                onChange={(e) => setForm((f) => ({ ...f, company_linkedin_url: e.target.value }))}
              />
            </div>
            <div>
              <label htmlFor="posted_date">Posted date</label>
              <input
                id="posted_date"
                value={form.posted_date}
                onChange={(e) => setForm((f) => ({ ...f, posted_date: e.target.value }))}
              />
            </div>
          </div>
          <div className="row">
            <div>
              <label htmlFor="keyword">Keyword</label>
              <input
                id="keyword"
                value={form.keyword}
                onChange={(e) => setForm((f) => ({ ...f, keyword: e.target.value }))}
              />
            </div>
            <div>
              <label htmlFor="seed_location">Seed location</label>
              <input
                id="seed_location"
                value={form.seed_location}
                onChange={(e) => setForm((f) => ({ ...f, seed_location: e.target.value }))}
              />
            </div>
          </div>
          <label htmlFor="job_description">Description</label>
          <textarea
            id="job_description"
            value={form.job_description}
            onChange={(e) => setForm((f) => ({ ...f, job_description: e.target.value }))}
          />
          <button type="submit">Create job</button>
        </form>
      </div>

      {editingId && (
        <div className="card">
          <h2>Edit job</h2>
          <p className="muted">
            Row id <code>{editingId}</code> — unique constraints apply to <code>job_id</code> and <code>linkedin_url</code>.
          </p>
          <form onSubmit={onSaveEdit}>
            <label htmlFor="ej_linkedin_url">Job LinkedIn URL</label>
            <input
              id="ej_linkedin_url"
              value={editForm.linkedin_url}
              onChange={(e) => setEditForm((f) => ({ ...f, linkedin_url: e.target.value }))}
              required
            />
            <label htmlFor="ej_company_id">Company (optional)</label>
            <select
              id="ej_company_id"
              value={editForm.company_id}
              onChange={(e) => setEditForm((f) => ({ ...f, company_id: e.target.value }))}
            >
              <option value="">— None —</option>
              {companies.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.company_name}
                </option>
              ))}
            </select>
            <div className="row">
              <div>
                <label htmlFor="ej_job_id">External job id</label>
                <input
                  id="ej_job_id"
                  value={editForm.job_id}
                  onChange={(e) => setEditForm((f) => ({ ...f, job_id: e.target.value }))}
                  required
                />
              </div>
              <div>
                <label htmlFor="ej_job_title">Title</label>
                <input
                  id="ej_job_title"
                  value={editForm.job_title}
                  onChange={(e) => setEditForm((f) => ({ ...f, job_title: e.target.value }))}
                />
              </div>
            </div>
            <div className="row">
              <div>
                <label htmlFor="ej_company_linkedin_url">Company LinkedIn URL</label>
                <input
                  id="ej_company_linkedin_url"
                  value={editForm.company_linkedin_url}
                  onChange={(e) => setEditForm((f) => ({ ...f, company_linkedin_url: e.target.value }))}
                />
              </div>
              <div>
                <label htmlFor="ej_posted_date">Posted date</label>
                <input
                  id="ej_posted_date"
                  value={editForm.posted_date}
                  onChange={(e) => setEditForm((f) => ({ ...f, posted_date: e.target.value }))}
                />
              </div>
            </div>
            <div className="row">
              <div>
                <label htmlFor="ej_keyword">Keyword</label>
                <input
                  id="ej_keyword"
                  value={editForm.keyword}
                  onChange={(e) => setEditForm((f) => ({ ...f, keyword: e.target.value }))}
                />
              </div>
              <div>
                <label htmlFor="ej_seed_location">Seed location</label>
                <input
                  id="ej_seed_location"
                  value={editForm.seed_location}
                  onChange={(e) => setEditForm((f) => ({ ...f, seed_location: e.target.value }))}
                />
              </div>
            </div>
            <label htmlFor="ej_job_description">Description</label>
            <textarea
              id="ej_job_description"
              value={editForm.job_description}
              onChange={(e) => setEditForm((f) => ({ ...f, job_description: e.target.value }))}
            />
            <div className="table-actions">
              <button type="submit">Save changes</button>
              <button type="button" className="secondary" onClick={cancelEdit}>
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="card">
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.75rem" }}>
          <h2 style={{ margin: 0 }}>All jobs</h2>
          <button type="button" className="secondary" onClick={() => void load()} disabled={loading}>
            Refresh
          </button>
        </div>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Title</th>
                  <th>External id</th>
                  <th>Company</th>
                  <th>LinkedIn</th>
                  <th>Scraped</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((j) => {
                  const co = j.company_id ? companies.find((c) => c.id === j.company_id) : undefined;
                  return (
                    <tr key={j.id}>
                      <td>{j.job_title ?? "—"}</td>
                      <td className="muted">{j.job_id}</td>
                      <td>{co?.company_name ?? (j.company_id ? j.company_id.slice(0, 8) + "…" : "—")}</td>
                      <td>
                        <a href={j.linkedin_url} target="_blank" rel="noreferrer">
                          link
                        </a>
                      </td>
                      <td className="muted">{new Date(j.scraped_at).toLocaleString()}</td>
                      <td>
                        <div className="table-actions">
                          <button type="button" className="btn-sm" onClick={() => startEdit(j)}>
                            Edit
                          </button>
                          <button type="button" className="btn-sm secondary" onClick={() => void onDelete(j)}>
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {rows.length === 0 && <p className="muted">No jobs yet.</p>}
          </div>
        )}
      </div>
    </>
  );
}
