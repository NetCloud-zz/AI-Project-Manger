"use client";

import { useCallback, useEffect, useState } from "react";
import { Button, Empty } from "antd";
import { ReloadOutlined } from "@ant-design/icons";

import { AppCard } from "@/components/common/AppCard";
import { AdviceCard } from "@/components/risk/AdviceCard";
import { listIssueAdvice } from "@/services/risks";
import type { AdviceRecord } from "@/types/advice";

/** The full advice record, so adoption happens against current data. */
export function AdviceListCard({ issueId }: { issueId: number }) {
  const [items, setItems] = useState<AdviceRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = useCallback(
    () =>
      listIssueAdvice(issueId)
        .then((result) => {
          setItems(result.items);
          setFailed(false);
        })
        .catch(() => setFailed(true))
        .finally(() => setLoading(false)),
    [issueId],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const latest = items.filter((item) => item.status !== "SUPERSEDED").slice(0, 2);

  return (
    <AppCard
      plain
      stack="sm"
      title="问题建议"
      extra={
        <Button
          size="small"
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={() => {
            setLoading(true);
            void load();
          }}
        />
      }
    >
      {failed ? (
        <p className="meta-line meta-line--danger">无法读取建议记录，请刷新或到项目页面查看。</p>
      ) : latest.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={loading ? "读取中…" : "建议还在生成，稍后刷新查看"}
        />
      ) : (
        latest.map((record) => (
          <AdviceCard
            key={record.id}
            record={record}
            onChanged={(next) =>
              setItems((prev) => prev.map((item) => (item.id === next.id ? next : item)))
            }
          />
        ))
      )}
    </AppCard>
  );
}
