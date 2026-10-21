/*
 * Copyright (C) 2026 Wang Zheng Lab, Peking University
 *
 * This file is part of PrimateX and is licensed under the GNU Affero General
 * Public License v3.0 or later. See LICENSE and CITATION.cff.
 */

import type { ThemeConfig } from 'antd';

/**
 * Shared design tokens. Keep these values in sync with the CSS custom
 * properties in styles/app.css so antd controls and hand-written layout use
 * the same palette.
 */
export const colors = {
  bg: '#f6f7f9',
  surface: '#ffffff',
  border: '#e5e7eb',
  borderStrong: '#d1d5db',
  text: '#111827',
  text2: '#4b5563',
  text3: '#9ca3af',
  primary: '#2563eb',
  primaryHover: '#1d4ed8',
  primarySoft: '#eff4ff',
  ok: '#16a34a',
  warn: '#d97706',
  err: '#dc2626',
};

export const fontFamily =
  'Inter, "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, "Segoe UI", sans-serif';

export const appTheme: ThemeConfig = {
  token: {
    colorPrimary: colors.primary,
    colorInfo: colors.primary,
    colorSuccess: colors.ok,
    colorWarning: colors.warn,
    colorError: colors.err,
    colorText: colors.text,
    colorTextSecondary: colors.text2,
    colorTextTertiary: colors.text3,
    colorBorder: colors.borderStrong,
    colorBorderSecondary: colors.border,
    colorBgLayout: colors.bg,
    colorBgContainer: colors.surface,
    borderRadius: 7,
    borderRadiusLG: 10,
    fontFamily,
    fontSize: 14,
    controlHeight: 34,
    boxShadow: '0 1px 2px rgba(16, 24, 40, 0.04)',
    boxShadowSecondary: '0 8px 24px rgba(16, 24, 40, 0.10)',
  },
  components: {
    Card: {
      headerFontSize: 14,
      headerHeight: 48,
      paddingLG: 20,
    },
    Button: {
      fontWeight: 500,
      primaryShadow: 'none',
      defaultShadow: 'none',
    },
    Table: {
      headerBg: '#fafafa',
      headerColor: colors.text3,
      headerSplitColor: 'transparent',
      rowHoverBg: '#f9fafb',
    },
    Tabs: {
      horizontalItemPadding: '10px 0',
    },
    Segmented: {
      itemSelectedColor: colors.text,
    },
    Menu: {
      itemBorderRadius: 6,
      itemSelectedBg: colors.primarySoft,
      itemSelectedColor: colors.primary,
    },
    Tag: {
      defaultBg: '#f3f4f6',
    },
  },
};
