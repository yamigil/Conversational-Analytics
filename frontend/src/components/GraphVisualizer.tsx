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
  const renderNodeIcon = (iconName: string, size: number = 20) => {
    switch (iconName) {
      case "users": return <Users size={size} />;
      case "shopping-bag": return <ShoppingBag size={size} />;
      case "package": return <Package size={size} />;
      case "award": return <Award size={size} />;
      case "store": return <Store size={size} />;
      default: return <Network size={size} />;
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

  return (
    <div className="w-full flex flex-col lg:flex-row gap-6 items-center justify-center py-4 select-none max-w-4xl mx-auto animate-fadeIn">
      {/* 1. Interactive Animated SVG Graph Canvas */}
      <div className="relative w-full lg:w-3/5 bg-slate-950/40 border border-white/6 rounded-3xl p-4 backdrop-blur-md shadow-inner flex items-center justify-center overflow-hidden aspect-[3/2] max-w-lg lg:max-w-none">
        {/* Subtle grid background */}
        <div className="absolute inset-0 bg-[radial-gradient(rgba(255,255,255,0.015)_1px,transparent_1px)] [background-size:16px_16px] pointer-events-none" />
        
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

              return (
                <g key={idx} className="transition-all duration-300">
                  {/* Glowing background line for highlighted connections */}
                  {highlighted && (
                    <line
                      x1={src.x}
                      y1={src.y}
                      x2={tgt.x}
                      y2={tgt.y}
                      stroke={brandPrimaryColor}
                      strokeWidth="6"
                      strokeLinecap="round"
                      className="opacity-25 blur-sm"
                    />
                  )}
                  {/* Core relationship line */}
                  <line
                    x1={src.x}
                    y1={src.y}
                    x2={tgt.x}
                    y2={tgt.y}
                    stroke={highlighted ? brandPrimaryColor : "rgba(255,255,255,0.08)"}
                    strokeWidth={highlighted ? "2.5" : "1.5"}
                    strokeDasharray={highlighted ? "none" : "5, 5"}
                    className={`transition-all duration-300 ${dimmed ? "opacity-30" : "opacity-100"}`}
                  />
                  
                  {/* Native SVG flowing particle animations */}
                  {highlighted && (
                    <circle r="4" fill={brandPrimaryColor} className="filter drop-shadow-[0_0_8px_var(--tw-shadow-color)]" style={{ shadowColor: brandPrimaryColor } as any}>
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

          {/* B. Symmetrical Glowing Nodes */}
          <g>
            {nodes.map((node) => {
              const isSelected = selectedNode === node.id;
              const isHovered = hoveredNode === node.id;
              const isDimmed = (hoveredNode || selectedNode) && !isSelected && !isHovered;

              return (
                <g
                  key={node.id}
                  transform={`translate(${node.x}, ${node.y})`}
                  className="cursor-pointer group"
                  onMouseEnter={() => setHoveredNode(node.id)}
                  onMouseLeave={() => setHoveredNode(null)}
                  onClick={() => setSelectedNode(isSelected ? null : node.id)}
                >
                  {/* Glow circle behind selected/hovered nodes */}
                  {(isSelected || isHovered) && (
                    <circle
                      r="32"
                      fill={brandPrimaryColor}
                      className="opacity-15 blur-md transition-all duration-300 scale-110"
                    />
                  )}
                  {/* Outer pulsing ring */}
                  <circle
                    r="26"
                    fill="none"
                    stroke={isSelected ? brandPrimaryColor : isHovered ? "rgba(255,255,255,0.25)" : "rgba(255,255,255,0.06)"}
                    strokeWidth={isSelected ? "2.5" : "1.5"}
                    className={`transition-all duration-300 ${isSelected ? "animate-ping opacity-10" : ""}`}
                  />
                  
                  {/* Core Node Circle */}
                  <circle
                    r="22"
                    fill={isSelected ? "rgba(15, 23, 42, 0.95)" : "rgba(30, 41, 59, 0.6)"}
                    stroke={isSelected ? brandPrimaryColor : isHovered ? "rgba(255,255,255,0.3)" : "rgba(255,255,255,0.1)"}
                    strokeWidth={isSelected ? "2" : "1"}
                    className={`transition-all duration-300 ${isDimmed ? "opacity-40" : "opacity-100"}`}
                  />

                  {/* Dynamic Lucide Icon Wrapper */}
                  <g 
                    className={`text-slate-300 transition-all duration-300 ${isSelected ? "text-white scale-110" : isHovered ? "text-white" : ""} ${isDimmed ? "opacity-40" : "opacity-100"}`}
                    transform="translate(-10, -10)"
                  >
                    {renderNodeIcon(node.icon, 20)}
                  </g>

                  {/* Symmetrical Label */}
                  <text
                    y="38"
                    textAnchor="middle"
                    className={`text-[10px] font-bold tracking-wider uppercase transition-all duration-300 select-none ${isSelected ? "fill-white font-extrabold" : isHovered ? "fill-slate-200" : "fill-slate-400"} ${isDimmed ? "opacity-30" : "opacity-100"}`}
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
            className="absolute bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 bg-slate-950/80 border border-white/8 rounded-xl text-[11px] text-slate-300 backdrop-blur-md flex items-center gap-1.5 shadow-lg pointer-events-none animate-fadeIn"
          >
            <span className="font-bold text-white uppercase">{nodes.find(n => n.id === hoveredNode)?.label}</span>
            <span className="text-slate-500">|</span>
            <span>Click to explore database connections</span>
          </div>
        )}
      </div>

      {/* 2. Dynamic Glassmorphic Entity Inspector Card */}
      <div className="w-full lg:w-2/5 flex flex-col h-full min-h-[260px] justify-center">
        {selectedNode && activeNodeObj ? (
          <div className="p-5 bg-white/3 border border-white/6 rounded-3xl backdrop-blur-md shadow-xl flex flex-col gap-4.5 animate-slideIn w-full">
            {/* Entity Header */}
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-brand-primary/10 text-brand-primary flex items-center justify-center border border-brand-primary/15">
                {renderNodeIcon(activeNodeObj.icon, 18)}
              </div>
              <div className="flex flex-col">
                <h3 className="text-sm font-bold text-white tracking-tight uppercase">{activeNodeObj.label}</h3>
                <span className="text-[10px] font-semibold text-brand-primary uppercase tracking-widest">{activeNodeObj.type}</span>
              </div>
            </div>

            {/* Entity Description */}
            <p className="text-xs text-slate-400 leading-relaxed">
              {activeNodeObj.description}
            </p>

            {/* Curated Suggested Queries */}
            <div className="flex flex-col gap-2">
              <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1">
                <Sparkles size={10} className="text-brand-primary animate-pulse" />
                Suggested Graph Insights:
              </h4>
              <div className="flex flex-col gap-2 max-h-[160px] overflow-y-auto pr-1">
                {suggestions.map((suggestion, idx) => (
                  <button
                    key={idx}
                    onClick={() => onSelectSuggestion(suggestion)}
                    className="p-3 bg-white/3 border border-white/6 hover:border-brand-primary/30 hover:bg-brand-primary/5 rounded-xl text-left text-[11px] text-slate-300 font-medium transition cursor-pointer flex items-center justify-between group"
                  >
                    <span className="group-hover:text-white transition duration-150 leading-relaxed pr-2">{suggestion}</span>
                    <ChevronRight size={12} className="text-brand-primary shrink-0 opacity-0 group-hover:opacity-100 transition-all duration-200 group-hover:translate-x-0.5" />
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="p-6 bg-white/2 border border-white/4 rounded-3xl backdrop-blur-sm text-center flex flex-col gap-4 w-full max-w-sm mx-auto">
            <div className="w-12 h-12 rounded-2xl bg-brand-primary/10 border border-brand-primary/15 text-brand-primary flex items-center justify-center mx-auto shadow-sm">
              <Network size={22} className="animate-pulse" />
            </div>
            <div className="flex flex-col gap-1">
              <h3 className="text-xs font-semibold text-white">Explore the Database Graph</h3>
              <p className="text-[10px] text-slate-500 leading-relaxed px-2">
                This agent is powered by a connected **BigQuery Graph Schema** representing key entity nodes and their relationships.
              </p>
            </div>
            <div className="p-3.5 bg-slate-950/30 border border-white/4 rounded-xl text-[10px] text-slate-400 leading-relaxed flex items-center justify-center gap-1.5 font-medium">
              <HelpCircle size={12} className="text-brand-primary shrink-0" />
              Click any node circle to reveal insights and ask questions!
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
