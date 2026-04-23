import { useState } from "react";
import { apiFetch, type AdminResetRoadmapsResponse, type AdminResetSkillsResponse } from "../api";

export default function SystemReset() {
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState<"prereqs" | "roadmaps" | null>(null);

  async function onResetSkills() {
    if (!window.confirm("Delete all users' saved prerequisite selections (per skill)? This does not delete interests.")) return;
    setError(null);
    setSuccess(null);
    setBusy("prereqs");
    try {
      const result = await apiFetch<AdminResetSkillsResponse>("/api/admin/reset/skills", { method: "DELETE" });
      setSuccess(`Reset prerequisites done. Deleted profile prerequisites: ${result.deleted_profile_prerequisites}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset prerequisites failed");
    } finally {
      setBusy(null);
    }
  }

  async function onResetRoadmaps() {
    if (!window.confirm("Delete all saved roadmaps and roadmap steps for all users?")) return;
    setError(null);
    setSuccess(null);
    setBusy("roadmaps");
    try {
      const result = await apiFetch<AdminResetRoadmapsResponse>("/api/admin/reset/roadmaps", { method: "DELETE" });
      setSuccess(
        `Reset roadmaps done. Deleted roadmap steps: ${result.deleted_roadmap_steps}, deleted roadmaps: ${result.deleted_roadmaps}.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset roadmaps failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <h1>System Reset</h1>
      <div className="card">
        <h2>Danger zone</h2>
        <p className="muted">
          Use these actions to clear saved prerequisite selections (per skill) or generated roadmaps from the backend database. Interests are not cleared by the
          prerequisites reset.
        </p>
        {error && <div className="error">{error}</div>}
        {success && <div className="success">{success}</div>}
        <div className="table-actions">
          <button type="button" className="secondary" onClick={() => void onResetSkills()} disabled={busy !== null}>
            {busy === "prereqs" ? "Resetting prerequisites..." : "Reset Prerequisite Selections"}
          </button>
          <button type="button" className="secondary" onClick={() => void onResetRoadmaps()} disabled={busy !== null}>
            {busy === "roadmaps" ? "Resetting roadmaps..." : "Reset Saved Roadmaps"}
          </button>
        </div>
      </div>
    </>
  );
}
