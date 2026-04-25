import { useEffect, useMemo, useRef, useState } from "react";

import { useI18n } from "../../app/i18n";
import { KgGraphResponse } from "../../lib/api/types";

type KnowledgeGraphViewProps = {
  graph: KgGraphResponse;
  mode: "overview" | "run_path";
};

const kindStyles: Record<string, { backgroundColor: string; lineColor?: string; shape?: string }> = {
  workflow_pattern: { backgroundColor: "#1e7b80", shape: "round-rectangle" },
  algorithm: { backgroundColor: "#d97924", shape: "ellipse" },
  data_source: { backgroundColor: "#45637d", shape: "diamond" },
  task: { backgroundColor: "#5f7a61", shape: "hexagon" },
};

const MIN_GRAPH_ZOOM = 0.45;
const MAX_GRAPH_ZOOM = 2.4;

function clampGraphZoom(level: number) {
  return Math.min(MAX_GRAPH_ZOOM, Math.max(MIN_GRAPH_ZOOM, level));
}

function normalizeWheelDelta(deltaY: number, deltaMode: number) {
  if (deltaMode === 1) {
    return deltaY * 16;
  }
  if (deltaMode === 2) {
    return deltaY * 120;
  }
  return deltaY;
}

function computeNextZoomLevel(currentZoom: number, deltaY: number, deltaMode: number) {
  const normalizedDelta = Math.max(-160, Math.min(160, normalizeWheelDelta(deltaY, deltaMode)));
  const zoomFactor = Math.exp(-normalizedDelta * 0.0015);
  return clampGraphZoom(currentZoom * zoomFactor);
}

function legendLabelFor(kind: string, labels: ReturnType<typeof useI18n>["copy"]["kgPage"]["legend"]) {
  switch (kind) {
    case "workflow_pattern":
      return labels.workflowPattern;
    case "algorithm":
      return labels.algorithm;
    case "data_source":
      return labels.dataSource;
    case "task":
      return labels.task;
    default:
      return kind;
  }
}

export function KnowledgeGraphView({ graph, mode }: KnowledgeGraphViewProps) {
  const { copy } = useI18n();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<any | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">(
    graph.nodes.length ? "loading" : "idle",
  );
  const [zoomLevel, setZoomLevel] = useState(100);

  const legendKinds = useMemo(
    () => Array.from(new Set(graph.nodes.map((node) => node.kind))),
    [graph.nodes],
  );

  function syncZoom(instance?: any) {
    const nextZoom = instance?.zoom?.() ?? cyRef.current?.zoom?.() ?? 1;
    setZoomLevel(Math.round(nextZoom * 100));
  }

  function fitView() {
    const instance = cyRef.current;
    if (!instance) {
      return;
    }
    instance.fit(instance.elements(), 40);
    syncZoom(instance);
  }

  function nudgeZoom(direction: "in" | "out") {
    const instance = cyRef.current;
    if (!instance) {
      return;
    }
    const currentZoom = instance.zoom();
    const nextZoom = clampGraphZoom(currentZoom * (direction === "in" ? 1.14 : 1 / 1.14));
    instance.zoom(nextZoom);
    syncZoom(instance);
  }

  useEffect(() => {
    if (containerRef.current === null || graph.nodes.length === 0) {
      setStatus("idle");
      cyRef.current = null;
      setZoomLevel(100);
      return;
    }
    if (typeof window === "undefined" || /jsdom/i.test(window.navigator.userAgent)) {
      setStatus("ready");
      setZoomLevel(100);
      return;
    }

    let isCancelled = false;
    let instance: { destroy: () => void } | null = null;
    let removeWheelListener: (() => void) | null = null;
    let resizeObserver: ResizeObserver | null = null;

    async function mountGraph() {
      setStatus("loading");
      try {
        const [{ default: cytoscape }, { default: dagrePlugin }] = await Promise.all([
          import("cytoscape"),
          import("cytoscape-dagre"),
        ]);
        cytoscape.use(dagrePlugin);

        if (isCancelled || containerRef.current === null) {
          return;
        }

        const elements = [
          ...graph.nodes.map((node) => ({
            data: {
              id: node.id,
              label: node.label,
              kind: node.kind,
            },
          })),
          ...graph.edges.map((edge) => ({
            data: {
              id: `${edge.source}-${edge.relationship}-${edge.target}`,
              source: edge.source,
              target: edge.target,
              relationship: edge.relationship,
            },
          })),
        ];

        instance = cytoscape({
          container: containerRef.current,
          elements,
          minZoom: MIN_GRAPH_ZOOM,
          maxZoom: MAX_GRAPH_ZOOM,
          userZoomingEnabled: false,
          textureOnViewport: true,
          motionBlur: true,
          motionBlurOpacity: 0.14,
          pixelRatio: 1,
          autoungrabify: true,
          layout: {
            name: "dagre",
            rankDir: mode === "overview" ? "LR" : "TB",
            padding: 32,
            nodeSep: 46,
            rankSep: 64,
            edgeSep: 24,
            ranker: "tight-tree",
          },
          style: [
            {
              selector: "node",
              style: {
                label: "data(label)",
                color: "#1d2730",
                "font-size": 13,
                "font-weight": 600,
                "text-wrap": "wrap",
                "text-max-width": 136,
                "text-valign": "center",
                "text-halign": "center",
                "text-background-opacity": 0.85,
                "text-background-color": "#f7fbfa",
                "text-background-padding": 4,
                width: 112,
                height: 64,
                "background-color": "#d7e6e0",
                shape: "round-rectangle",
                "border-width": 1,
                "border-color": "#ffffff",
                "overlay-opacity": 0,
              },
            },
            ...Object.entries(kindStyles).map(([kind, style]) => ({
              selector: `node[kind = "${kind}"]`,
              style,
            })),
            {
              selector: "edge",
              style: {
                width: 2,
                "curve-style": "bezier",
                "target-arrow-shape": "triangle",
                "target-arrow-color": "#90a4ae",
                "line-color": "#90a4ae",
                label: "data(relationship)",
                "font-size": 10,
                "text-rotation": "autorotate",
                "text-background-opacity": 1,
                "text-background-color": "#f7faf8",
                "text-background-padding": 3,
                color: "#5b6771",
                "overlay-opacity": 0,
              },
            },
          ],
        });
        cyRef.current = instance;

        const syncZoomFromInstance = () => syncZoom(instance);
        instance.on("zoom", syncZoomFromInstance);
        instance.on("render", syncZoomFromInstance);

        const wheelHandler = (event: WheelEvent) => {
          if (!cyRef.current) {
            return;
          }
          event.preventDefault();
          const nextZoom = computeNextZoomLevel(cyRef.current.zoom(), event.deltaY, event.deltaMode);
          cyRef.current.zoom({
            level: nextZoom,
            renderedPosition: {
              x: event.offsetX,
              y: event.offsetY,
            },
          });
          syncZoom(cyRef.current);
        };
        containerRef.current.addEventListener("wheel", wheelHandler, { passive: false });
        removeWheelListener = () => containerRef.current?.removeEventListener("wheel", wheelHandler);

        if (typeof ResizeObserver !== "undefined") {
          resizeObserver = new ResizeObserver(() => {
            cyRef.current?.resize();
          });
          resizeObserver.observe(containerRef.current);
        }

        instance.ready(() => {
          instance?.fit(instance.elements(), 36);
          syncZoom(instance);
        });

        setStatus("ready");
      } catch {
        if (!isCancelled) {
          setStatus("error");
        }
      }
    }

    void mountGraph();

    return () => {
      isCancelled = true;
      cyRef.current = null;
      removeWheelListener?.();
      resizeObserver?.disconnect();
      instance?.destroy();
    };
  }, [graph.edges, graph.nodes, mode]);

  return (
    <div className="graph-surface">
      <div className="graph-toolbar">
        <div className="graph-toolbar__actions">
          <button className="graph-toolbar__button" type="button" onClick={() => nudgeZoom("out")}>
            {copy.kgPage.view.zoomOut}
          </button>
          <button className="graph-toolbar__button graph-toolbar__button--primary" type="button" onClick={fitView}>
            {copy.kgPage.view.fitView}
          </button>
          <button className="graph-toolbar__button" type="button" onClick={() => nudgeZoom("in")}>
            {copy.kgPage.view.zoomIn}
          </button>
        </div>
        <span className="graph-toolbar__status">{copy.kgPage.view.zoomLevel(zoomLevel)}</span>
      </div>

      <div className="graph-legend">
        {legendKinds.map((kind) => (
          <div className="legend-item" key={kind}>
            <span className={`legend-swatch legend-swatch--${kind.replace(/_/g, "-")}`} />
            <span>{legendLabelFor(kind, copy.kgPage.legend)}</span>
          </div>
        ))}
      </div>

      <p className="graph-hint">{copy.kgPage.view.interactionHint}</p>

      <div className="graph-canvas" aria-label={copy.kgPage.view.canvasLabel} ref={containerRef}>
        {status === "loading" ? <p className="muted-text">{copy.kgPage.view.loading}</p> : null}
        {status === "error" ? <p className="status-error">{copy.kgPage.view.error}</p> : null}
        {status === "idle" ? <p className="muted-text">{copy.kgPage.view.empty}</p> : null}
      </div>
    </div>
  );
}
