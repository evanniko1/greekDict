import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import cytoscape from "cytoscape";
import type { Core, ElementDefinition } from "cytoscape";
import { getGraph } from "../api/client";
import type { GraphResponse } from "../api/types";
import { relEl } from "../api/labels";
import { useIsDark } from "../hooks/useTheme";

// Typed + sourced edges only — colour encodes relation_type (product feature #2).
// Palette: harmonised 600-weight tones for a calm, modern look.
const REL_COLORS: Record<string, string> = {
  current: "#1e293b",
  synonym: "#059669",
  antonym: "#e11d48",
  related: "#4f46e5",
  derived: "#7c3aed",
  hypernym: "#d97706",
  hyponym: "#0891b2",
  // etymological origin edges — warmer, earthy tones to read as "history"
  inherited: "#b45309",
  borrowed: "#0d9488",
  calque: "#65a30d",
  cognate: "#9333ea",
};
const REL_ORDER = ["synonym", "antonym", "related", "derived", "hypernym", "hyponym"];
const ETY_ORDER = ["inherited", "borrowed", "derived", "calque", "cognate"];

function colorFor(type: string): string {
  return REL_COLORS[type] ?? "#94a3b8";
}

export default function RelationGraph({ lemma }: { lemma: string }) {
  const navigate = useNavigate();
  const isDark = useIsDark();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const [data, setData] = useState<GraphResponse | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    getGraph(lemma)
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setStatus("ok");
      })
      .catch(() => {
        if (cancelled) return;
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [lemma]);

  useEffect(() => {
    if (!data || !containerRef.current) return;

    // Theme-dependent label colours: cytoscape can't use Tailwind classes, so we
    // recompute on theme change (isDark is in this effect's deps). The halo is the
    // page background colour so labels stay legible over edges/nodes either way.
    const labelColor = isDark ? "#e2e8f0" : "#0f172a";
    const haloColor = isDark ? "#0f172a" : "#ffffff";
    const mutedColor = isDark ? "#94a3b8" : "#64748b";

    const elements: ElementDefinition[] = [
      ...data.nodes.map((n) => ({
        data: { id: n.id, label: n.label, ntype: n.type, resolved: n.resolved, etymon: !!n.etymon },
      })),
      ...data.edges.map((e) => ({
        data: {
          id: `${e.source}->${e.target}-${e.type}`,
          source: e.source,
          target: e.target,
          reltype: e.type,
          title: `${relEl(e.type)} · ${e.source_name}`,
        },
      })),
    ];

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": (ele: cytoscape.NodeSingular) => colorFor(ele.data("ntype")),
            "background-opacity": 0.92,
            label: "data(label)",
            color: labelColor,
            "font-size": 11,
            "font-family": "system-ui, sans-serif",
            "text-valign": "bottom",
            "text-halign": "center",
            "text-margin-y": 4,
            // Halo (page-bg colour) keeps labels legible where they overlap edges/nodes.
            "text-outline-color": haloColor,
            "text-outline-width": 2.5,
            "text-outline-opacity": 0.9,
            width: 12,
            height: 12,
          },
        },
        {
          selector: 'node[ntype = "current"]',
          style: {
            width: 26,
            height: 26,
            "font-size": 15,
            "font-weight": "bold",
            "text-margin-y": 6,
          },
        },
        {
          // Resolved (clickable) targets get a subtle ring + pointer affordance.
          selector: "node[?resolved][ntype != 'current']",
          style: { "border-width": 3, "border-color": haloColor, width: 15, height: 15 },
        },
        {
          // Unresolved targets read as muted/secondary.
          selector: "node[!resolved]",
          style: { "background-opacity": 0.45, color: mutedColor },
        },
        {
          // Etymological ancestors: square shape distinguishes "origin" (a
          // cross-language source word) from lexical neighbours (circles).
          selector: "node[?etymon]",
          style: {
            shape: "round-rectangle",
            "background-opacity": 0.85,
            color: mutedColor,
            width: 14,
            height: 14,
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.25,
            "line-color": (ele: cytoscape.EdgeSingular) => colorFor(ele.data("reltype")),
            "line-opacity": 0.5,
            "target-arrow-color": (ele: cytoscape.EdgeSingular) => colorFor(ele.data("reltype")),
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.7,
            "curve-style": "bezier",
          },
        },
      ],
      layout: {
        name: "cose",
        animate: false,
        padding: 36,
        // Account for label boxes so words don't pile on top of each other.
        nodeDimensionsIncludeLabels: true,
        idealEdgeLength: 120,
        nodeRepulsion: 14000,
        componentSpacing: 120,
        gravity: 0.2,
        numIter: 1500,
        fit: true,
      } as cytoscape.LayoutOptions,
      minZoom: 0.2,
      maxZoom: 2.5,
    });

    cy.on("tap", "node", (evt) => {
      const node = evt.target;
      if (node.data("resolved") && node.data("ntype") !== "current") {
        navigate(`/word/${encodeURIComponent(node.data("label"))}`);
      }
    });

    // Pointer cursor only on clickable (resolved) targets.
    cy.on("mouseover", "node[?resolved][ntype != 'current']", () => {
      if (containerRef.current) containerRef.current.style.cursor = "pointer";
    });
    cy.on("mouseout", "node", () => {
      if (containerRef.current) containerRef.current.style.cursor = "default";
    });

    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [data, navigate, isDark]);

  if (status === "error") {
    return <p className="text-sm text-slate-400 dark:text-slate-500">Το γράφημα δεν είναι διαθέσιμο.</p>;
  }
  if (status === "ok" && data && data.edges.length === 0) {
    return (
      <p className="text-sm text-slate-400 dark:text-slate-500">
        Δεν έχουν καταγραφεί ακόμη τυποποιημένες σχέσεις για αυτή τη λέξη.
      </p>
    );
  }

  // Only show etymology legend entries actually present in this word's graph.
  const etyTypes = data
    ? ETY_ORDER.filter((t) => data.edges.some((e) => e.type === t))
    : [];

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-slate-500 dark:text-slate-400">
        {REL_ORDER.map((t) => (
          <span key={t} className="flex items-center gap-1">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: colorFor(t) }}
            />
            {relEl(t)}
          </span>
        ))}
        <span className="text-slate-400 dark:text-slate-500">· πάτησε έναν κόμβο με περίγραμμα για να ανοίξει</span>
      </div>
      {etyTypes.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-slate-500 dark:text-slate-400">
          <span className="text-slate-400 dark:text-slate-500">Ετυμολογία:</span>
          {etyTypes.map((t) => (
            <span key={t} className="flex items-center gap-1">
              <span
                className="inline-block h-2.5 w-2.5 rounded-sm"
                style={{ backgroundColor: colorFor(t) }}
              />
              {relEl(t)}
            </span>
          ))}
        </div>
      )}
      <div
        ref={containerRef}
        className="h-[480px] w-full rounded-lg border border-slate-200 bg-slate-50/40 dark:border-slate-800 dark:bg-slate-900/40"
      />
    </div>
  );
}
