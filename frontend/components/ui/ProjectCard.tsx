import Link from "next/link";

import { ProjectStatusTag, RiskTag } from "@/components/project/StatusTags";
import type { ProjectOwnerBrief } from "@/types/project";

type ProjectLike = {
  id?: number;
  project_id?: number;
  project_code: string;
  project_name: string;
  status: string;
  risk_level: string;
  owner?: string | ProjectOwnerBrief | null;
  current_focus?: string | null;
  next_deadline?: string | null;
};

type Props = {
  project: ProjectLike;
  href?: string;
};

function ownerLabel(owner: ProjectLike["owner"]): string | null {
  if (!owner) return null;
  if (typeof owner === "string") return owner;
  return owner.name;
}

export function ProjectCard({ project, href }: Props) {
  const id = project.id ?? project.project_id;
  const link = href ?? `/projects/${id}`;
  const owner = ownerLabel(project.owner);

  return (
    <Link href={link} className="app-card app-card--interactive list-link">
      <div className="entity-card__top">
        <div className="entity-card__code">{project.project_code}</div>
        <div className="chip-row chip-row--flush">
          <ProjectStatusTag status={project.status} />
          <RiskTag level={project.risk_level} />
        </div>
      </div>
      <div className="entity-card__name">{project.project_name}</div>
      {owner ? <div className="meta-line">负责人 · {owner}</div> : null}
      {project.current_focus ? (
        <div className="meta-line">当前重点 · {project.current_focus}</div>
      ) : null}
      {project.next_deadline ? (
        <div className="meta-line">下一节点 · {project.next_deadline}</div>
      ) : null}
    </Link>
  );
}
