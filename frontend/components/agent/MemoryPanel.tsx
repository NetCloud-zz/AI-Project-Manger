"use client";

import { useCallback, useState } from "react";
import { App, Button, Input, List, Modal } from "antd";
import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";

import { createMemory, deleteMemory, fetchMemories } from "@/services/memory";
import type { AgentMemory } from "@/types/memory";

type Props = {
  open: boolean;
  onClose: () => void;
};

export function MemoryPanel({ open, onClose }: Props) {
  const { message } = App.useApp();
  const [items, setItems] = useState<AgentMemory[]>([]);
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await fetchMemories(true));
    } catch {
      message.error("无法加载记忆");
    } finally {
      setLoading(false);
    }
  }, [message]);

  const onAdd = async () => {
    const content = draft.trim();
    if (!content) return;
    setSaving(true);
    try {
      await createMemory({ content, memory_type: "PREFERENCE" });
      setDraft("");
      message.success("已保存到记忆");
      await reload();
    } catch (err) {
      const detail =
        err && typeof err === "object" && "payload" in err
          ? String((err as { payload?: { detail?: string } }).payload?.detail ?? "")
          : "";
      message.error(detail || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const onRemove = async (id: number) => {
    try {
      await deleteMemory(id);
      await reload();
    } catch {
      message.error("删除失败");
    }
  };

  return (
    <Modal
      title="项目助手记忆"
      open={open}
      onCancel={onClose}
      footer={null}
      width={520}
      destroyOnHidden
      afterOpenChange={(visible) => {
        if (visible) void reload();
      }}
    >
      <p className="meta-line" style={{ marginBottom: 12 }}>
        仅保存你明确要求记住的偏好与关注重点。任务状态、截止日期等动态事实不会作为记忆权威来源。
      </p>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <Input.TextArea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="例如：以后项目汇报优先告诉我风险、延期和需要协调的问题"
          autoSize={{ minRows: 2, maxRows: 4 }}
        />
        <Button
          type="primary"
          icon={<PlusOutlined />}
          loading={saving}
          onClick={() => void onAdd()}
        >
          保存
        </Button>
      </div>
      <List
        loading={loading}
        locale={{ emptyText: "暂无记忆" }}
        dataSource={items}
        renderItem={(item) => (
          <List.Item
            actions={[
              <Button
                key="del"
                type="text"
                danger
                icon={<DeleteOutlined />}
                onClick={() => void onRemove(item.id)}
              />,
            ]}
          >
            <div>{item.content}</div>
          </List.Item>
        )}
      />
    </Modal>
  );
}
