"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { Button, Modal } from "antd";
import { BarChartOutlined } from "@ant-design/icons";

import { AppCard } from "@/components/common/AppCard";
import { LoadingState } from "@/components/feedback/LoadingState";

const ProjectGantt = dynamic(
  () => import("@/components/gantt/ProjectGantt").then((mod) => mod.ProjectGantt),
  { ssr: false, loading: () => <LoadingState tip="加载甘特图组件…" /> },
);

const GANTT_MODAL_WIDTH = 1600;

export function ProjectGanttPanel({ projectId }: { projectId: number }) {
  const [open, setOpen] = useState(true);

  return (
    <>
      <AppCard stack="md">
        <Button type="primary" icon={<BarChartOutlined />} onClick={() => setOpen(true)}>
          打开甘特图
        </Button>
      </AppCard>

      <Modal
        title={null}
        open={open}
        onCancel={() => setOpen(false)}
        footer={null}
        closable={false}
        centered
        destroyOnHidden
        width={GANTT_MODAL_WIDTH}
        className="gantt-modal"
        styles={{
          container: {
            width: GANTT_MODAL_WIDTH,
            maxWidth: "calc(100vw - 32px)",
            height: "88vh",
            maxHeight: "88vh",
            padding: 0,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          },
          body: {
            flex: 1,
            minHeight: 0,
            height: "100%",
            padding: 0,
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
          },
        }}
      >
        <div className="gantt-modal__body">
          <ProjectGantt projectId={projectId} onClose={() => setOpen(false)} />
        </div>
      </Modal>
    </>
  );
}
