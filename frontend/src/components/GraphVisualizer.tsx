import React, { useState } from "react";
import { 
  Users, 
  ShoppingBag, 
  Package, 
  Award, 
  Store, 
  Sparkles, 
  ChevronRight,
  HelpCircle,
  Network,
  BookOpen,
  Activity,
  Target,
  CreditCard,
  DollarSign,
  Globe,
  Database,
  Car,
  Wrench,
  FileText
} from "lucide-react";

interface Node {
  id: string;
  label: string;
  icon: string;
  type: string;
  description: string;
  x: number;
  y: number;
}

interface Edge {
  source: string;
  target: string;
  label: string;
}

interface GraphVisualizerProps {
  graphData: {
    nodes: Omit<Node, "x" | "y">[];
    edges: Edge[];
    nodeSuggestions: Record<string, string[]>;
  };
  onSelectSuggestion: (question: string) => void;
  brandPrimaryColor?: string;
}

// Wider preset coordinates to spread nodes further towards the boundaries, reclaiming canvas space
const PRESET_COORDINATES: Record<string, { x: number; y: number }> = {
  users: { x: 75, y: 70 },
  orders: { x: 75, y: 330 },
  products: { x: 300, y: 200 },
  brands: { x: 525, y: 70 },
  stores: { x: 525, y: 330 }
};

// Vibrant color presets for flagship nodes
const PRESET_COLORS: Record<string, string> = {
  users: "#a78bfa",      // Bright Violet/Purple
  orders: "#38bdf8",     // Bright Cyan/Blue
  products: "#34d399",    // Bright Emerald Green
  brands: "#fbbf24",     // Bright Amber Gold
  stores: "#f472b6"      // Bright Pink/Rose
};

// Curated 8-color cyclic palette for custom/unknown graph schemas
const DYNAMIC_PALETTE = [
  "#a78bfa", // Purple/Violet
  "#38bdf8", // Cyan/Blue
  "#34d399", // Emerald Green
  "#fbbf24", // Amber Gold
  "#f472b6", // Rose/Pink
  "#fb7185", // Coral/Salmon
  "#2dd4bf", // Teal
  "#f43f5e"  // Red/Pink
];

export const GraphVisualizer: React.FC<GraphVisualizerProps> = ({
  graphData,
  onSelectSuggestion,
  brandPrimaryColor = "#3b82f6"
}) => {
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  // Check if we should use the preset showcase layout
  const usePresetLayout = graphData.nodes.every(n => PRESET_COORDINATES[n.id]);

  // Dynamic Layout Engine: maps coordinates on the fly
  const nodes: Node[] = graphData.nodes.map((n, idx) => {
    if (usePresetLayout && PRESET_COORDINATES[n.id]) {
      return {
        ...n,
        x: PRESET_COORDINATES[n.id].x,
        y: PRESET_COORDINATES[n.id].y
      };
    }
    
    // Circular Layout distribution for custom graphs (expanded radius from 125 to 145)
    const center = { x: 300, y: 200 };
    const radius = 145;
    const angle = (2 * Math.PI * idx) / graphData.nodes.length - Math.PI / 2; // Start at top
    
    return {
      ...n,
      x: Math.round(center.x + radius * Math.cos(angle)),
      y: Math.round(center.y + radius * Math.sin(angle))
    };
  });

  const edges = graphData.edges;

  // Semantic Icon Resolver
  const renderNodeIcon = (iconName: string, size: number = 22, color: string = "#fff") => {
    const name = (iconName || "").toLowerCase();
    
    if (name.includes("vehicle") || name.includes("car") || name.includes("truck") || name.includes("auto")) {
      return <Car size={size} color={color} />;
    }
    if (name.includes("service") || name.includes("maintenance") || name.includes("repair") || name.includes("wrench")) {
      return <Wrench size={size} color={color} />;
    }
    if (name.includes("deal") || name.includes("jacket") || name.includes("contract") || name.includes("file") || name.includes("document")) {
      return <FileText size={size} color={color} />;
    }
    if (name.includes("user") || name.includes("customer") || name.includes("visitor") || name.includes("client")) {
      return <Users size={size} color={color} />;
    }
    if (name.includes("order") || name.includes("transaction") || name.includes("sale") || name.includes("purchase")) {
      return <ShoppingBag size={size} color={color} />;
    }
    if (name.includes("product") || name.includes("item") || name.includes("package") || name.includes("sku") || name.includes("part")) {
      return <Package size={size} color={color} />;
    }
    if (name.includes("brand") || name.includes("vendor") || name.includes("award") || name.includes("manufacturer")) {
      return <Award size={size} color={color} />;
    }
    if (name.includes("store") || name.includes("warehouse") || name.includes("location") || name.includes("hub") || name.includes("depot")) {
      return <Store size={size} color={color} />;
    }
    if (name.includes("page") || name.includes("view") || name.includes("url") || name.includes("screen") || name.includes("article")) {
      return <BookOpen size={size} color={color} />;
    }
    if (name.includes("session") || name.includes("visit") || name.includes("activity") || name.includes("click") || name.includes("event")) {
      return <Activity size={size} color={color} />;
    }
    if (name.includes("conversion") || name.includes("goal") || name.includes("target") || name.includes("kpi")) {
      return <Target size={size} color={color} />;
    }
    if (name.includes("card") || name.includes("credit") || name.includes("payment") || name.includes("account")) {
      return <CreditCard size={size} color={color} />;
    }
    if (name.includes("money") || name.includes("dollar") || name.includes("price") || name.includes("cost") || name.includes("revenue") || name.includes("profit")) {
      return <DollarSign size={size} color={color} />;
    }
    if (name.includes("globe") || name.includes("country") || name.includes("region") || name.includes("world") || name.includes("site")) {
      return <Globe size={size} color={color} />;
    }
    if (name.includes("db") || name.includes("database") || name.includes("table") || name.includes("schema")) {
      return <Database size={size} color={color} />;
    }
    return <Network size={size} color={color} />;
  };

  // Helper to check if an edge connects to a hovered/selected node
  const isEdgeHighlighted = (edge: Edge) => {
    const activeNode = hoveredNode || selectedNode;
    if (!activeNode) return false;
    return edge.source === activeNode || edge.target === activeNode;
  };

  // Helper to resolve node specific color dynamically
  const getNodeColor = (nodeId: string, nodeIdx: number) => {
    if (usePresetLayout && PRESET_COLORS[nodeId]) {
      return PRESET_COLORS[nodeId];
    }
    return DYNAMIC_PALETTE[nodeIdx % DYNAMIC_PALETTE.length];
  };

  // Get active suggestions to display in the floating inspector
  const activeNodeObj = nodes.find(n => n.id === selectedNode);
  const activeNodeIdx = nodes.findIndex(n => n.id === selectedNode);
  const suggestions = selectedNode ? graphData.nodeSuggestions[selectedNode] || [] : [];
  const activeNodeColor = selectedNode ? getNodeColor(selectedNode, activeNodeIdx) : brandPrimaryColor;

  return (
    <div className="w-full flex flex-col gap-6 items-center py-2 select-none max-w-4xl mx-auto animate-fadeIn">
      {/* 1. Interactive Animated SVG Graph Canvas */}
      <div className="relative w-full bg-slate-950/60 border border-white/10 rounded-3xl p-4 backdrop-blur-md shadow-2xl flex items-center justify-center overflow-hidden aspect-[3/2] md:aspect-[16/10] w-full">
        {/* Grid background */}
        <div className="absolute inset-0 bg-[radial-gradient(rgba(255,255,255,0.025)_1px,transparent_1px)] [background-size:20px_20px] pointer-events-none" />
        
        <svg 
          viewBox="0 0 600 400" 
          className="w-full h-full overflow-visible cursor-default"
          onClick={() => setSelectedNode(null)}
        >
          <defs>
            {/* Standard edge arrow markers */}
            <marker
              id="arrow-end"
              viewBox="0 0 10 10"
              refX="6"
              refY="5"
              markerWidth="5"
              markerHeight="5"
              orient="auto"
            >
              <path d="M 0 1.5 L 7 5 L 0 8.5 z" fill="rgba(255,255,255,0.25)" />
            </marker>
            <marker
              id="arrow-start"
              viewBox="0 0 10 10"
              refX="1"
              refY="5"
              markerWidth="5"
              markerHeight="5"
              orient="auto-start-reverse"
            >
              <path d="M 0 1.5 L 7 5 L 0 8.5 z" fill="rgba(255,255,255,0.25)" />
            </marker>
            
            {/* Highlighted active edge arrow markers */}
            <marker
              id="arrow-end-active"
              viewBox="0 0 10 10"
              refX="6"
              refY="5"
              markerWidth="5"
              markerHeight="5"
              orient="auto"
            >
              <path d="M 0 1.5 L 7 5 L 0 8.5 z" fill="currentColor" />
            </marker>
            <marker
              id="arrow-start-active"
              viewBox="0 0 10 10"
              refX="1"
              refY="5"
              markerWidth="5"
              markerHeight="5"
              orient="auto-start-reverse"
            >
              <path d="M 0 1.5 L 7 5 L 0 8.5 z" fill="currentColor" />
            </marker>
          </defs>

          {/* A. Relationship Tracks (Edges) */}
          <g>
            {edges.map((edge, idx) => {
              const src = nodes.find(n => n.id === edge.source);
              const tgt = nodes.find(n => n.id === edge.target);
              if (!src || !tgt) return null;

              const srcIdx = nodes.findIndex(n => n.id === edge.source);
              const edgeColor = getNodeColor(edge.source, srcIdx);

              const highlighted = isEdgeHighlighted(edge);
              const dimmed = (hoveredNode || selectedNode) && !highlighted;

              // Shorten edge lines to end exactly at the node boundary rings (34px radius)
              const dx = tgt.x - src.x;
              const dy = tgt.y - src.y;
              const dist = Math.sqrt(dx * dx + dy * dy) || 1;
              const ux = dx / dist;
              const uy = dy / dist;

              const rBoundary = 34;
              const x1 = src.x + ux * rBoundary;
              const y1 = src.y + uy * rBoundary;
              const x2 = tgt.x - ux * rBoundary;
              const y2 = tgt.y - uy * rBoundary;

              return (
                <g key={idx} className="transition-all duration-300">
                  {/* Glowing background line for highlighted connections */}
                  {highlighted && (
                    <line
                      x1={x1}
                      y1={y1}
                      x2={x2}
                      y2={y2}
                      stroke={edgeColor}
                      strokeWidth="5"
                      strokeLinecap="round"
                      className="opacity-30 blur-sm"
                    />
                  )}
                  {/* Core relationship line */}
                  <line
                    x1={x1}
                    y1={y1}
                    x2={x2}
                    y2={y2}
                    stroke={highlighted ? edgeColor : "rgba(255,255,255,0.15)"}
                    strokeWidth={highlighted ? "3" : "1.5"}
                    strokeDasharray={highlighted ? "none" : "6, 6"}
                    markerEnd={highlighted ? "url(#arrow-end-active)" : "url(#arrow-end)"}
                    className={`transition-all duration-300 ${dimmed ? "opacity-20" : "opacity-100"}`}
                    style={{ color: edgeColor }}
                  />
                  
                  {/* Native SVG flowing particle animations */}
                  {highlighted && (
                    <circle r="4.5" fill={edgeColor} className="filter drop-shadow-[0_0_8px_var(--tw-shadow-color)]" style={{ shadowColor: edgeColor } as any}>
                      <animateMotion
                        dur="2s"
                        repeatCount="indefinite"
                        path={`M ${x1} ${y1} L ${x2} ${y2}`}
                      />
                    </circle>
                  )}
                </g>
              );
            })}
          </g>

          {/* B. Relationship Labels (Edges text) */}
          <g>
            {edges.map((edge, idx) => {
              const src = nodes.find(n => n.id === edge.source);
              const tgt = nodes.find(n => n.id === edge.target);
              if (!src || !tgt) return null;

              const srcIdx = nodes.findIndex(n => n.id === edge.source);
              const edgeColor = getNodeColor(edge.source, srcIdx);

              const highlighted = isEdgeHighlighted(edge);
              const dimmed = (hoveredNode || selectedNode) && !highlighted;

              const xMid = (src.x + tgt.x) / 2;
              const yMid = (src.y + tgt.y) / 2;

              return (
                <g 
                  key={`label-${idx}`} 
                  className={`transition-all duration-300 ${dimmed ? "opacity-15" : "opacity-100"}`}
                >
                  {/* Micro-glassmorphic background pill - dynamically sized based on character length */}
                  {(() => {
                    const labelLength = edge.label.length;
                    const approxCharWidth = 7.5; // Increased from 5.6 to handle bold wide tracking
                    const padding = 24; // Increased from 16 for elegant horizontal margins
                    const rectWidth = Math.max(56, labelLength * approxCharWidth + padding);
                    const rectHeight = 18;
                    const rx = rectHeight / 2;
                    return (
                      <rect
                        x={xMid - rectWidth / 2}
                        y={yMid - rectHeight / 2}
                        width={rectWidth}
                        height={rectHeight}
                        rx={rx}
                        fill="rgba(15, 23, 42, 0.9)"
                        stroke={highlighted ? edgeColor : "rgba(255,255,255,0.12)"}
                        strokeWidth={highlighted ? "1.5" : "1"}
                        className="transition-all duration-300"
                      />
                    );
                  })()}
                  {/* Edge Label text */}
                  <text
                    x={xMid}
                    y={yMid + 3}
                    textAnchor="middle"
                    className={`text-[8.5px] font-bold tracking-widest uppercase transition-all duration-300 select-none ${highlighted ? "fill-white font-extrabold" : "fill-slate-400"}`}
                  >
                    {edge.label}
                  </text>
                </g>
              );
            })}
          </g>

          {/* C. Symmetrical Glowing Multi-Color Nodes (SCALED UP FOR VISIBILITY) */}
          <g>
            {nodes.map((node, idx) => {
              const isSelected = selectedNode === node.id;
              const isHovered = hoveredNode === node.id;
              const isDimmed = (hoveredNode || selectedNode) && !isSelected && !isHovered;
              
              const nodeColor = getNodeColor(node.id, idx);

              return (
                <g
                  key={node.id}
                  transform={`translate(${node.x}, ${node.y})`}
                  className="cursor-pointer group"
                  onMouseEnter={() => setHoveredNode(node.id)}
                  onMouseLeave={() => setHoveredNode(null)}
                  onClick={(e) => {
                    e.stopPropagation(); // Prevent deselecting when clicking the node itself
                    setSelectedNode(isSelected ? null : node.id);
                  }}
                >
                  {/* Larger glowing aura behind active node */}
                  {(isSelected || isHovered) && (
                    <circle
                      r="38"
                      fill={nodeColor}
                      className="opacity-25 blur-md transition-all duration-300 scale-110"
                    />
                  )}
                  
                  {/* Outer pulsing ring - scaled up from 28 to 32 */}
                  <circle
                    r="32"
                    fill="none"
                    stroke={isSelected ? nodeColor : isHovered ? "rgba(255,255,255,0.4)" : "rgba(255,255,255,0.12)"}
                    strokeWidth={isSelected ? "3" : "1.5"}
                    className={`transition-all duration-300 ${isSelected ? "animate-ping opacity-20" : ""}`}
                  />
                  
                  {/* Core Node Circle - scaled up from 24 to 28 */}
                  <circle
                    r="28"
                    fill={isSelected ? "rgba(15, 23, 42, 0.95)" : "rgba(17, 24, 39, 0.85)"}
                    stroke={isSelected || isHovered ? nodeColor : "rgba(255,255,255,0.2)"}
                    strokeWidth={isSelected || isHovered ? "2.5" : "1.5"}
                    className={`transition-all duration-300 ${isDimmed ? "opacity-30" : "opacity-100"}`}
                  />

                  {/* Semantic Icon - scaled up from 20 to 22, aligned using translate(-11, -11) */}
                  <g 
                    className={`transition-all duration-300 ${isDimmed ? "opacity-30" : "opacity-100"}`}
                    transform="translate(-11, -11)"
                  >
                    {renderNodeIcon(
                      node.icon, 
                      22, 
                      isSelected || isHovered ? "#ffffff" : nodeColor
                    )}
                  </g>

                  {/* Node Label - offset adjusted to 45 for larger circle */}
                  <text
                    y="45"
                    textAnchor="middle"
                    className={`text-[10.5px] font-bold tracking-widest uppercase transition-all duration-300 select-none ${isSelected ? "fill-white font-extrabold" : isHovered ? "fill-white" : "fill-slate-200"} ${isDimmed ? "opacity-20" : "opacity-100"}`}
                    style={{ textShadow: !isDimmed ? "0 2px 4px rgba(0,0,0,0.85)" : "none" }}
                  >
                    {node.label}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
        
        {/* Hover Tooltip */}
        {hoveredNode && !selectedNode && (
          <div 
            className="absolute bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 bg-slate-950/90 border border-white/10 rounded-xl text-[11px] text-slate-200 backdrop-blur-md flex items-center gap-1.5 shadow-xl pointer-events-none animate-fadeIn"
          >
            <span 
              className="font-bold uppercase"
              style={{ color: getNodeColor(hoveredNode, nodes.findIndex(n => n.id === hoveredNode)) }}
            >
              {nodes.find(n => n.id === hoveredNode)?.label}
            </span>
            <span className="text-slate-600">|</span>
            <span className="font-medium">Click node to explore queries</span>
          </div>
        )}
      </div>

      {/* 2. Dynamic Glassmorphic Entity Inspector Card */}
      <div className="w-full flex flex-col min-h-[160px] justify-center w-full">
        {selectedNode && activeNodeObj ? (
          <div 
            className="p-5 bg-slate-950/50 border rounded-3xl backdrop-blur-md shadow-2xl grid grid-cols-1 md:grid-cols-2 gap-6 animate-slideIn w-full transition-all duration-300"
            style={{ borderColor: `${activeNodeColor}30` }}
          >
            {/* COLUMN 1: Entity Info */}
            <div className="flex flex-col gap-3.5">
              <div className="flex items-center gap-3">
                <div 
                  className="w-10 h-10 rounded-xl flex items-center justify-center border transition-all duration-300"
                  style={{ 
                    backgroundColor: `${activeNodeColor}15`,
                    borderColor: `${activeNodeColor}40`
                  }}
                >
                  {renderNodeIcon(activeNodeObj.icon, 18, activeNodeColor)}
                </div>
                <div className="flex flex-col">
                  <h3 className="text-sm font-bold text-white tracking-tight uppercase">{activeNodeObj.label}</h3>
                  <span 
                    className="text-[9px] font-bold uppercase tracking-widest transition-all duration-300"
                    style={{ color: activeNodeColor }}
                  >
                    {activeNodeObj.type}
                  </span>
                </div>
              </div>

              {/* Entity Description */}
              <p className="text-xs text-slate-300 leading-relaxed font-medium">
                {activeNodeObj.description}
              </p>
            </div>

            {/* COLUMN 2: Curated Suggested Queries */}
            <div className="flex flex-col gap-2">
              <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1.5">
                <Sparkles size={11} className="animate-pulse" style={{ color: activeNodeColor }} />
                Suggested Graph Insights:
              </h4>
              <div className="flex flex-col gap-2 max-h-[150px] overflow-y-auto pr-1">
                {suggestions.map((suggestion, idx) => (
                  <button
                    key={idx}
                    onClick={() => onSelectSuggestion(suggestion)}
                    className="p-3 bg-white/4 border border-white/6 hover:bg-white/8 rounded-xl text-left text-[11px] text-slate-200 font-semibold transition cursor-pointer flex items-center justify-between group"
                  >
                    <span className="group-hover:text-white transition duration-150 leading-relaxed pr-2">{suggestion}</span>
                    <ChevronRight 
                      size={12} 
                      className="shrink-0 opacity-0 group-hover:opacity-100 transition-all duration-200 group-hover:translate-x-0.5"
                      style={{ color: activeNodeColor }}
                    />
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="p-6 bg-white/3 border border-white/6 rounded-3xl backdrop-blur-sm text-center flex flex-col gap-4 w-full max-w-xl mx-auto">
            <div className="w-12 h-12 rounded-2xl bg-brand-primary/10 border border-brand-primary/15 text-brand-primary flex items-center justify-center mx-auto shadow-sm">
              <Network size={22} className="animate-pulse text-brand-primary" />
            </div>
            <div className="flex flex-col gap-1">
              <h3 className="text-xs font-bold text-white">Explore the Database Graph</h3>
              <p className="text-[10px] text-slate-400 leading-relaxed px-2 font-medium">
                This agent is powered by a connected **BigQuery Graph Schema** representing key entity nodes and their relationships.
              </p>
            </div>
            <div className="p-3.5 bg-slate-950/50 border border-white/6 rounded-xl text-[10px] text-slate-300 leading-relaxed flex items-center justify-center gap-1.5 font-semibold">
              <HelpCircle size={12} className="text-brand-primary shrink-0" />
              Click any node circle to reveal insights and ask questions!
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
