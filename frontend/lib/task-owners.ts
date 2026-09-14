import type { Task, TaskOwnerBrief } from "@/types/task";

/** Display label for one or more equal task owners. */
export function taskOwnerLabel(task: Pick<Task, "owner" | "owners" | "owner_id">): string {
  const people: TaskOwnerBrief[] =
    task.owners && task.owners.length > 0
      ? task.owners
      : task.owner
        ? [task.owner]
        : [];
  const names = people.map((person) => person.name).filter(Boolean);
  if (names.length > 0) return names.join("、");
  return task.owner_id == null ? "" : String(task.owner_id);
}
