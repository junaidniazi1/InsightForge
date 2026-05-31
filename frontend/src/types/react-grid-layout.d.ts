/**
 * Local type declarations for react-grid-layout@1.5.2.
 *
 * react-grid-layout v1 ships no bundled types, and the `@types/react-grid-layout`
 * package on npm is now an empty deprecation stub (installing it makes
 * `tsc` fail with "Cannot find type definition file for 'react-grid-layout'").
 * So we declare the small surface this app actually uses, by hand.
 *
 * Pinned intentionally to v1 — do NOT upgrade to v2.x, which dropped the
 * `WidthProvider` HOC. See components/dashboard/responsive-grid.tsx.
 */
declare module "react-grid-layout" {
  import type { ComponentType, ReactNode, CSSProperties } from "react";

  export interface LayoutItem {
    i: string;
    x: number;
    y: number;
    w: number;
    h: number;
    minW?: number;
    maxW?: number;
    minH?: number;
    maxH?: number;
    static?: boolean;
    isDraggable?: boolean;
    isResizable?: boolean;
  }

  export type Layout = LayoutItem[];

  export interface Layouts {
    [breakpoint: string]: Layout;
  }

  export interface CoreProps {
    className?: string;
    style?: CSSProperties;
    rowHeight?: number;
    margin?: [number, number];
    containerPadding?: [number, number];
    isDraggable?: boolean;
    isResizable?: boolean;
    isBounded?: boolean;
    draggableHandle?: string;
    draggableCancel?: string;
    compactType?: "vertical" | "horizontal" | null;
    preventCollision?: boolean;
    useCSSTransforms?: boolean;
    autoSize?: boolean;
    children?: ReactNode;
  }

  export interface GridLayoutProps extends CoreProps {
    cols?: number;
    width?: number;
    layout?: Layout;
    onLayoutChange?: (layout: Layout) => void;
  }

  export interface ResponsiveProps extends CoreProps {
    breakpoints?: { [breakpoint: string]: number };
    cols?: { [breakpoint: string]: number };
    layouts?: Layouts;
    width?: number;
    onLayoutChange?: (currentLayout: Layout, allLayouts: Layouts) => void;
    onBreakpointChange?: (newBreakpoint: string, newCols: number) => void;
  }

  export interface WidthProviderProps {
    measureBeforeMount?: boolean;
  }

  export const Responsive: ComponentType<ResponsiveProps>;

  export function WidthProvider<P>(
    component: ComponentType<P>,
  ): ComponentType<P & WidthProviderProps>;

  const GridLayout: ComponentType<GridLayoutProps>;
  export default GridLayout;
}
