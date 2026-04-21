import { Fragment, useCallback, useEffect, useState } from "react";
import {
  apiFetch,
  type Job,
  type Company,
  type JobDisplayAIJobQueued,
  type JobDisplayAIJobStatus,
  type JobDisplayAIResponse,
} from "../api";

const emptyForm = {
  job_url: "",
  company_id: "",
  job_id: "",
  job_title: "",
  posted_date: "",
  job_description: "",
  extra_details: "",
  keyword: "",
  displayed_description: "",
  displayed_keywords: "",
};

function jobToForm(j: Job) {
  return {
    job_url: j.job_url,
    company_id: j.company_id ?? "",
    job_id: j.job_id,
    job_title: j.job_title ?? "",
    posted_date: j.posted_date ?? "",
    job_description: j.job_description ?? "",
    extra_details: j.extra_details ?? "",
    keyword: j.keyword ?? "",
    displayed_description: j.displayed_description ?? "",
    displayed_keywords: j.displayed_keywords ?? "",
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
  const [processingAllAiDisplay, setProcessingAllAiDisplay] = useState(false);
  const [aiJobRowIds, setAiJobRowIds] = useState<Record<string, boolean>>({});

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

  function hasJobDescriptionForAi(j: Job): boolean {
    return !!(j.job_description ?? "").trim();
  }

  function hasBothJobDisplayedFields(j: Job): boolean {
    const d = (j.displayed_description ?? "").trim();
    const k = (j.displayed_keywords ?? "").trim();
    return !!(d && k);
  }

  async function enqueueJobDisplayAiJob(
    jobIds: string[],
    onlyMissingDisplay: boolean,
  ): Promise<JobDisplayAIJobQueued> {
    return apiFetch<JobDisplayAIJobQueued>("/api/admin/jobs/ai-display/jobs", {
      method: "POST",
      body: JSON.stringify({
        job_ids: jobIds,
        only_missing_display: onlyMissingDisplay,
      }),
    });
  }

  async function pollJobDisplayAiJob(jobId: string): Promise<JobDisplayAIJobStatus> {
    while (true) {
      const status = await apiFetch<JobDisplayAIJobStatus>(
        `/api/admin/jobs/ai-display/jobs/${encodeURIComponent(jobId)}?wait=1`,
      );
      if (status.status === "completed" || status.status === "failed") {
        return status;
      }
    }
  }

  async function onAiDisplayForJob(j: Job) {
    setError(null);
    setSuccess(null);
    setAiJobRowIds((prev) => ({ ...prev, [j.id]: true }));
    try {
      const result = await apiFetch<JobDisplayAIResponse>(`/api/admin/jobs/${encodeURIComponent(j.id)}/ai-display`, {
        method: "POST",
      });
      if (result.saved && result.job) {
        setError(null);
        setSuccess("Displayed description and keywords updated from description (AI).");
        setRows((prev) => prev.map((row) => (row.id === result.job!.id ? result.job! : row)));
        if (editingId === j.id) {
          setEditForm(jobToForm(result.job));
        }
      } else if (!result.success) {
        setSuccess(null);
        setError(
          "AI did not treat the job text as a real posting (error/CAPTCHA/noise or unclear content). Nothing was saved.",
        );
      } else {
        setSuccess(null);
        setError("Unexpected AI response; nothing was saved.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "AI display generation failed");
    } finally {
      setAiJobRowIds((prev) => {
        const { [j.id]: _removed, ...rest } = prev;
        return rest;
      });
    }
  }

  async function onQueueAiProcessAllJobs() {
    setError(null);
    setSuccess(null);
    setProcessingAllAiDisplay(true);
    try {
      const queued = await enqueueJobDisplayAiJob([], true);
      const finalStatus = await pollJobDisplayAiJob(queued.job_id);
      if (finalStatus.status === "failed") {
        setError(finalStatus.error || "AI display queue job failed");
      } else {
        setSuccess(
          `AI display job finished. Processed: ${finalStatus.processed}, updated: ${finalStatus.updated}, skipped: ${finalStatus.skipped}, declined: ${finalStatus.declined}, failed: ${finalStatus.failed}.`,
        );
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed while running AI display job");
    } finally {
      setProcessingAllAiDisplay(false);
    }
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
          job_url: form.job_url,
          company_id: companyId ? companyId : null,
          job_id: form.job_id.trim() || null,
          job_title: form.job_title || null,
          posted_date: form.posted_date || null,
          job_description: form.job_description || null,
          extra_details: form.extra_details || null,
          keyword: form.keyword || null,
          displayed_description: form.displayed_description || null,
          displayed_keywords: form.displayed_keywords || null,
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
          job_url: editForm.job_url.trim(),
          company_id: companyId ? companyId : null,
          job_title: editForm.job_title.trim() || null,
          posted_date: editForm.posted_date.trim() || null,
          job_description: editForm.job_description.trim() || null,
          extra_details: editForm.extra_details.trim() || null,
          keyword: editForm.keyword.trim() || null,
          displayed_description: editForm.displayed_description.trim() || null,
          displayed_keywords: editForm.displayed_keywords.trim() || null,
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
          <label htmlFor="j_job_url">Job URL</label>
          <input
            id="j_job_url"
            value={form.job_url}
            onChange={(e) => setForm((f) => ({ ...f, job_url: e.target.value }))}
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
          <label htmlFor="posted_date">Posted date</label>
          <input
            id="posted_date"
            value={form.posted_date}
            onChange={(e) => setForm((f) => ({ ...f, posted_date: e.target.value }))}
          />
          <label htmlFor="keyword">Keyword</label>
          <input
            id="keyword"
            value={form.keyword}
            onChange={(e) => setForm((f) => ({ ...f, keyword: e.target.value }))}
          />
          <label htmlFor="job_description">Description</label>
          <textarea
            id="job_description"
            value={form.job_description}
            onChange={(e) => setForm((f) => ({ ...f, job_description: e.target.value }))}
          />
          <label htmlFor="extra_details">Extra details</label>
          <textarea
            id="extra_details"
            value={form.extra_details}
            onChange={(e) => setForm((f) => ({ ...f, extra_details: e.target.value }))}
          />
          <label htmlFor="displayed_description">Displayed description</label>
          <textarea
            id="displayed_description"
            value={form.displayed_description}
            onChange={(e) => setForm((f) => ({ ...f, displayed_description: e.target.value }))}
          />
          <label htmlFor="displayed_keywords">Displayed keywords (comma-separated, no spaces)</label>
          <input
            id="displayed_keywords"
            value={form.displayed_keywords}
            onChange={(e) => setForm((f) => ({ ...f, displayed_keywords: e.target.value }))}
            placeholder="keyword1,keyword2,keyword3"
          />
          <button type="submit">Create job</button>
        </form>
      </div>

      <div className="card">
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.75rem" }}>
          <h2 style={{ margin: 0 }}>All jobs</h2>
          <button type="button" className="secondary" onClick={() => void load()} disabled={loading || processingAllAiDisplay}>
            Refresh
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => void onQueueAiProcessAllJobs()}
            disabled={loading || processingAllAiDisplay}
            title="Jobs with a description where both displayed description and displayed keywords are empty."
          >
            {processingAllAiDisplay ? "AI processing…" : "AI Process All"}
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
                  <th>Job URL</th>
                  <th>Scraped</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((j) => {
                  const co = j.company_id ? companies.find((c) => c.id === j.company_id) : undefined;
                  return (
                    <Fragment key={j.id}>
                      <tr>
                        <td>{j.job_title ?? "—"}</td>
                        <td className="muted">{j.job_id}</td>
                        <td>
                          {j.company_name ??
                            co?.company_name ??
                            (j.company_id ? j.company_id.slice(0, 8) + "…" : "—")}
                        </td>
                        <td>
                          <a href={j.job_url} target="_blank" rel="noreferrer">
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
                            <button
                              type="button"
                              className="btn-sm secondary"
                              onClick={() => void onAiDisplayForJob(j)}
                              disabled={
                                !!aiJobRowIds[j.id] ||
                                processingAllAiDisplay ||
                                !hasJobDescriptionForAi(j) ||
                                hasBothJobDisplayedFields(j)
                              }
                              title={
                                !hasJobDescriptionForAi(j)
                                  ? "Add job description first (AI uses job_description)"
                                  : hasBothJobDisplayedFields(j)
                                    ? "Displayed description and keywords are already set"
                                    : "Generate displayed description & keywords from description (Gemini)"
                              }
                            >
                              {aiJobRowIds[j.id] ? "AI…" : "AI"}
                            </button>
                          </div>
                        </td>
                      </tr>
                      {editingId === j.id && (
                        <tr>
                          <td colSpan={6}>
                            <div className="card" style={{ margin: 0 }}>
                              <h2 style={{ marginTop: 0 }}>Edit job</h2>
                              <p className="muted">
                                Row id <code>{editingId}</code> — unique constraints apply to <code>job_id</code> and{" "}
                                <code>job_url</code>.
                              </p>
                              <form onSubmit={onSaveEdit}>
                                <label htmlFor="ej_job_url">Job URL</label>
                                <input
                                  id="ej_job_url"
                                  value={editForm.job_url}
                                  onChange={(e) => setEditForm((f) => ({ ...f, job_url: e.target.value }))}
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
                                <label htmlFor="ej_posted_date">Posted date</label>
                                <input
                                  id="ej_posted_date"
                                  value={editForm.posted_date}
                                  onChange={(e) => setEditForm((f) => ({ ...f, posted_date: e.target.value }))}
                                />
                                <label htmlFor="ej_keyword">Keyword</label>
                                <input
                                  id="ej_keyword"
                                  value={editForm.keyword}
                                  onChange={(e) => setEditForm((f) => ({ ...f, keyword: e.target.value }))}
                                />
                                <label htmlFor="ej_job_description">Description</label>
                                <textarea
                                  id="ej_job_description"
                                  value={editForm.job_description}
                                  onChange={(e) => setEditForm((f) => ({ ...f, job_description: e.target.value }))}
                                />
                                <label htmlFor="ej_extra_details">Extra details</label>
                                <textarea
                                  id="ej_extra_details"
                                  value={editForm.extra_details}
                                  onChange={(e) => setEditForm((f) => ({ ...f, extra_details: e.target.value }))}
                                />
                                <label htmlFor="ej_displayed_description">Displayed description</label>
                                <textarea
                                  id="ej_displayed_description"
                                  value={editForm.displayed_description}
                                  onChange={(e) =>
                                    setEditForm((f) => ({ ...f, displayed_description: e.target.value }))
                                  }
                                />
                                <label htmlFor="ej_displayed_keywords">Displayed keywords (comma-separated, no spaces)</label>
                                <input
                                  id="ej_displayed_keywords"
                                  value={editForm.displayed_keywords}
                                  onChange={(e) =>
                                    setEditForm((f) => ({ ...f, displayed_keywords: e.target.value }))
                                  }
                                  placeholder="keyword1,keyword2,keyword3"
                                />
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
