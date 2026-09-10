export type ComponentStatus = "up" | "down" | "not_configured";

export interface DependencyHealth {
  status: ComponentStatus;
  detail: string | null;
}

export interface HealthResponse {
  status: "ok";
  app: string;
  version: string;
  environment: string;
}

export interface ReadinessResponse {
  status: "ok" | "degraded";
  app: string;
  version: string;
  environment: string;
  dependencies: Record<string, DependencyHealth>;
}
