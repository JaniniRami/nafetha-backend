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
  scraped_at: string;
};

export type Job = {
  id: string;
  company_id: string | null;
  job_id: string;
  job_title: string | null;
  company_linkedin_url: string | null;
  posted_date: string | null;
  job_description: string | null;
  linkedin_url: string;
  seed_location: string | null;
  keyword: string | null;
  scraped_at: string;
};

export type Community = {
  id: string;
  name: string;
  description: string;
  website: string | null;
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
