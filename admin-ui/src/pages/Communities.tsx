import { useCallback, useEffect, useState } from "react";
import { apiFetch, type Community, type CommunityEvent } from "../api";

const emptyCommunityForm = {
  name: "",
  description: "",
  website: "",
  keywords: "",
};

const emptyEventForm = {
  name: "",
  event_at: "",
  location: "",
  description: "",
  website: "",
  keywords: "",
};

function optionalWebsite(s: string): string | null {
  const t = s.trim();
  return t ? t : null;
}

function isoToDatetimeLocal(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function Communities() {
  const [communities, setCommunities] = useState<Community[]>([]);
  const [events, setEvents] = useState<CommunityEvent[]>([]);
  const [selectedCommunityId, setSelectedCommunityId] = useState("");
  const [loadingCommunities, setLoadingCommunities] = useState(true);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [communityForm, setCommunityForm] = useState(emptyCommunityForm);
  const [eventForm, setEventForm] = useState(emptyEventForm);

  const [editingCommunity, setEditingCommunity] = useState<Community | null>(null);
  const [editCommunityForm, setEditCommunityForm] = useState(emptyCommunityForm);
  const [aiCommunityIds, setAiCommunityIds] = useState<Record<string, boolean>>({});

  const [editingEvent, setEditingEvent] = useState<CommunityEvent | null>(null);
  const [editEventForm, setEditEventForm] = useState(emptyEventForm);

  const loadCommunities = useCallback(async () => {
    setError(null);
    setLoadingCommunities(true);
    try {
      const data = await apiFetch<Community[]>("/api/communities");
      setCommunities(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load communities");
    } finally {
      setLoadingCommunities(false);
    }
  }, []);

  const loadEvents = useCallback(async (communityId: string) => {
    if (!communityId) {
      setEvents([]);
      return;
    }
    setError(null);
    setLoadingEvents(true);
    try {
      const data = await apiFetch<CommunityEvent[]>(`/api/communities/${communityId}/events`);
      setEvents(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load events");
    } finally {
      setLoadingEvents(false);
    }
  }, []);

  useEffect(() => {
    void loadCommunities();
  }, [loadCommunities]);

  useEffect(() => {
    if (!selectedCommunityId && communities.length > 0) {
      setSelectedCommunityId(communities[0].id);
      return;
    }
    if (selectedCommunityId && !communities.some((c) => c.id === selectedCommunityId)) {
      setSelectedCommunityId(communities[0]?.id ?? "");
    }
  }, [communities, selectedCommunityId]);

  useEffect(() => {
    void loadEvents(selectedCommunityId);
  }, [selectedCommunityId, loadEvents]);

  async function onCreateCommunity(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    try {
      const kw = communityForm.keywords.trim();
      const created = await apiFetch<Community>("/api/communities", {
        method: "POST",
        body: JSON.stringify({
          name: communityForm.name.trim(),
          description: communityForm.description,
          website: optionalWebsite(communityForm.website),
          keywords: kw ? kw : null,
        }),
      });
      setSuccess("Community created.");
      setCommunityForm(emptyCommunityForm);
      await loadCommunities();
      setSelectedCommunityId(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  }

  function startEditCommunity(c: Community) {
    setError(null);
    setSuccess(null);
    setEditingCommunity(c);
    setEditCommunityForm({
      name: c.name,
      description: c.description,
      website: c.website ?? "",
      keywords: c.keywords ?? "",
    });
  }

  function cancelEditCommunity() {
    setEditingCommunity(null);
    setEditCommunityForm(emptyCommunityForm);
  }

  function hasCommunityContentForAi(c: Community): boolean {
    return !!(c.name ?? "").trim() || !!(c.description ?? "").trim();
  }

  function hasBothCommunityAiFields(c: Community): boolean {
    const d = (c.description ?? "").trim();
    const k = (c.keywords ?? "").trim();
    return !!(d && k);
  }

  async function onAiDisplayForCommunity(c: Community) {
    setError(null);
    setSuccess(null);
    setAiCommunityIds((prev) => ({ ...prev, [c.id]: true }));
    try {
      const updated = await apiFetch<Community>(`/api/communities/${encodeURIComponent(c.id)}/display-ai`, {
        method: "POST",
      });
      setSuccess("Description and keywords updated from name and description (AI).");
      setCommunities((prev) => prev.map((row) => (row.id === updated.id ? updated : row)));
      if (editingCommunity?.id === c.id) {
        setEditCommunityForm({
          name: updated.name,
          description: updated.description,
          website: updated.website ?? "",
          keywords: updated.keywords ?? "",
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "AI display generation failed");
    } finally {
      setAiCommunityIds((prev) => {
        const { [c.id]: _removed, ...rest } = prev;
        return rest;
      });
    }
  }

  async function onSaveCommunity(e: React.FormEvent) {
    e.preventDefault();
    if (!editingCommunity) return;
    setError(null);
    setSuccess(null);
    try {
      const kw = editCommunityForm.keywords.trim();
      await apiFetch<Community>(`/api/communities/${encodeURIComponent(editingCommunity.id)}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: editCommunityForm.name.trim(),
          description: editCommunityForm.description,
          website: optionalWebsite(editCommunityForm.website),
          keywords: kw ? kw : null,
        }),
      });
      setSuccess("Community updated.");
      cancelEditCommunity();
      await loadCommunities();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function onDeleteCommunity(c: Community) {
    if (
      !window.confirm(
        `Delete community “${c.name}”? All events in this community will be removed. Subscriptions and favorites are cleaned up by the database.`,
      )
    ) {
      return;
    }
    setError(null);
    setSuccess(null);
    try {
      await apiFetch<void>(`/api/communities/${encodeURIComponent(c.id)}`, { method: "DELETE" });
      if (editingCommunity?.id === c.id) cancelEditCommunity();
      if (editingEvent?.community_id === c.id) cancelEditEvent();
      setSuccess("Community deleted.");
      await loadCommunities();
      if (selectedCommunityId === c.id) setSelectedCommunityId("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function onCreateEvent(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedCommunityId) {
      setError("Select a community first.");
      return;
    }
    setError(null);
    setSuccess(null);
    if (!eventForm.event_at) {
      setError("Event date and time are required.");
      return;
    }
    try {
      await apiFetch<CommunityEvent>(`/api/communities/${selectedCommunityId}/events`, {
        method: "POST",
        body: JSON.stringify({
          name: eventForm.name.trim(),
          event_at: new Date(eventForm.event_at).toISOString(),
          location: eventForm.location.trim(),
          description: eventForm.description,
          website: optionalWebsite(eventForm.website),
          keywords: eventForm.keywords.trim() ? eventForm.keywords.trim() : null,
        }),
      });
      setSuccess("Event created.");
      setEventForm(emptyEventForm);
      await loadEvents(selectedCommunityId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  }

  function startEditEvent(ev: CommunityEvent) {
    setError(null);
    setSuccess(null);
    setEditingEvent(ev);
    setEditEventForm({
      name: ev.name,
      event_at: isoToDatetimeLocal(ev.event_at),
      location: ev.location,
      description: ev.description,
      website: ev.website ?? "",
      keywords: ev.keywords ?? "",
    });
  }

  function cancelEditEvent() {
    setEditingEvent(null);
    setEditEventForm(emptyEventForm);
  }

  async function onSaveEvent(e: React.FormEvent) {
    e.preventDefault();
    if (!editingEvent) return;
    setError(null);
    setSuccess(null);
    if (!editEventForm.event_at) {
      setError("Event date and time are required.");
      return;
    }
    try {
      await apiFetch<CommunityEvent>(
        `/api/communities/${encodeURIComponent(editingEvent.community_id)}/events/${encodeURIComponent(editingEvent.id)}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            name: editEventForm.name.trim(),
            event_at: new Date(editEventForm.event_at).toISOString(),
            location: editEventForm.location.trim(),
            description: editEventForm.description,
            website: optionalWebsite(editEventForm.website),
            keywords: editEventForm.keywords.trim() ? editEventForm.keywords.trim() : null,
          }),
        },
      );
      setSuccess("Event updated.");
      cancelEditEvent();
      await loadEvents(selectedCommunityId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function onDeleteEvent(ev: CommunityEvent) {
    if (!window.confirm(`Delete event “${ev.name}”?`)) return;
    setError(null);
    setSuccess(null);
    try {
      await apiFetch<void>(
        `/api/communities/${encodeURIComponent(ev.community_id)}/events/${encodeURIComponent(ev.id)}`,
        { method: "DELETE" },
      );
      if (editingEvent?.id === ev.id) cancelEditEvent();
      setSuccess("Event deleted.");
      await loadEvents(selectedCommunityId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  return (
    <>
      <h1>Communities &amp; events</h1>
      <p className="muted" style={{ marginTop: "-0.5rem", marginBottom: "1.25rem" }}>
        Superadmins can edit or delete any community and its events. Other users only manage communities they created.
      </p>

      <div className="card">
        <h2>Add community</h2>
        {error && <div className="error">{error}</div>}
        {success && <div className="success">{success}</div>}
        <form onSubmit={onCreateCommunity}>
          <div className="row">
            <div>
              <label htmlFor="c_name">Name</label>
              <input
                id="c_name"
                value={communityForm.name}
                onChange={(e) => setCommunityForm((f) => ({ ...f, name: e.target.value }))}
                required
              />
            </div>
            <div>
              <label htmlFor="c_website">Website (optional)</label>
              <input
                id="c_website"
                value={communityForm.website}
                onChange={(e) => setCommunityForm((f) => ({ ...f, website: e.target.value }))}
                placeholder="https://…"
              />
            </div>
          </div>
          <label htmlFor="c_description">Description</label>
          <textarea
            id="c_description"
            value={communityForm.description}
            onChange={(e) => setCommunityForm((f) => ({ ...f, description: e.target.value }))}
            rows={3}
          />
          <label htmlFor="c_keywords">Keywords (optional, comma-separated)</label>
          <input
            id="c_keywords"
            value={communityForm.keywords}
            onChange={(e) => setCommunityForm((f) => ({ ...f, keywords: e.target.value }))}
            placeholder="topic-one,topic-two"
          />
          <button type="submit">Create community</button>
        </form>
      </div>

      {editingCommunity && (
        <div className="card">
          <h2>Edit community</h2>
          <p className="muted">
            Id <code>{editingCommunity.id}</code>
          </p>
          <form onSubmit={onSaveCommunity}>
            <div className="row">
              <div>
                <label htmlFor="ec_name">Name</label>
                <input
                  id="ec_name"
                  value={editCommunityForm.name}
                  onChange={(e) => setEditCommunityForm((f) => ({ ...f, name: e.target.value }))}
                  required
                />
              </div>
              <div>
                <label htmlFor="ec_website">Website (optional)</label>
                <input
                  id="ec_website"
                  value={editCommunityForm.website}
                  onChange={(e) => setEditCommunityForm((f) => ({ ...f, website: e.target.value }))}
                />
              </div>
            </div>
            <label htmlFor="ec_description">Description</label>
            <textarea
              id="ec_description"
              value={editCommunityForm.description}
              onChange={(e) => setEditCommunityForm((f) => ({ ...f, description: e.target.value }))}
              rows={3}
            />
            <label htmlFor="ec_keywords">Keywords (optional, comma-separated)</label>
            <input
              id="ec_keywords"
              value={editCommunityForm.keywords}
              onChange={(e) => setEditCommunityForm((f) => ({ ...f, keywords: e.target.value }))}
            />
            <div className="table-actions">
              <button type="submit">Save changes</button>
              <button type="button" className="secondary" onClick={cancelEditCommunity}>
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="card">
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.75rem" }}>
          <h2 style={{ margin: 0 }}>Communities</h2>
          <button type="button" className="secondary" onClick={() => void loadCommunities()} disabled={loadingCommunities}>
            Refresh
          </button>
        </div>
        {loadingCommunities ? (
          <p className="muted">Loading…</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Website</th>
                  <th>Keywords</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {communities.map((c) => (
                  <tr key={c.id}>
                    <td>{c.name}</td>
                    <td>
                      {c.website ? (
                        <a href={c.website} target="_blank" rel="noreferrer">
                          link
                        </a>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td className="muted" style={{ maxWidth: "12rem", overflow: "hidden", textOverflow: "ellipsis" }} title={c.keywords ?? undefined}>
                      {c.keywords?.trim() ? c.keywords : "—"}
                    </td>
                    <td className="muted">{new Date(c.created_at).toLocaleString()}</td>
                    <td>
                      <div className="table-actions">
                        <button type="button" className="btn-sm" onClick={() => startEditCommunity(c)}>
                          Edit
                        </button>
                        <button type="button" className="btn-sm secondary" onClick={() => void onDeleteCommunity(c)}>
                          Delete
                        </button>
                        <button
                          type="button"
                          className="btn-sm secondary"
                          onClick={() => void onAiDisplayForCommunity(c)}
                          disabled={!!aiCommunityIds[c.id] || !hasCommunityContentForAi(c) || hasBothCommunityAiFields(c)}
                          title={
                            !hasCommunityContentForAi(c)
                              ? "Add a name or description first (AI uses both)"
                              : hasBothCommunityAiFields(c)
                                ? "Description and keywords are already set — clear one to run AI again"
                                : "Generate one-line description and three keywords (Ollama)"
                          }
                        >
                          {aiCommunityIds[c.id] ? "AI…" : "AI"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {communities.length === 0 && <p className="muted">No communities yet. Create one above.</p>}
          </div>
        )}
      </div>

      <div className="card">
        <h2>Add community event</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          Choose which community this event belongs to, then fill in the details. Date/time is saved in UTC from your
          browser&apos;s local timezone.
        </p>
        <form onSubmit={onCreateEvent}>
          <label htmlFor="ev_community">Community</label>
          <select
            id="ev_community"
            value={selectedCommunityId}
            onChange={(e) => setSelectedCommunityId(e.target.value)}
            required
            disabled={communities.length === 0}
          >
            {communities.length === 0 ? (
              <option value="">— Create a community first —</option>
            ) : (
              communities.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))
            )}
          </select>
          <div className="row">
            <div>
              <label htmlFor="ev_name">Event name</label>
              <input
                id="ev_name"
                value={eventForm.name}
                onChange={(e) => setEventForm((f) => ({ ...f, name: e.target.value }))}
                required
              />
            </div>
            <div>
              <label htmlFor="ev_at">Date &amp; time</label>
              <input
                id="ev_at"
                type="datetime-local"
                value={eventForm.event_at}
                onChange={(e) => setEventForm((f) => ({ ...f, event_at: e.target.value }))}
                required
              />
            </div>
          </div>
          <label htmlFor="ev_location">Location</label>
          <input
            id="ev_location"
            value={eventForm.location}
            onChange={(e) => setEventForm((f) => ({ ...f, location: e.target.value }))}
            required
          />
          <div className="row">
            <div>
              <label htmlFor="ev_website">Website (optional)</label>
              <input
                id="ev_website"
                value={eventForm.website}
                onChange={(e) => setEventForm((f) => ({ ...f, website: e.target.value }))}
                placeholder="RSVP or info link"
              />
            </div>
          </div>
          <label htmlFor="ev_description">Description</label>
          <textarea
            id="ev_description"
            value={eventForm.description}
            onChange={(e) => setEventForm((f) => ({ ...f, description: e.target.value }))}
            rows={3}
          />
          <label htmlFor="ev_keywords">Keywords (optional, comma-separated)</label>
          <input
            id="ev_keywords"
            value={eventForm.keywords}
            onChange={(e) => setEventForm((f) => ({ ...f, keywords: e.target.value }))}
            placeholder="topic-one,topic-two"
          />
          <button type="submit" disabled={communities.length === 0}>
            Create event
          </button>
        </form>
      </div>

      {editingEvent && (
        <div className="card">
          <h2>Edit event</h2>
          <p className="muted">
            Community id <code>{editingEvent.community_id}</code> — event id <code>{editingEvent.id}</code>
          </p>
          <form onSubmit={onSaveEvent}>
            <div className="row">
              <div>
                <label htmlFor="ee_name">Event name</label>
                <input
                  id="ee_name"
                  value={editEventForm.name}
                  onChange={(e) => setEditEventForm((f) => ({ ...f, name: e.target.value }))}
                  required
                />
              </div>
              <div>
                <label htmlFor="ee_at">Date &amp; time</label>
                <input
                  id="ee_at"
                  type="datetime-local"
                  value={editEventForm.event_at}
                  onChange={(e) => setEditEventForm((f) => ({ ...f, event_at: e.target.value }))}
                  required
                />
              </div>
            </div>
            <label htmlFor="ee_location">Location</label>
            <input
              id="ee_location"
              value={editEventForm.location}
              onChange={(e) => setEditEventForm((f) => ({ ...f, location: e.target.value }))}
              required
            />
            <label htmlFor="ee_website">Website (optional)</label>
            <input
              id="ee_website"
              value={editEventForm.website}
              onChange={(e) => setEditEventForm((f) => ({ ...f, website: e.target.value }))}
            />
            <label htmlFor="ee_description">Description</label>
            <textarea
              id="ee_description"
              value={editEventForm.description}
              onChange={(e) => setEditEventForm((f) => ({ ...f, description: e.target.value }))}
              rows={3}
            />
            <label htmlFor="ee_keywords">Keywords (optional, comma-separated)</label>
            <input
              id="ee_keywords"
              value={editEventForm.keywords}
              onChange={(e) => setEditEventForm((f) => ({ ...f, keywords: e.target.value }))}
            />
            <div className="table-actions">
              <button type="submit">Save changes</button>
              <button type="button" className="secondary" onClick={cancelEditEvent}>
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="card">
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
          <h2 style={{ margin: 0 }}>Events for selected community</h2>
          <select
            aria-label="Filter events by community"
            value={selectedCommunityId}
            onChange={(e) => setSelectedCommunityId(e.target.value)}
            disabled={communities.length === 0}
          >
            {communities.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <button type="button" className="secondary" onClick={() => void loadEvents(selectedCommunityId)} disabled={!selectedCommunityId || loadingEvents}>
            Refresh
          </button>
        </div>
        {!selectedCommunityId ? (
          <p className="muted">Create a community to list events.</p>
        ) : loadingEvents ? (
          <p className="muted">Loading…</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>When</th>
                  <th>Location</th>
                  <th>Website</th>
                  <th>Keywords</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {events.map((ev) => (
                  <tr key={ev.id}>
                    <td>{ev.name}</td>
                    <td className="muted">{new Date(ev.event_at).toLocaleString()}</td>
                    <td>{ev.location}</td>
                    <td>
                      {ev.website ? (
                        <a href={ev.website} target="_blank" rel="noreferrer">
                          link
                        </a>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td
                      className="muted"
                      style={{ maxWidth: "12rem", overflow: "hidden", textOverflow: "ellipsis" }}
                      title={ev.keywords ?? undefined}
                    >
                      {ev.keywords?.trim() ? ev.keywords : "—"}
                    </td>
                    <td>
                      <div className="table-actions">
                        <button type="button" className="btn-sm" onClick={() => startEditEvent(ev)}>
                          Edit
                        </button>
                        <button type="button" className="btn-sm secondary" onClick={() => void onDeleteEvent(ev)}>
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {events.length === 0 && <p className="muted">No events for this community yet.</p>}
          </div>
        )}
      </div>
    </>
  );
}
