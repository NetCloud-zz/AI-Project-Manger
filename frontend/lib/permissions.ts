import type { UserProfile } from "@/types/auth";
import type { Project } from "@/types/project";

type ProjectOwnerRef = Pick<Project, "owner_id" | "owners">;
type UserRef = Pick<UserProfile, "id" | "role">;

/** True when the user is primary owner or listed in project.owners. */
export function isProjectOwner(
  user: UserRef | null | undefined,
  project: ProjectOwnerRef | null | undefined,
): boolean {
  if (!user || !project) return false;
  if (project.owner_id === user.id) return true;
  return (project.owners ?? []).some((owner) => owner.id === user.id);
}

/**
 * UI gate matching backend can_modify_project:
 * ADMIN, or any non-EXECUTIVE user who owns the project.
 */
export function canManageProject(
  user: UserRef | null | undefined,
  project: ProjectOwnerRef | null | undefined,
): boolean {
  if (!user) return false;
  if (user.role === "ADMIN") return true;
  if (user.role === "EXECUTIVE") return false;
  return isProjectOwner(user, project);
}

/** Task status / progress: admin, task owner, or project manager. */
export function canActOnTask(
  user: UserRef | null | undefined,
  taskOwnerId: number | null | undefined,
  managesProject: boolean,
): boolean {
  if (!user) return false;
  if (user.role === "ADMIN") return true;
  if (taskOwnerId != null && taskOwnerId === user.id) return true;
  return managesProject;
}
