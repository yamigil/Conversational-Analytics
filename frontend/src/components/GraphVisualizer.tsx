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
  Network
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

// Fixed symmetrical coordinates for a perfectly balanced, responsive layout
const NODE_COORDINATES: Record<string, { x: number; y: number }> = {
  users: { x: 110, y: 100 },
  orders: { x: 110, y: 300 },
  products: { x: 300, y: 200 },
  brands: { x: 490, y: 100 },
  stores: { x: 490, y: 300 }
};

// Vibrant, distinct colors for each entity node type to make them pop!
const NODE_COLORS: Record<string, string> = {
  users: "#a78bfa",      // Bright Violet/Purple
  orders: "#38bdf8",     // Bright Cyan/Blue
  products: "#34d399",    // Bright Emerald Green
  brands: "#fbbf24",     // Bright Amber Gold
  stores: "#f472b6"      // Bright Pink/Rose
};

export const GraphVisualizer: React.FC<GraphVisualizerProps> = ({
  graphData,
  onSelectSuggestion,
  brandPrimaryColor = "#3b82f6"
}) => {
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  // Map coordinates onto backend node descriptions
  const nodes: Node[] = graphData.nodes.map(n => ({
    ...n,
    x: NODE_COORDINATES[n.id]?.x || 300,
    y: NODE_COORDINATES[n.id]?.y || 200
  }));

  const edges = graphData.edges;

  // Helper to render entity-specific Lucide icons
  const renderNodeIcon = (iconName: string, size: number = 20, color: string = "#fff") => {
    switch (iconName) {
      case "users": return <Users size={size} color={color} />;
      case "shopping-bag": return <ShoppingBag size={size} color={color} />;
      case "package": return <Package size={size} color={color} />;
      case "award": return <Award size={size} color={color} />;
      case "store": return <Store size={size} color={color} />;
      default: return <Network size={size} color={color} />;
    }
  };

  // Helper to check if an edge connects to a hovered/selected node
  const isEdgeHighlighted = (edge: Edge) => {
    const activeNode = hoveredNode || selectedNode;
    if (!activeNode) return false;
    return edge.source === activeNode || edge.target === activeNode;
  };

  // Get active suggestions to display in the floating inspector
  const activeNodeObj = nodes.find(n => n.id === selectedNode);
  const suggestions = selectedNode ? graphData.nodeSuggestions[selectedNode] || [] : [];
  const activeNodeColor = selectedNode ? NODE_COLORS[selectedNode] || brandPrimaryColor : brandPrimaryColor;

  return (
    <div className="w-full flex flex-col lg:flex-row gap-6 items-center justify-center py-4 select-none max-w-4xl mx-auto animate-fadeIn">
      {/* 1. Interactive Animated SVG Graph Canvas */}
      <div className="relative w-full lg:w-3/5 bg-slate-950/60 border border-white/10 rounded-3xl p-4 backdrop-blur-md shadow-2xl flex items-center justify-center overflow-hidden aspect-[3/2] max-w-lg lg:max-w-none">
        {/* Grid background with slightly higher visibility */}
        <div className="absolute inset-0 bg-[radial-gradient(rgba(255,255,255,0.025)_1px,transparent_1px)] [background-size:20px_20px] pointer-events-none" />
        
        <svg 
          viewBox="0 0 600 400" 
          className="w-full h-full overflow-visible"
        >
          {/* A. Relationship Tracks (Edges) */}
          <g>
            {edges.map((edge, idx) => {
              const src = nodes.find(n => n.id === edge.source);
              const tgt = nodes.find(n => n.id === edge.target);
              if (!src || !tgt) return null;

              const highlighted = isEdgeHighlighted(edge);
              const dimmed = (hoveredNode || selectedNode) && !highlighted;
              
              // Color relationships based on the source node's identity
              const edgeColor = NODE_COLORS[edge.source] || brandPrimaryColor;

              return (
                <g key={idx} className="transition-all duration-300">
                  {/* Glowing background line for highlighted connections */}
                  {highlighted && (
                    <line
                      x1={src.x}
                      y1={src.y}
                      x2={tgt.x}
                      y2={tgt.y}
                      stroke={edgeColor}
                      strokeWidth="6"
                      strokeLinecap="round"
                      className="opacity-30 blur-sm"
                    />
                  )}
                  {/* Core relationship line - increased opacity and thickness for visibility */}
                  <line
                    x1={src.x}
                    y1={src.y}
                    x2={tgt.x}
                    y2={tgt.y}
                    stroke={highlighted ? edgeColor : "rgba(255,255,255,0.15)"}
                    strokeWidth={highlighted ? "3" : "1.5"}
                    strokeDasharray={highlighted ? "none" : "6, 6"}
                    className={`transition-all duration-300 ${dimmed ? "opacity-20" : "opacity-100"}`}
                  />
                  
                  {/* Native SVG flowing particle animations */}
                  {highlighted && (
                    <circle r="4.5" fill={edgeColor} className="filter drop-shadow-[0_0_8px_var(--tw-shadow-color)]" style={{ shadowColor: edgeColor } as any}>
                      <animateMotion
                        dur="2s"
                        repeatCount="indefinite"
                        path={`M ${src.x} ${src.y} L ${tgt.x} ${tgt.y}`}
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

              const highlighted = isEdgeHighlighted(edge);
              const dimmed = (hoveredNode || selectedNode) && !highlighted;
              const edgeColor = NODE_COLORS[edge.source] || brandPrimaryColor;

              // Compute midpoint
              const xMid = (src.x + tgt.x) / 2;
              const yMid = (src.y + tgt.y) / 2;

              return (
                <g 
                  key={`label-${idx}`} 
                  className={`transition-all duration-300 ${dimmed ? "opacity-15" : "opacity-100"}`}
                >
                  {/* Micro-glassmorphic background pill */}
                  <rect
                    x={xMid - 30}
                    y={yMid - 8}
                    width="60"
                    height="16"
                    rx="8"
                    fill="rgba(15, 23, 42, 0.9)"
                    stroke={highlighted ? edgeColor : "rgba(255,255,255,0.12)"}
                    strokeWidth={highlighted ? "1.5" : "1"}
                    className="transition-all duration-300"
                  />
                  {/* Edge Label text */}
                  <text
                    x={xMid}
                    y={yMid + 3}
                    textAnchor="middle"
                    className={`text-[8px] font-bold tracking-widest uppercase transition-all duration-300 select-none ${highlighted ? "fill-white font-extrabold" : "fill-slate-400"}`}
                  >
                    {edge.label}
                  </text>
                </g>
              );
            })}
          </g>

          {/* C. Symmetrical Glowing Multi-Color Nodes */}
          <g>
            {nodes.map((node) => {
              const isSelected = selectedNode === node.id;
              const isHovered = hoveredNode === node.id;
              const isDimmed = (hoveredNode || selectedNode) && !isSelected && !isHovered;
              
              // Resolve entity-specific color
              const nodeColor = NODE_COLORS[node.id] || brandPrimaryColor;

              return (
                <g
                  key={node.id}
                  transform={`translate(${node.x}, ${node.y})`}
                  className="cursor-pointer group"
                  onMouseEnter={() => setHoveredNode(node.id)}
                  onMouseLeave={() => setHoveredNode(null)}
                  onClick={() => setSelectedNode(isSelected ? null : node.id)}
                >
                  {/* Stronger glow circle behind selected/hovered nodes */}
                  {(isSelected || isHovered) && (
                    <circle
                      r="34"
                      fill={nodeColor}
                      className="opacity-25 blur-md transition-all duration-300 scale-110"
                    />
                  )}
                  
                  {/* Outer pulsing ring in entity color */}
                  <circle
                    r="28"
                    fill="none"
                    stroke={isSelected ? nodeColor : isHovered ? "rgba(255,255,255,0.4)" : "rgba(255,255,255,0.12)"}
                    strokeWidth={isSelected ? "3" : "1.5"}
                    className={`transition-all duration-300 ${isSelected ? "animate-ping opacity-20" : ""}`}
                  />
                  
                  {/* Core Node Circle - Darker background, thicker colored border */}
                  <circle
                    r="24"
                    fill={isSelected ? "rgba(15, 23, 42, 0.95)" : "rgba(17, 24, 39, 0.8)"}
                    stroke={isSelected || isHovered ? nodeColor : "rgba(255,255,255,0.2)"}
                    strokeWidth={isSelected || isHovered ? "2.5" : "1.5"}
                    className={`transition-all duration-300 ${isDimmed ? "opacity-30" : "opacity-100"}`}
                  />

                  {/* Dynamic Lucide Icon Wrapper - Colored based on state */}
                  <g 
                    className={`transition-all duration-300 ${isDimmed ? "opacity-30" : "opacity-100"}`}
                    transform="translate(-10, -10)"
                  >
                    {renderNodeIcon(
                      node.icon, 
                      20, 
                      isSelected || isHovered ? "#ffffff" : nodeColor
                    )}
                  </g>

                  {/* Node Label - Increased brightness and contrast */}
                  <text
                    y="42"
                    textAnchor="middle"
                    className={`text-[10px] font-bold tracking-widest uppercase transition-all duration-300 select-none ${isSelected ? "fill-white font-extrabold" : isHovered ? "fill-white" : "fill-slate-200"} ${isDimmed ? "opacity-20" : "opacity-100"}`}
                    style={{ textShadow: !isDimmed ? "0 2px 4px rgba(0,0,0,0.8)" : "none" }}
                  >
                    {node.label}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
        
        {/* Floating tooltip when hovering over a node */}
        {hoveredNode && !selectedNode && (
          <div 
            className="absolute bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 bg-slate-950/90 border border-white/10 rounded-xl text-[11px] text-slate-200 backdrop-blur-md flex items-center gap-1.5 shadow-xl pointer-events-none animate-fadeIn"
          >
            <span 
              className="font-bold uppercase"
              style={{ color: NODE_COLORS[hoveredNode] }}
            >
              {nodes.find(n => n.id === hoveredNode)?.label}
            </span>
            <span className="text-slate-600">|</span>
            <span className="font-medium">Click node to explore queries</span>
          </div>
        )}
      </div>

      {/* 2. Dynamic Glassmorphic Entity Inspector Card */}
      <div className="w-full lg:w-2/5 flex flex-col h-full min-h-[260px] justify-center">
        {selectedNode && activeNodeObj ? (
          <div 
            className="p-5 bg-slate-950/50 border rounded-3xl backdrop-blur-md shadow-2xl flex flex-col gap-4.5 animate-slideIn w-full transition-all duration-300"
            style={{ borderColor: `${activeNodeObj ? NODE_COLORS[selectedNode] + "30" : "rgba(255,255,255,0.06)"}` }}
          >
            {/* Entity Header */}
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

            {/* Curated Suggested Queries */}
            <div className="flex flex-col gap-2">
              <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1.5">
                <Sparkles size={11} className="animate-pulse" style={{ color: activeNodeColor }} />
                Suggested Graph Insights:
              </h4>
              <div className="flex flex-col gap-2 max-h-[160px] overflow-y-auto pr-1">
                {suggestions.map((suggestion, idx) => (
                  <button
                    key={idx}
                    onClick={() => onSelectSuggestion(suggestion)}
                    className="p-3 bg-white/4 border border-white/6 hover:bg-white/8 rounded-xl text-left text-[11px] text-slate-200 font-semibold transition cursor-pointer flex items-center justify-between group"
                    style={{ 
                      hoverBorderColor: activeNodeColor
                    } as any}
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
          <div className="p-6 bg-white/3 border border-white/6 rounded-3xl backdrop-blur-sm text-center flex flex-col gap-4 w-full max-w-sm mx-auto">
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
