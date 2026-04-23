const API_BASE = import.meta.env.VITE_API_BASE ?? "";

function authHeader(): HeadersInit {
  const token = localStorage.getItem("access_token");
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeader(),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
      else if (Array.isArray(body?.detail)) detail = body.detail.map((x: { msg?: string }) => x.msg).join("; ");
    } catch {
      /* ignore */
    }
    throw new Error(detail || `Request failed (${res.status})`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export type MeUser = {
  id: string;
  email: string;
  full_name: string;
  role: string;
};

export type MeResponse = MeUser & { setup?: unknown };

export type Company = {
  id: string;
  company_name: string;
  linkedin_url: string | null;
  blacklisted: boolean;
  industry: string | null;
  company_size: string | null;
  website: string | null;
  phone: string | null;
  about_us: string | null;
  displayed_description: string | null;
  displayed_keywords: string | null;
  scraped_at: string;
};

/** Response from POST /api/admin/companies/{id}/ai-display */
export type CompanyDisplayAIResponse = {
  success: boolean;
  description: string;
  keywords: string[];
  saved: boolean;
  company: Company | null;
};

export type CompanyDisplayAIJobQueued = {
  job_id: string;
  status: string;
};

export type CompanyDisplayAIJobStatus = {
  job_id: string;
  status: string;
  only_missing_display: boolean;
  company_ids: string[];
  limit: number | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  processed: number;
  updated: number;
  skipped: number;
  failed: number;
  declined: number;
  error: string | null;
};

export type CompanyAboutBackfillRowResult = {
  company_id: string;
  company_name: string;
  source_url: string | null;
  status: string;
  reason: string | null;
  saved_chars: number | null;
};

export type CompanyAboutBackfillResponse = {
  processed: number;
  updated: number;
  skipped: number;
  failed: number;
  results: CompanyAboutBackfillRowResult[];
};

export type CompanyAboutBackfillJobQueued = {
  job_id: string;
  status: string;
};

export type CompanyAboutBackfillJobStatus = {
  job_id: string;
  status: string;
  only_missing: boolean;
  company_ids: string[];
  limit: number | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  processed: number;
  updated: number;
  skipped: number;
  failed: number;
  error: string | null;
};

export type Job = {
  id: string;
  company_id: string | null;
  company_name: string | null;
  job_id: string;
  job_title: string | null;
  posted_date: string | null;
  job_description: string | null;
  extra_details: string | null;
  job_url: string;
  keyword: string | null;
  displayed_description: string | null;
  displayed_keywords: string | null;
  scraped_at: string;
};

/** Response from POST /api/admin/jobs/{id}/ai-display */
export type JobDisplayAIResponse = {
  success: boolean;
  description: string;
  keywords: string[];
  saved: boolean;
  job: Job | null;
};

export type JobDisplayAIJobQueued = {
  job_id: string;
  status: string;
};

export type JobDisplayAIJobStatus = {
  job_id: string;
  status: string;
  only_missing_display: boolean;
  job_ids: string[];
  limit: number | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  processed: number;
  updated: number;
  skipped: number;
  failed: number;
  declined: number;
  error: string | null;
};

export type Community = {
  id: string;
  name: string;
  description: string;
  website: string | null;
  keywords: string | null;
  created_by_user_id: string | null;
  created_at: string;
};

export type CommunityEvent = {
  id: string;
  community_id: string;
  name: string;
  event_at: string;
  location: string;
  description: string;
  website: string | null;
  keywords: string | null;
  created_at: string;
};

export type LinkedInScrapeProgress = {
  total_locations: number;
  locations_completed: number;
  current_location: string | null;
  pages_processed: number;
  job_urls_found: number;
  jobs_scraped: number;
  companies_discovered: number;
  companies_scraped: number;
  last_message: string;
  logs: string[];
};

export type LinkedInScrapeRequest = {
  keywords: string[];
  locations: string[];
  jobs_per_location: number | null;
  delay_seconds: number;
  session_path: string;
  output_dir: string;
  verbose: boolean;
};

export type LinkedInScrapeJobStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelling"
  | "cancelled";

export type LinkedInScrapeJob = {
  id: string;
  status: LinkedInScrapeJobStatus;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  request: LinkedInScrapeRequest;
  progress: LinkedInScrapeProgress;
  output_jobs_xlsx: string | null;
  output_companies_xlsx: string | null;
  error: string | null;
};

export type StartLinkedInScrapeResponse = {
  job_id: string;
  status: string;
};

export type ImportUrlResultRow = {
  url: string;
  status: "saved" | "skipped" | "error";
  job_id: string | null;
  job_title: string | null;
  reason: string | null;
};

export type ImportUrlsResponse = {
  saved: number;
  skipped: number;
  errors: number;
  results: ImportUrlResultRow[];
};

export type VolunteeringEvent = {
  id: string;
  event_url: string;
  title: string | null;
  subtitle: string | null;
  organizer: string | null;
  organizer_website: string | null;
  description: string | null;
  duration_dates: string | null;
  days: string | null;
  keywords: string | null;
  scraped_at: string;
};

export type VolunteeringKeywordAIResponse = {
  success: boolean;
  keyword: string;
  saved: boolean;
  event: VolunteeringEvent | null;
};

export type NahnoImportResultRow = {
  event_url: string;
  status: "saved" | "skipped" | "error";
  title: string | null;
  reason: string | null;
};

export type NahnoImportResponse = {
  saved: number;
  skipped: number;
  errors: number;
  results: NahnoImportResultRow[];
};
