"use client";

import React, { useEffect, useRef, useState } from "react";
import { ReactFlow, Background, Controls, MiniMap, Connection, MarkerType, addEdge, NodeTypes, EdgeTypes, Viewport, EdgeProps, applyNodeChanges, applyEdgeChanges } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { GraphOut, GraphNode, GraphEdge } from "@/lib/types";
import StatusBadge from "@/components/StatusBadge";

function safeGet<T>(obj: Record<string, unknown> | undefined, key: string, fallback: T): T {
  if (!obj || typeof obj !== "object") return fallback;
  const val = obj[key];
  return (val as T) ?? fallback;
}

const nodeTypes: NodeTypes = {
  repository: ({ data }) => (
    <div className="px-3 py-2 rounded-md bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 text-xs font-mono whitespace-nowrap">
      Repo: {data.label}
    </div>
  ),
  file: ({ data }) => {
    const changeType = safeGet(data, "change_type", "unknown");
    return (
      <div className="px-3 py-2 rounded-md bg-sky-500/20 border border-sky-500/40 text-sky-400 text-xs font-mono whitespace-nowrap max-w-[200px] truncate">
        {data.label}
        <StatusBadge value={changeType} className="ml-2" />
      </div>
    );
  },
  scope: ({ data }) => {
    const coverageStatus = safeGet(data, "coverage_status", "COVERAGE_UNAVAILABLE");
    return (
      <div className="px-3 py-2 rounded-md bg-violet-500/20 border border-violet-500/40 text-violet-400 text-xs font-mono whitespace-nowrap max-w-[250px] truncate">
        {data.label}
        <StatusBadge value={coverageStatus} className="ml-2" />
      </div>
    );
  },
  line: ({ data }) => (
    <div className="px-2 py-1 rounded bg-rose-500/20 border border-rose-500/40 text-rose-400 text-[10px] font-mono whitespace-nowrap">
      {data.label}
    </div>
  ),
  test: ({ data }) => {
    const category = safeGet(data, "category", "UNKNOWN");
    return (
      <div className="px-3 py-2 rounded-md bg-amber-500/20 border border-amber-500/40 text-amber-400 text-xs font-mono whitespace-nowrap max-w-[200px] truncate">
        {data.label}
        <StatusBadge value={category} className="ml-2" />
      </div>
    );
  },
  verification: ({ data }) => {
    const classification = safeGet(data, "classification", "UNKNOWN");
    return (
      <div className="px-3 py-2 rounded-md bg-fuchsia-500/20 border border-fuchsia-500/40 text-fuchsia-400 text-xs font-mono whitespace-nowrap max-w-[200px] truncate">
        {data.label}
        <StatusBadge value={classification} className="ml-2" />
      </div>
    );
  },
  failure: ({ data }) => (
    <div className="px-3 py-2 rounded-md bg-rose-500/20 border-2 border-rose-500 text-rose-300 text-xs font-mono whitespace-nowrap max-w-[200px] truncate">
      🔴 {data.label}
    </div>
  ),
};

function CustomEdge({ data, ...rest }: EdgeProps) {
  const stroke = data?.type === "REGRESSED_AGAINST" ? "#f87171" : data?.type === "PROVES_FAILURE" ? "#f87171" : "#3b82f6";
  const strokeDasharray = data?.type === "CONTAINS" || data?.type === "HAS_SCOPE" ? "4 4" : undefined;
  return (
    <>
      <path
        {...rest}
        strokeWidth={1.5}
        stroke={stroke}
        strokeDasharray={strokeDasharray}
        fill="none"
        markerEnd={`url(#arrow-${stroke.replace("#", "")})`}
      />
      <defs>
        <marker
          id={`arrow-${stroke.replace("#", "")}`}
          markerWidth={10}
          markerHeight={10}
          refX={8}
          refY={3}
          orient="auto"
          markerUnits="strokeWidth"
        >
          <path d="M0,0 L0,6 L9,3 z" fill={stroke} />
        </marker>
      </defs>
    </>
  );
}

const edgeTypes: EdgeTypes = {
  default: CustomEdge,
};

interface EvidenceGraphProps {
  graph: {
    nodes: Array<{ id: string; type: string; label: string; data: Record<string, unknown> }>;
    edges: Array<{ id: string; source: string; target: string; type: string; data: Record<string, unknown> }>;
  };
  onNodeClick?: (nodeId: string) => void;
}

export default function EvidenceGraph({ graph, onNodeClick }: EvidenceGraphProps) {
  const [nodes, setNodes] = useState<Array<{ id: string; type: string; position: { x: number; y: number }; data: Record<string, unknown> }>>([]);
  const [edges, setEdges] = useState<Array<{ id: string; source: string; target: string; type: string; data: Record<string, unknown> }>>([]);
  const [viewport, setViewport] = useState<Viewport>({ x: 0, y: 0, zoom: 1 });

  useEffect(() => {
    const nodeCount = graph.nodes.length;
    const newNodes = graph.nodes.map((n, i) => {
      const angle = (i / Math.max(1, nodeCount - 1)) * 2 * Math.PI;
      const radius = Math.max(300, nodeCount * 20);
      return {
        id: n.id,
        type: n.type,
        position: {
          x: Math.cos(angle) * radius + 400,
          y: Math.sin(angle) * radius + 300,
        },
        data: n.data,
      };
    });
    const newEdges = graph.edges.map(e => ({
      id: e.id,
      source: e.source,
      target: e.target,
      type: e.type,
      data: e.data,
    }));
    setNodes(newNodes);
    setEdges(newEdges);
  }, [graph]);

  const onConnect = (connection: Connection) => {
    setEdges(eds => addEdge({ ...connection, type: "default" }, eds));
  };

  const handleNodeClick = (_event: React.MouseEvent, node: { id: string }) => {
    if (onNodeClick) {
      onNodeClick(node.id);
    }
  };

  return (
    <div className="w-full h-full rounded-md border border-[#1e2633] bg-[#0b0e14]">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={changes => setNodes(ns => applyNodeChanges(changes, ns))}
        onEdgesChange={changes => setEdges(es => applyEdgeChanges(changes, es))}
        onConnect={onConnect}
        onViewportChange={setViewport}
        viewport={viewport}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView={true}
        onNodeClick={handleNodeClick}
      >
        <Background color="#1e2633" gap={16} />
        <Controls />
        <MiniMap />
      </ReactFlow>
    </div>
  );
}