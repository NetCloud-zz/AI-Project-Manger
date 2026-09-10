"use client";

import { Pagination } from "antd";

import { PAGE_SIZE_OPTIONS } from "@/hooks/usePagedList";
import { useViewport } from "@/hooks/useViewport";

type Props = {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
};

export function AppPagination({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
}: Props) {
  const viewport = useViewport();
  const isMobile = viewport === "mobile";

  if (total <= Math.min(...PAGE_SIZE_OPTIONS)) return null;

  return (
    <div className="app-pagination">
      <Pagination
        current={page}
        pageSize={pageSize}
        total={total}
        size={isMobile ? "small" : undefined}
        simple={isMobile}
        showSizeChanger={!isMobile}
        pageSizeOptions={PAGE_SIZE_OPTIONS}
        showTotal={isMobile ? undefined : (count) => `共 ${count} 条`}
        onChange={(nextPage, nextSize) => {
          if (nextSize !== pageSize) {
            onPageSizeChange(nextSize);
            return;
          }
          onPageChange(nextPage);
        }}
      />
    </div>
  );
}
