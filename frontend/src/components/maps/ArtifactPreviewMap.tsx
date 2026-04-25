import { useEffect, useRef, useState } from "react";

import { useI18n } from "../../app/i18n";

type ArtifactPreviewMapProps = {
  geojsonUrl?: string;
  bbox?: [number, number, number, number] | null;
  featureCount?: number;
  crs?: string | null;
};

const blankStyle = {
  version: 8,
  sources: {},
  layers: [
    {
      id: "background",
      type: "background",
      paint: {
        "background-color": "#edf2f0",
      },
    },
  ],
} as const;

export function ArtifactPreviewMap({
  geojsonUrl,
  bbox,
  featureCount = 0,
  crs,
}: ArtifactPreviewMapProps) {
  const { copy } = useI18n();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">(
    geojsonUrl ? "loading" : "idle",
  );

  useEffect(() => {
    if (!geojsonUrl || containerRef.current === null) {
      setStatus("idle");
      return;
    }
    if (typeof window === "undefined" || /jsdom/i.test(window.navigator.userAgent)) {
      setStatus("ready");
      return;
    }

    let isCancelled = false;
    let map: { remove: () => void } | null = null;

    async function mountMap() {
      setStatus("loading");
      try {
        const [{ default: maplibregl }, response] = await Promise.all([
          import("maplibre-gl"),
          fetch(geojsonUrl),
        ]);
        const data = await response.json();

        if (isCancelled || containerRef.current === null) {
          return;
        }

        map = new maplibregl.Map({
          container: containerRef.current,
          style: blankStyle,
          center: [0, 0],
          zoom: 1.5,
          attributionControl: false,
        });

        map.on("load", () => {
          if (isCancelled || map === null) {
            return;
          }

          map.addSource("artifact-preview", {
            type: "geojson",
            data,
          });

          map.addLayer({
            id: "artifact-fill",
            type: "fill",
            source: "artifact-preview",
            filter: ["any", ["==", ["geometry-type"], "Polygon"], ["==", ["geometry-type"], "MultiPolygon"]],
            paint: {
              "fill-color": "#1e7b80",
              "fill-opacity": 0.25,
            },
          });
          map.addLayer({
            id: "artifact-line",
            type: "line",
            source: "artifact-preview",
            filter: ["any", ["==", ["geometry-type"], "LineString"], ["==", ["geometry-type"], "MultiLineString"], ["==", ["geometry-type"], "Polygon"], ["==", ["geometry-type"], "MultiPolygon"]],
            paint: {
              "line-color": "#0f6166",
              "line-width": 2,
            },
          });
          map.addLayer({
            id: "artifact-point",
            type: "circle",
            source: "artifact-preview",
            filter: ["any", ["==", ["geometry-type"], "Point"], ["==", ["geometry-type"], "MultiPoint"]],
            paint: {
              "circle-radius": 5,
              "circle-color": "#d97924",
              "circle-stroke-width": 1,
              "circle-stroke-color": "#ffffff",
            },
          });

          if (bbox) {
            map.fitBounds(
              [
                [bbox[0], bbox[1]],
                [bbox[2], bbox[3]],
              ],
              { padding: 32, duration: 0 },
            );
          }
          setStatus("ready");
        });
      } catch {
        if (!isCancelled) {
          setStatus("error");
        }
      }
    }

    void mountMap();

    return () => {
      isCancelled = true;
      map?.remove();
    };
  }, [bbox, geojsonUrl]);

  return (
    <section className="map-panel">
      <div className="map-panel__meta">
        <span>{copy.map.stats.features(featureCount)}</span>
        <span>{copy.map.stats.crs(crs)}</span>
      </div>
      <div className="map-canvas" ref={containerRef}>
        {status === "loading" ? <p className="muted-text">{copy.map.loading}</p> : null}
        {status === "error" ? <p className="status-error">{copy.map.error}</p> : null}
        {status === "idle" ? <p className="muted-text">{copy.map.empty}</p> : null}
      </div>
    </section>
  );
}
