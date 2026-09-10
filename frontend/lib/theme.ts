import type { ThemeConfig } from "antd";

const FONT_FAMILY =
  '"PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';

/** Shared with the CSS custom properties in globals.css. */
const PALETTE = {
  primary: "#0b5cab",
  success: "#059669",
  warning: "#d97706",
  error: "#dc2626",
  text: "#1a2332",
  textSecondary: "#5c6b7f",
  border: "#e2e8f0",
  bgLayout: "#eef2f7",
  bgContainer: "#ffffff",
} as const;

const RADIUS = { base: 8, lg: 12, sm: 6 } as const;

function buildTheme(controlHeight: number): ThemeConfig {
  const controlHeightSM = Math.round(controlHeight * 0.78);
  const controlHeightLG = Math.round(controlHeight * 1.14);

  return {
    token: {
      colorPrimary: PALETTE.primary,
      colorSuccess: PALETTE.success,
      colorWarning: PALETTE.warning,
      colorError: PALETTE.error,
      colorText: PALETTE.text,
      colorTextSecondary: PALETTE.textSecondary,
      colorBorder: PALETTE.border,
      colorBgLayout: PALETTE.bgLayout,
      colorBgContainer: PALETTE.bgContainer,
      borderRadius: RADIUS.base,
      borderRadiusLG: RADIUS.lg,
      borderRadiusSM: RADIUS.sm,
      fontSize: 14,
      fontFamily: FONT_FAMILY,
      controlHeight,
      controlHeightSM,
      controlHeightLG,
    },
    components: {
      Button: { controlHeight, controlHeightSM, controlHeightLG, fontWeight: 500 },
      Input: { controlHeight, controlHeightSM, controlHeightLG },
      InputNumber: { controlHeight, controlHeightSM, controlHeightLG },
      Select: { controlHeight, controlHeightSM, controlHeightLG },
      DatePicker: { controlHeight, controlHeightSM, controlHeightLG },
      Segmented: { controlHeight, controlHeightSM, controlHeightLG },
      Pagination: { controlHeight, controlHeightSM },
      Card: { borderRadiusLG: RADIUS.lg, paddingLG: 16 },
      Table: {
        headerBg: "#f7f9fc",
        rowHoverBg: "#f2f6fb",
        cellPaddingBlock: 12,
        cellPaddingInline: 16,
        borderRadius: RADIUS.lg,
      },
      Form: { itemMarginBottom: 16, labelColor: PALETTE.textSecondary },
      Tag: { borderRadiusSM: RADIUS.sm },
      Modal: { borderRadiusLG: RADIUS.lg },
      Drawer: { paddingLG: 20 },
    },
  };
}

/**
 * 44px meets the WCAG 2.1 minimum touch target; pointer devices get the denser
 * 36px control so desktop pages do not look oversized.
 */
export const mobileTheme = buildTheme(44);
export const desktopTheme = buildTheme(36);
