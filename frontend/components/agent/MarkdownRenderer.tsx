"use client";

import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

type Props = {
  content: string;
  className?: string;
};

function isSafeHref(href: string | undefined): href is string {
  if (!href) return false;
  const trimmed = href.trim();
  if (trimmed.startsWith("/") && !trimmed.startsWith("//")) return true;
  if (trimmed.startsWith("#")) return true;
  try {
    const url = new URL(trimmed, "https://example.invalid");
    return url.protocol === "http:" || url.protocol === "https:" || url.protocol === "mailto:";
  } catch {
    return false;
  }
}

function isInternalHref(href: string): boolean {
  if (href.startsWith("/") && !href.startsWith("//")) return true;
  if (href.startsWith("#")) return true;
  if (typeof window === "undefined") return false;
  try {
    const url = new URL(href, window.location.origin);
    return url.origin === window.location.origin;
  } catch {
    return false;
  }
}

/**
 * Safe Markdown renderer for assistant replies.
 * Uses react-markdown (no dangerouslySetInnerHTML).
 * Same-origin paths stay in-app; external links open in a new tab.
 */
export function MarkdownRenderer({ content, className }: Props) {
  const components: Components = {
    a: ({ href, children }) => {
      if (!isSafeHref(href)) {
        return <span>{children}</span>;
      }
      if (isInternalHref(href)) {
        return (
          <Link href={href} className="md-link md-link--internal">
            {children}
          </Link>
        );
      }
      return (
        <a href={href} target="_blank" rel="noopener noreferrer" className="md-link md-link--external">
          {children}
        </a>
      );
    },
    table: ({ children }) => (
      <div className="md-table-wrap">
        <table>{children}</table>
      </div>
    ),
  };

  return (
    <div className={className ? `md-content ${className}` : "md-content"}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
