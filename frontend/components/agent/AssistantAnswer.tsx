"use client";

import { ExplanationDisclosure } from "@/components/feedback/ExplanationDisclosure";
import { MarkdownRenderer } from "@/components/agent/MarkdownRenderer";
import {
  buildAnswerPreview,
  isLongAssistantAnswer,
} from "@/lib/answer-preview";

type Props = {
  content: string;
  /** When streaming, never collapse to avoid layout jump. */
  streaming?: boolean;
  /** Stable id so expand state survives parent re-renders of the same message. */
  messageKey: string | number;
};

/**
 * Renders assistant Markdown with an optional collapsed preview for long replies.
 * Copy actions should still use the full `content` from the parent.
 */
export function AssistantAnswer({ content, streaming = false, messageKey }: Props) {
  if (streaming || !isLongAssistantAnswer(content)) {
    return <MarkdownRenderer content={content} />;
  }

  const { preview, remainingBlocks } = buildAnswerPreview(content);
  if (remainingBlocks === 0 || preview === content) {
    return <MarkdownRenderer content={content} />;
  }

  return (
    <ExplanationDisclosure
      key={String(messageKey)}
      defaultOpen={false}
      expandCount={remainingBlocks}
      summary={
        <div>
          <p className="meta-line">回答预览</p>
          <MarkdownRenderer content={preview} />
        </div>
      }
    >
      <MarkdownRenderer content={content} />
    </ExplanationDisclosure>
  );
}
