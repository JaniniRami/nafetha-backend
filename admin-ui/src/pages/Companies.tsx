import { useCallback, useEffect, useState } from "react";
import { apiFetch, type Company } from "../api";

const emptyForm = {
  company_name: "",
  linkedin_url: "",
  blacklisted: false,
  industry: "",
  company_size: "",
  website: "",
  phone: "",
  about_us: "",
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

      {editingId && (
        <div className="card">
          <h2>Edit company</h2>
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
      )}

      <div className="card">
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.75rem" }}>
          <h2 style={{ margin: 0 }}>All companies</h2>
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
                  <th>Name</th>
                  <th>LinkedIn</th>
                  <th>Flags</th>
                  <th>Scraped</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id}>
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
                      </div>
                    </td>
                  </tr>
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
