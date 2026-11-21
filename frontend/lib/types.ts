// Mirrors backend/app/schemas — keep in sync.

export interface ServiceStatus {
  ok: boolean;
  detail: string;
}

export interface HealthReport {
  status: "ok" | "degraded";
  services: Record<string, ServiceStatus>;
  version: string;
}
