// Stub types for libs that don't ship their own TS declarations.

declare module "plotly.js-dist-min" {
  // The min build re-exports the full Plotly API; we only call .toImage().
  // Keep this `any` — Phase 8 polish can replace with @types/plotly.js if needed.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const Plotly: any;
  export default Plotly;
}
