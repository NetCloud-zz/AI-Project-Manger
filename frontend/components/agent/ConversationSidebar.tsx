"use client";

import { Button, Dropdown, Input, Modal, Switch } from "antd";
import {
  EditOutlined,
  InboxOutlined,
  MoreOutlined,
  PlusOutlined,
  UndoOutlined,
} from "@ant-design/icons";

import type { AgentConversation } from "@/types/agent";

type Props = {
  conversations: AgentConversation[];
  activeId: number | null;
  loading?: boolean;
  searchQuery: string;
  onSearchQuery: (value: string) => void;
  showArchived: boolean;
  onShowArchived: (value: boolean) => void;
  onSelect: (id: number) => void;
  onCreate: () => void;
  onRename: (id: number, title: string) => void;
  onArchive: (id: number) => void;
  onRestore: (id: number) => void;
};

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  const now = new Date();
  const sameDay =
    date.getFullYear() == now.getFullYear() &&
    date.getMonth() == now.getMonth() &&
    date.getDate() == now.getDate();
  if (sameDay) {
    return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

export function ConversationSidebar({
  conversations,
  activeId,
  searchQuery,
  onSearchQuery,
  showArchived,
  onShowArchived,
  onSelect,
  onCreate,
  onRename,
  onArchive,
  onRestore,
}: Props) {
  const promptRename = (item: AgentConversation) => {
    let next = item.title;
    Modal.confirm({
      title: "重命名对话",
      content: (
        <Input
          defaultValue={item.title}
          maxLength={200}
          onChange={(event) => {
            next = event.target.value;
          }}
        />
      ),
      okText: "保存",
      onOk: () => {
        const trimmed = next.trim();
        if (trimmed && trimmed !== item.title) onRename(item.id, trimmed);
      },
    });
  };

  return (
    <aside className="agent-sidebar">
      <div className="agent-sidebar__top">
        <Button type="primary" block icon={<PlusOutlined />} onClick={onCreate}>
          新对话
        </Button>
        <Input.Search
          allowClear
          placeholder="搜索对话"
          value={searchQuery}
          onChange={(event) => onSearchQuery(event.target.value)}
          aria-label="搜索对话"
        />
        <label className="agent-sidebar__archive-toggle">
          <Switch size="small" checked={showArchived} onChange={onShowArchived} />
          <span>归档</span>
        </label>
      </div>
      <div className="agent-sidebar__list">
        {conversations.length === 0 ? (
          <p className="meta-line agent-sidebar__empty">
            {showArchived ? "暂无归档对话" : "暂无对话"}
          </p>
        ) : (
          conversations.map((item) => {
            const isActive = item.id === activeId;
            return (
              <div
                key={item.id}
                className={`agent-sidebar__item${isActive ? " is-active" : ""}`}
              >
                <button
                  type="button"
                  className="agent-sidebar__item-main"
                  onClick={() => onSelect(item.id)}
                >
                  <span className="agent-sidebar__title">{item.title}</span>
                  <span className="agent-sidebar__time">
                    {formatWhen(item.last_message_at ?? item.updated_at)}
                  </span>
                </button>
                <Dropdown
                  menu={{
                    items: showArchived
                      ? [
                          {
                            key: "restore",
                            icon: <UndoOutlined />,
                            label: "恢复",
                            onClick: () => onRestore(item.id),
                          },
                        ]
                      : [
                          {
                            key: "rename",
                            icon: <EditOutlined />,
                            label: "重命名",
                            onClick: () => promptRename(item),
                          },
                          {
                            key: "archive",
                            icon: <InboxOutlined />,
                            label: "归档",
                            onClick: () => onArchive(item.id),
                          },
                        ],
                  }}
                  trigger={["click"]}
                >
                  <button
                    type="button"
                    className="agent-sidebar__more"
                    aria-label="更多操作"
                    onClick={(event) => event.stopPropagation()}
                  >
                    <MoreOutlined />
                  </button>
                </Dropdown>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
