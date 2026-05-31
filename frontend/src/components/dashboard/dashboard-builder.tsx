"use client";

import { useCallback, useEffect, useMemo, useState, type ComponentType, type ReactNode } from "react";
import dynamic from "next/dynamic";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

import { apiDelete, apiGet, apiPatch, apiPost } from "@/lib/api";
import type {
  ChartSpec,
  ChartSuggestionsResponse,
  Dashboard,
  DashboardListItem,
  FilterClause,
  FilterOptionsResponse,
  GridLayoutItem,
  Profile,
  ProfileEnvelope,
} from "@/types";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { ChartHandle } from "@/components/charts/chart";
import { ChartTile } from "./chart-tile";
import { ExportReport } from "./export-report";
import { FiltersBar } from "./filters-bar";
import { ManualBuilder } from "./manual-builder";
import { SaveLoad } from "./save-load";
import { SuggestionsGallery, suggestionKey } from "./suggestions-gallery";

// Minimal local prop type — @types/react-grid-layout exists but doesn't play
// well with `next/dynamic`'s prop-stripping. We re-state the few props we use.
interface GridProps {
  className?: string;
  cols: Record<string, number>;
  breakpoints: Record<string, number>;
  rowHeight: number;
  layouts: Record<string, GridLayoutItem[]>;
  onLayoutChange?: (layout: GridLayoutItem[]) => void;
  draggableHandle?: string;
  margin?: [number, number];
  isResizable?: boolean;
  isDraggable?: boolean;
  isBounded?: boolean;
  children?: ReactNode;
}

// react-grid-layout uses window at module-eval; ship it client-only via a
// dedicated wrapper that does the static namespace import. Resolving the
// (CJS-shaped) Responsive/WidthProvider symbols via runtime destructure has
// proven fragile across bundler versions — a static import in a "use client"
// module lets the bundler handle the interop natively and is much more
// stable. `ssr: false` keeps the bundle out of the server build.
const ResponsiveGridLayout = dynamic(
  () => import("./responsive-grid"),
  {
    ssr: false,
    loading: () => (
      <div className="text-xs text-[var(--color-muted)]">Loading grid…</div>
    ),
  },
) as unknown as ComponentType<GridProps>;

interface Props {
  datasetId: string;
  datasetName: string;
}

const GRID_COLS = { lg: 12, md: 10, sm: 6, xs: 4, xxs: 2 };
const GRID_BREAKPOINTS = { lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 };
const ROW_HEIGHT = 60;

function defaultLayoutFor(index: number): Omit<GridLayoutItem, "i"> {
  return {
    x: (index % 2) * 6,
    y: Math.floor(index / 2) * 5,
    w: 6,
    h: 5,
  };
}

interface AddedChart {
  key: string;
  spec: ChartSpec;
}

export function DashboardBuilder({ datasetId, datasetName }: Props) {
  const [versionId, setVersionId] = useState<string | null>(null);
  const [versionLabel, setVersionLabel] = useState<string>("");

  const [profile, setProfile] = useState<Profile | null>(null);
  const [suggestions, setSuggestions] = useState<ChartSuggestionsResponse | null>(null);
  const [filterOptions, setFilterOptions] = useState<FilterOptionsResponse | null>(null);
  const [filters, setFilters] = useState<FilterClause[]>([]);
  const [addedCharts, setAddedCharts] = useState<AddedChart[]>([]);
  const [gridLayout, setGridLayout] = useState<GridLayoutItem[]>([]);

  const [savedDashboards, setSavedDashboards] = useState<DashboardListItem[]>([]);
  const [name, setName] = useState<string>("Untitled dashboard");
  const [currentDashboardId, setCurrentDashboardId] = useState<string | null>(null);

  const [showBuilder, setShowBuilder] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // ----- bootstrap ----------------------------------------------------------
  useEffect(() => {
    apiGet<ChartSuggestionsResponse>(`/datasets/${datasetId}/chart-suggestions`)
      .then((r) => {
        setSuggestions(r);
        setVersionId(r.version_id);
        setVersionLabel(r.version_label);
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : String(e)));
    apiGet<FilterOptionsResponse>(`/datasets/${datasetId}/filter-options`)
      .then(setFilterOptions)
      .catch(() => setFilterOptions({ version_id: "", filters: [] }));
    apiGet<DashboardListItem[]>(`/dashboards?dataset_id=${datasetId}`)
      .then(setSavedDashboards)
      .catch(() => setSavedDashboards([]));
  }, [datasetId]);

  // Profile for the manual-builder column picker.
  useEffect(() => {
    if (!versionId) return;
    apiGet<ProfileEnvelope>(`/datasets/${datasetId}/profile?version_id=${versionId}`)
      .then((env) => {
        if (env.profile) setProfile(env.profile);
      })
      .catch(() => undefined);
  }, [datasetId, versionId]);

  // ----- chart add/remove ---------------------------------------------------
  const addChart = useCallback((spec: ChartSpec) => {
    setAddedCharts((prev) => {
      const key = suggestionKey(spec);
      if (prev.some((c) => c.key === key)) return prev;
      const next = [...prev, { key, spec }];
      setGridLayout((gl) => [...gl, { i: key, ...defaultLayoutFor(prev.length) }]);
      return next;
    });
  }, []);

  const removeChart = useCallback((key: string) => {
    setAddedCharts((prev) => prev.filter((c) => c.key !== key));
    setGridLayout((gl) => gl.filter((i) => i.i !== key));
  }, []);

  const editChart = useCallback((key: string, nextSpec: ChartSpec) => {
    setAddedCharts((prev) => prev.map((c) => (c.key === key ? { ...c, spec: nextSpec } : c)));
  }, []);

  const addedKeys = useMemo(() => new Set(addedCharts.map((c) => c.key)), [addedCharts]);

  // Phase 6 — chart-handle registry so the report can capture PNGs.
  const handlesRef = useMemo<Map<string, ChartHandle | null>>(() => new Map(), []);
  const makeRegisterHandle = useCallback(
    (key: string) => (handle: ChartHandle | null) => {
      if (handle) handlesRef.set(key, handle);
      else handlesRef.delete(key);
    },
    [handlesRef]
  );
  function chartsForReport() {
    return addedCharts.map((c) => ({
      key: c.key,
      spec: c.spec,
      handle: handlesRef.get(c.key) ?? null,
    }));
  }

  // ----- save / load --------------------------------------------------------
  async function saveDashboard() {
    const payload = {
      dataset_id: datasetId,
      name: name.trim() || "Untitled dashboard",
      layout: { items: gridLayout, filters },
      charts: addedCharts.map((c, i) => ({
        chart_type: c.spec.chart_type,
        config: c.spec,
        position: i,
      })),
    };
    if (currentDashboardId) {
      const r = await apiPatch<Dashboard>(`/dashboards/${currentDashboardId}`, {
        name: payload.name,
        layout: payload.layout,
        charts: payload.charts,
      });
      setCurrentDashboardId(r.id);
    } else {
      const r = await apiPost<Dashboard>("/dashboards", payload);
      setCurrentDashboardId(r.id);
    }
    const list = await apiGet<DashboardListItem[]>(`/dashboards?dataset_id=${datasetId}`);
    setSavedDashboards(list);
  }

  async function openDashboard(id: string) {
    const r = await apiGet<Dashboard>(`/dashboards/${id}`);
    setCurrentDashboardId(r.id);
    setName(r.name);
    const charts: AddedChart[] = r.charts
      .slice()
      .sort((a, b) => a.position - b.position)
      .map((c) => ({ key: suggestionKey(c.config), spec: c.config }));
    setAddedCharts(charts);
    const layout = r.layout as { items?: GridLayoutItem[]; filters?: FilterClause[] } | undefined;
    if (layout?.items && layout.items.length > 0) setGridLayout(layout.items);
    else setGridLayout(charts.map((c, i) => ({ i: c.key, ...defaultLayoutFor(i) })));
    setFilters(layout?.filters ?? []);
  }

  async function deleteDashboard(id: string) {
    await apiDelete(`/dashboards/${id}`);
    const list = await apiGet<DashboardListItem[]>(`/dashboards?dataset_id=${datasetId}`);
    setSavedDashboards(list);
    if (currentDashboardId === id) newDashboard();
  }

  function newDashboard() {
    setCurrentDashboardId(null);
    setName("Untitled dashboard");
    setAddedCharts([]);
    setGridLayout([]);
    setFilters([]);
  }

  // ----- render -------------------------------------------------------------
  return (
    <div className="space-y-6">
      <SaveLoad
        saved={savedDashboards}
        currentName={name}
        currentId={currentDashboardId}
        onNameChange={setName}
        onSave={saveDashboard}
        onOpen={openDashboard}
        onDelete={deleteDashboard}
        onNew={newDashboard}
      />

      <p className="text-xs text-[var(--color-muted)]">
        Built on the <span className="font-mono">{versionLabel || "…"}</span> version of this dataset.
        {versionLabel === "cleaned" && " Use the Clean page to add or remove preprocessing steps."}
      </p>

      {loadError && (
        <Card>
          <p className="text-sm text-[var(--color-danger)]">Couldn’t load dashboard: {loadError}</p>
        </Card>
      )}

      {/* KPI row */}
      {suggestions && suggestions.kpis.length > 0 && (
        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {suggestions.kpis.slice(0, 6).map((k, i) => {
            const spec: ChartSpec = {
              chart_type: "kpi",
              encoding: k.encoding,
              title: k.title,
              bins: null,
              top_n: null,
              filters: [],
            };
            return (
              <ChartTile
                key={`kpi-${i}`}
                datasetId={datasetId}
                versionId={versionId}
                spec={spec}
                filters={filters}
                height={80}
                showHeader={false}
              />
            );
          })}
        </section>
      )}

      {/* Filters */}
      <Card>
        <h2 className="mb-3 text-sm font-medium">Filters</h2>
        {filterOptions ? (
          <FiltersBar
            options={filterOptions.filters}
            value={filters}
            onChange={setFilters}
          />
        ) : (
          <p className="text-xs text-[var(--color-muted)]">Loading filter options…</p>
        )}
      </Card>

      {/* Suggestions gallery */}
      <Card>
        <header className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-medium">Suggestions</h2>
            <p className="text-xs text-[var(--color-muted)]">
              Best charts for this data, ranked by usefulness.
            </p>
          </div>
          <Button variant="secondary" onClick={() => setShowBuilder((b) => !b)}>
            {showBuilder ? "Hide manual builder" : "Manual builder"}
          </Button>
        </header>
        {suggestions ? (
          <SuggestionsGallery
            datasetId={datasetId}
            versionId={versionId}
            suggestions={suggestions.suggestions}
            filters={filters}
            addedKeys={addedKeys}
            onAdd={addChart}
          />
        ) : (
          <p className="text-xs text-[var(--color-muted)]">Loading suggestions…</p>
        )}
      </Card>

      {/* Manual builder */}
      {showBuilder && profile && (
        <Card>
          <h2 className="mb-3 text-sm font-medium">Manual chart builder</h2>
          <ManualBuilder
            datasetId={datasetId}
            versionId={versionId}
            columns={profile.columns}
            filters={filters}
            onAdd={addChart}
          />
        </Card>
      )}

      {/* Grid of added charts */}
      <section>
        <header className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium">
            Dashboard ({addedCharts.length} chart{addedCharts.length === 1 ? "" : "s"})
          </h2>
          <ExportReport
            datasetId={datasetId}
            datasetName={datasetName}
            versionLabel={versionLabel}
            cleaningStepCount={0}
            charts={chartsForReport()}
          />
        </header>
        {addedCharts.length === 0 ? (
          <Card>
            <p className="text-sm text-[var(--color-muted)]">
              No charts yet — add suggestions above, or open the manual builder.
            </p>
          </Card>
        ) : (
          <ResponsiveGridLayout
            className="layout"
            cols={GRID_COLS}
            breakpoints={GRID_BREAKPOINTS}
            rowHeight={ROW_HEIGHT}
            layouts={{ lg: gridLayout }}
            onLayoutChange={(layout: GridLayoutItem[]) => setGridLayout(layout)}
            draggableHandle=".drag-handle"
            margin={[12, 12]}
            isResizable
            isDraggable
            isBounded
          >
            {addedCharts.map((c) => (
              <div
                key={c.key}
                data-grid={gridLayout.find((g) => g.i === c.key) ?? { i: c.key, ...defaultLayoutFor(0) }}
              >
                <ChartTile
                  datasetId={datasetId}
                  versionId={versionId}
                  spec={c.spec}
                  filters={filters}
                  onRemove={() => removeChart(c.key)}
                  onEdit={(next) => editChart(c.key, next)}
                  columns={profile?.columns}
                  registerHandle={makeRegisterHandle(c.key)}
                />
              </div>
            ))}
          </ResponsiveGridLayout>
        )}
      </section>
    </div>
  );
}
