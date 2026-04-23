import { Fragment, useCallback, useEffect, useState } from "react";
import { apiFetch, type VolunteeringEvent, type VolunteeringKeywordAIResponse } from "../api";

const emptyForm = {
  event_url: "",
  title: "",
  subtitle: "",
  organizer: "",
  organizer_website: "",
  description: "",
  duration_dates: "",
  days: "",
  keywords: "",
};

function eventToForm(event: VolunteeringEvent) {
  return {
    event_url: event.event_url,
    title: event.title ?? "",
    subtitle: event.subtitle ?? "",
    organizer: event.organizer ?? "",
    organizer_website: event.organizer_website ?? "",
    description: event.description ?? "",
    duration_dates: event.duration_dates ?? "",
    days: event.days ?? "",
    keywords: event.keywords ?? "",
  };
}

export default function Volunteering() {
  const [rows, setRows] = useState<VolunteeringEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState(emptyForm);
  const [aiEventIds, setAiEventIds] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const data = await apiFetch<VolunteeringEvent[]>("/api/volunteering-events");
      setRows(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load volunteering events");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function startEdit(event: VolunteeringEvent) {
    setError(null);
    setSuccess(null);
    setEditingId(event.id);
    setEditForm(eventToForm(event));
  }

  function cancelEdit() {
    setEditingId(null);
    setEditForm(emptyForm);
  }

  async function onSaveEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editingId) return;
    setError(null);
    setSuccess(null);
    try {
      await apiFetch<VolunteeringEvent>(`/api/admin/volunteering-events/${encodeURIComponent(editingId)}`, {
        method: "PATCH",
        body: JSON.stringify({
          event_url: editForm.event_url.trim(),
          title: editForm.title.trim() || null,
          subtitle: editForm.subtitle.trim() || null,
          organizer: editForm.organizer.trim() || null,
          organizer_website: editForm.organizer_website.trim() || null,
          description: editForm.description.trim() || null,
          duration_dates: editForm.duration_dates.trim() || null,
          days: editForm.days.trim() || null,
          keywords: editForm.keywords.trim() || null,
        }),
      });
      setSuccess("Volunteering event updated.");
      cancelEdit();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function onDelete(event: VolunteeringEvent) {
    if (!window.confirm(`Delete volunteering event “${event.title ?? event.event_url}”? This cannot be undone.`)) {
      return;
    }
    setError(null);
    setSuccess(null);
    try {
      await apiFetch<void>(`/api/admin/volunteering-events/${encodeURIComponent(event.id)}`, { method: "DELETE" });
      if (editingId === event.id) cancelEdit();
      if (selectedId === event.id) setSelectedId(null);
      setSuccess("Volunteering event deleted.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  function hasEventContentForAi(event: VolunteeringEvent): boolean {
    return !!(
      (event.title ?? "").trim() ||
      (event.subtitle ?? "").trim() ||
      (event.organizer ?? "").trim() ||
      (event.description ?? "").trim() ||
      (event.duration_dates ?? "").trim() ||
      (event.days ?? "").trim()
    );
  }

  function hasKeywordAlready(event: VolunteeringEvent): boolean {
    return !!(event.keywords ?? "").trim();
  }

  async function onAiKeyword(event: VolunteeringEvent) {
    setError(null);
    setSuccess(null);
    setAiEventIds((prev) => ({ ...prev, [event.id]: true }));
    try {
      const result = await apiFetch<VolunteeringKeywordAIResponse>(
        `/api/admin/volunteering-events/${encodeURIComponent(event.id)}/ai-keyword`,
        { method: "POST" },
      );
      if (result.saved && result.event) {
        setRows((prev) => prev.map((row) => (row.id === result.event!.id ? result.event! : row)));
        if (selectedId === result.event.id) {
          setSelectedId(result.event.id);
        }
        if (editingId === result.event.id) {
          setEditForm(eventToForm(result.event));
        }
        setSuccess(`AI keyword generated: ${result.keyword}`);
      } else if (!result.success) {
        setError("AI could not classify this event from its current text. Nothing was saved.");
      } else {
        setError("Unexpected AI response; nothing was saved.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "AI keyword generation failed");
    } finally {
      setAiEventIds((prev) => {
        const { [event.id]: _removed, ...rest } = prev;
        return rest;
      });
    }
  }

  const selected = selectedId ? rows.find((r) => r.id === selectedId) ?? null : null;

  return (
    <>
      <h1>Volunteering events</h1>

      <div className="card">
        <div className="card-toolbar">
          <h2 style={{ margin: 0 }}>All events</h2>
          <button type="button" className="secondary" onClick={() => void load()} disabled={loading}>
            Refresh
          </button>
        </div>
        {error && <div className="error">{error}</div>}
        {success && <div className="success">{success}</div>}
        {loading ? (
          <p className="muted">Loading…</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Organizer</th>
                  <th>Duration</th>
                  <th>Days</th>
                  <th>URL</th>
                  <th>Scraped</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((event) => (
                  <Fragment key={event.id}>
                    <tr
                      className={`clickable-row${event.id === selectedId ? " row-selected" : ""}`}
                      onClick={() => setSelectedId(event.id === selectedId ? null : event.id)}
                    >
                      <td>{event.title ?? "—"}</td>
                      <td>{event.organizer ?? "—"}</td>
                      <td className="muted">{event.duration_dates ?? "—"}</td>
                      <td className="muted">{event.days ?? "—"}</td>
                      <td>
                        <a href={event.event_url} target="_blank" rel="noreferrer" className="small">
                          link
                        </a>
                      </td>
                      <td className="muted small">{new Date(event.scraped_at).toLocaleString()}</td>
                      <td>
                        <div className="table-actions">
                          <button
                            type="button"
                            className="btn-sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              startEdit(event);
                            }}
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            className="btn-sm secondary"
                            onClick={(e) => {
                              e.stopPropagation();
                              void onDelete(event);
                            }}
                          >
                            Delete
                          </button>
                          <button
                            type="button"
                            className="btn-sm secondary"
                            onClick={(e) => {
                              e.stopPropagation();
                              void onAiKeyword(event);
                            }}
                            disabled={!!aiEventIds[event.id] || !hasEventContentForAi(event) || hasKeywordAlready(event)}
                            title={
                              !hasEventContentForAi(event)
                                ? "Add event text first (title/subtitle/organizer/description/dates/days)"
                                : hasKeywordAlready(event)
                                  ? "Keyword already exists — clear it to run AI again"
                                  : "Generate one classification keyword (AI)"
                            }
                          >
                            {aiEventIds[event.id] ? "AI…" : "AI"}
                          </button>
                        </div>
                      </td>
                    </tr>
                    {editingId === event.id && (
                      <tr>
                        <td colSpan={7}>
                          <div className="card" style={{ margin: 0 }}>
                            <h2 style={{ marginTop: 0 }}>Edit volunteering event</h2>
                            <p className="muted">
                              Row id <code>{editingId}</code>
                            </p>
                            <form onSubmit={onSaveEdit}>
                              <label htmlFor="ve_event_url">Event URL</label>
                              <input
                                id="ve_event_url"
                                value={editForm.event_url}
                                onChange={(e) => setEditForm((f) => ({ ...f, event_url: e.target.value }))}
                                required
                              />
                              <div className="row">
                                <div>
                                  <label htmlFor="ve_title">Title</label>
                                  <input
                                    id="ve_title"
                                    value={editForm.title}
                                    onChange={(e) => setEditForm((f) => ({ ...f, title: e.target.value }))}
                                  />
                                </div>
                                <div>
                                  <label htmlFor="ve_subtitle">Subtitle</label>
                                  <input
                                    id="ve_subtitle"
                                    value={editForm.subtitle}
                                    onChange={(e) => setEditForm((f) => ({ ...f, subtitle: e.target.value }))}
                                  />
                                </div>
                              </div>
                              <div className="row">
                                <div>
                                  <label htmlFor="ve_organizer">Organizer</label>
                                  <input
                                    id="ve_organizer"
                                    value={editForm.organizer}
                                    onChange={(e) => setEditForm((f) => ({ ...f, organizer: e.target.value }))}
                                  />
                                </div>
                                <div>
                                  <label htmlFor="ve_organizer_website">Organizer website</label>
                                  <input
                                    id="ve_organizer_website"
                                    value={editForm.organizer_website}
                                    onChange={(e) => setEditForm((f) => ({ ...f, organizer_website: e.target.value }))}
                                  />
                                </div>
                              </div>
                              <div className="row">
                                <div>
                                  <label htmlFor="ve_duration_dates">Duration dates</label>
                                  <input
                                    id="ve_duration_dates"
                                    value={editForm.duration_dates}
                                    onChange={(e) => setEditForm((f) => ({ ...f, duration_dates: e.target.value }))}
                                  />
                                </div>
                                <div>
                                  <label htmlFor="ve_days">Days</label>
                                  <input
                                    id="ve_days"
                                    value={editForm.days}
                                    onChange={(e) => setEditForm((f) => ({ ...f, days: e.target.value }))}
                                  />
                                </div>
                              </div>
                              <label htmlFor="ve_keywords">Keywords (optional, comma-separated)</label>
                              <input
                                id="ve_keywords"
                                value={editForm.keywords}
                                onChange={(e) => setEditForm((f) => ({ ...f, keywords: e.target.value }))}
                              />
                              <label htmlFor="ve_description">Description</label>
                              <textarea
                                id="ve_description"
                                value={editForm.description}
                                onChange={(e) => setEditForm((f) => ({ ...f, description: e.target.value }))}
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
                ))}
              </tbody>
            </table>
            {rows.length === 0 && <p className="muted">No volunteering events yet.</p>}
          </div>
        )}
        <p className="muted">Click a row for full detail. Click again to clear.</p>
      </div>

      {selected && (
        <div className="card">
          <h2>Event detail</h2>
          <p className="muted mono small">Row id: {selected.id}</p>
          <ul className="stat-list muted">
            <li>title: {selected.title ?? "—"}</li>
            <li>subtitle: {selected.subtitle ?? "—"}</li>
            <li>organizer: {selected.organizer ?? "—"}</li>
            <li>
              event_url:{" "}
              <a href={selected.event_url} target="_blank" rel="noreferrer">
                {selected.event_url}
              </a>
            </li>
            <li>
              organizer_website:{" "}
              {selected.organizer_website ? (
                <a href={selected.organizer_website} target="_blank" rel="noreferrer">
                  {selected.organizer_website}
                </a>
              ) : (
                "—"
              )}
            </li>
            <li>duration_dates: {selected.duration_dates ?? "—"}</li>
            <li>days: {selected.days ?? "—"}</li>
            <li>keywords: {selected.keywords ?? "—"}</li>
          </ul>
          <h3>Description</h3>
          <pre className="log-panel" aria-live="polite">
            {selected.description?.trim() ? selected.description : "No description stored."}
          </pre>
        </div>
      )}
    </>
  );
}
