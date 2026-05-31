"use client";

import type { ComponentType } from "react";
import { Responsive, WidthProvider } from "react-grid-layout";

/**
 * Client-only `WidthProvider(Responsive)` from react-grid-layout.
 *
 * Pinned to react-grid-layout@1.5.2 — the stable v1 line whose package root
 * exports the canonical named values `{ Responsive, WidthProvider }`.
 *
 * DO NOT upgrade to react-grid-layout v2.x. The v2 rewrite reorganised the
 * module: the root entry exports only types plus a `default` grid, and the
 * `WidthProvider` HOC was removed in favour of a `useContainerWidth` hook
 * (verified: at v2 the root `WidthProvider` export is `undefined`). That shape
 * change is exactly what broke the dashboard with "Responsive or WidthProvider
 * missing on module". v1.5.2 keeps the documented, ecosystem-standard API this
 * whole component tree relies on.
 *
 * This module is imported via `next/dynamic({ ssr: false })` from
 * dashboard-builder.tsx because RGL touches `window` at module-eval and can't
 * render on the server.
 */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ResponsiveGridLayout = WidthProvider(Responsive) as ComponentType<any>;

export default ResponsiveGridLayout;
