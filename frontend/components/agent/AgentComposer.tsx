"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type FocusEvent,
  type KeyboardEvent,
} from "react";
import { Button, Input } from "antd";
import type { TextAreaRef } from "antd/es/input/TextArea";
import { SendOutlined, StopOutlined } from "@ant-design/icons";

import { ActionGroup } from "@/components/common/ActionGroup";

export type AgentComposerHandle = {
  focus: (options?: FocusOptions) => void;
  blur: () => void;
  getTextarea: () => HTMLTextAreaElement | null;
};

type Props = {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  /** True while a generation is in flight (disables send, keeps draft editable). */
  sending: boolean;
  showStop: boolean;
  disabled?: boolean;
  maxLength: number;
  placeholder?: string;
  /** Fires when focus leaves the composer shell (not send/stop within it). */
  onLeaveComposer?: () => void;
  /** Fires when focus enters the composer shell. */
  onEnterComposer?: () => void;
};

function resolveRem(): number {
  if (typeof document === "undefined") return 16;
  return parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
}

/**
 * Chat composer: full-width textarea above send/stop actions.
 * Desktop defaults to ~3 rows; narrow containers ~2; max ~8.
 */
export const AgentComposer = forwardRef<AgentComposerHandle, Props>(
  function AgentComposer(
    {
      value,
      onChange,
      onSend,
      onStop,
      sending,
      showStop,
      disabled = false,
      maxLength,
      placeholder = "输入问题，例如：PRJ-1001 现在怎么样？",
      onLeaveComposer,
      onEnterComposer,
    },
    ref,
  ) {
    const rootRef = useRef<HTMLDivElement>(null);
    const textAreaRef = useRef<TextAreaRef>(null);
    const [minRows, setMinRows] = useState(2);

    useImperativeHandle(ref, () => ({
      focus: (options) => {
        textAreaRef.current?.focus({ preventScroll: options?.preventScroll });
      },
      blur: () => {
        textAreaRef.current?.blur();
      },
      getTextarea: () =>
        textAreaRef.current?.resizableTextArea?.textArea ?? null,
    }));

    useEffect(() => {
      const el = rootRef.current;
      if (!el || typeof ResizeObserver === "undefined") return;
      const update = (width: number) => {
        // Narrow content column → 2 rows; otherwise desktop default 3.
        setMinRows(width < 36 * resolveRem() ? 2 : 3);
      };
      update(el.getBoundingClientRect().width);
      const observer = new ResizeObserver((entries) => {
        const width = entries[0]?.contentRect.width;
        if (width != null) update(width);
      });
      observer.observe(el);
      return () => observer.disconnect();
    }, []);

    const trimmedEmpty = !value.trim();
    const sendDisabled = disabled || sending || trimmedEmpty;

    const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key !== "Enter" || event.shiftKey) return;
      if (event.nativeEvent.isComposing || event.keyCode === 229) return;
      event.preventDefault();
      if (!sendDisabled) onSend();
    };

    const handleFocusOut = (event: FocusEvent<HTMLDivElement>) => {
      const next = event.relatedTarget as Node | null;
      if (next && rootRef.current?.contains(next)) return;
      // Send → Stop swap or brief body focus should not count as leaving.
      requestAnimationFrame(() => {
        const active = document.activeElement;
        if (rootRef.current?.contains(active)) return;
        onLeaveComposer?.();
      });
    };

    return (
      <div
        ref={rootRef}
        className="agent-composer"
        onFocus={onEnterComposer}
        onBlur={handleFocusOut}
      >
        <Input.TextArea
          ref={textAreaRef}
          className="agent-composer__textarea"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          autoSize={{ minRows, maxRows: 8 }}
          maxLength={maxLength}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          aria-label="消息输入"
        />
        <div className="agent-composer__footer">
          <ActionGroup className="agent-composer__actions">
            {showStop ? (
              <Button danger icon={<StopOutlined />} onClick={onStop}>
                停止
              </Button>
            ) : (
              <Button
                type="primary"
                icon={<SendOutlined />}
                aria-label="发送消息"
                onClick={onSend}
                disabled={sendDisabled}
              >
                发送
              </Button>
            )}
          </ActionGroup>
        </div>
      </div>
    );
  },
);
