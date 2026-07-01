import React, { useState, useRef } from "react";
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
  FileText,
  Loader2,
  Table
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
  brandLogoSvg?: string;
  brandLogoUrl?: string;
  brandLogoText?: string;
  agentName?: string;
  fetchTablePreview?: (tableName: string, agentName?: string) => Promise<{ columns: string[], rows: any[] }>;
  isGraphAgent?: boolean;
}

const PRESET_COORDINATES: Record<string, { x: number; y: number }> = {
  // 1. The Look Graph Showcase Presets
  users: { x: 75, y: 70 },
  orders: { x: 75, y: 330 },
  products: { x: 300, y: 200 },
  brands: { x: 525, y: 70 },
  stores: { x: 525, y: 330 },
  
  // 2. Penske Customer 360 Graph Showcase Presets (spacious, wide pyramid layout)
  customers: { x: 300, y: 95 },
  web_events: { x: 90, y: 210 },
  vehicles: { x: 510, y: 210 },
  deal_jackets: { x: 190, y: 335 },
  service_visits: { x: 410, y: 335 }
};

// Vibrant color presets for flagship nodes
const PRESET_COLORS: Record<string, string> = {
  // The Look Graph
  users: "#a78bfa",      // Bright Violet/Purple
  orders: "#38bdf8",     // Bright Cyan/Blue
  products: "#34d399",    // Bright Emerald Green
  brands: "#fbbf24",     // Bright Amber Gold
  stores: "#f472b6",     // Bright Pink/Rose
  
  // Penske Customer 360 Graph
  customers: "#a78bfa",      // Bright Violet/Purple (Customer root)
  vehicles: "#38bdf8",       // Bright Cyan/Blue (Vehicles)
  service_visits: "#34d399", // Bright Emerald Green (Service Wrench)
  deal_jackets: "#fbbf24",   // Bright Amber Gold (F&I Contracts)
  web_events: "#f472b6"      // Bright Pink/Rose (GA4 Marketing)
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

const getProperty = (row: any, keyName: string): any => {
  if (!row) return undefined;
  const target = keyName.toLowerCase();
  for (const [k, v] of Object.entries(row)) {
    if (k.toLowerCase() === target) return v;
  }
  return undefined;
};

const getInstanceLabel = (nodeId: string, row: any, idx: number): string => {
  let nameVal = getProperty(row, 'name');
  if (nodeId === "customers" && !nameVal) {
    const first = getProperty(row, 'first_name');
    const last = getProperty(row, 'last_name');
    if (first || last) nameVal = `${first || ""} ${last || ""}`.trim();
  }
  if (nodeId === "customers" && nameVal) {
    return String(nameVal).split(" ").map((n: string) => n[0]).join("").slice(0, 2).toUpperCase();
  }
  if (nodeId === "orders") return `O${idx+1}`;
  if (nodeId === "products") return `P${idx+1}`;
  if (nodeId === "brands") return `B${idx+1}`;
  if (nodeId === "stores") return `S${idx+1}`;
  if (nodeId === "vehicles") return `V${idx+1}`;
  if (nodeId === "service_visits") return `SV${idx+1}`;
  if (nodeId === "deal_jackets") return `DJ${idx+1}`;
  if (nodeId === "web_events") return `WE${idx+1}`;
  return `${nodeId[0].toUpperCase()}${idx+1}`;
};

const getInstanceSuggestions = (nodeId: string, row: any): string[] => {
  if (nodeId === "customers") {
    let name = getProperty(row, 'name');
    if (!name) {
      const first = getProperty(row, 'first_name');
      const last = getProperty(row, 'last_name');
      if (first || last) name = `${first || ""} ${last || ""}`.trim();
    }
    if (!name) name = "this customer";
    const cid = getProperty(row, 'customer_id') || getProperty(row, 'id') || "";
    return [
      `Show me the complete service visit history and repair costs for customer ${name}.`,
      `List all vehicles purchased or leased by customer ID ${cid}.`,
      `What online web events and searches did customer ${name} perform?`
    ];
  }
  if (nodeId === "orders") {
    const oid = getProperty(row, 'order_id') || getProperty(row, 'id') || "this order";
    return [
      `Which customer placed order ${oid} and what is their contact email?`,
      `List the brand names and prices of all products included in order ${oid}.`,
      `Show me other orders placed by the user who made order ${oid}.`
    ];
  }
  if (nodeId === "vehicles") {
    const vin = getProperty(row, 'vin') || "this vehicle";
    return [
      `Who is the customer that purchased the vehicle with VIN ${vin}?`,
      `Show the full service ticket history, costs, and repair dates for vehicle ${vin}.`,
      `What is the credit score and loan status in the F&I deal jacket for vehicle ${vin}?`
    ];
  }
  if (nodeId === "service_visits") {
    const vid = getProperty(row, 'visit_id') || getProperty(row, 'id') || "this visit";
    const vin = getProperty(row, 'vin') || "";
    return [
      `Which customer owns the vehicle with VIN ${vin} that was serviced in visit ${vid}?`,
      `What was the total cost and service type breakdown for visit ${vid}?`,
      `Compare the service cost of visit ${vid} with our dealership average.`
    ];
  }
  if (nodeId === "deal_jackets") {
    const did = getProperty(row, 'deal_id') || getProperty(row, 'id') || "this deal";
    return [
      `Show me the profile and contact details of the customer for deal jacket ${did}.`,
      `What is the interest rate, credit score, and status of finance deal ${did}?`,
      `Which finance provider was chosen for deal jacket ${did}?`
    ];
  }
  if (nodeId === "web_events") {
    const eid = getProperty(row, 'event_id') || getProperty(row, 'id') || "this event";
    const cid = getProperty(row, 'customer_id') || "";
    return [
      `Who is the customer who triggered web event ${eid}?`,
      `What is the timestamp and details of web event ${eid}?`,
      `Show me all digital browser activities triggered by customer ID ${cid} in the last month.`
    ];
  }
  if (nodeId === "users") {
    const name = getProperty(row, 'name') || "this user";
    const uid = getProperty(row, 'id') || "";
    return [
      `List all orders placed by user ${name} including purchase dates and order status.`,
      `What are the most popular product categories browsed or purchased by user ID ${uid}?`,
      `Show the billing address and traffic source channel for user ${name}.`
    ];
  }
  if (nodeId === "products") {
    const pid = getProperty(row, 'id') || "";
    return [
      `Which other customers purchased the product with ID ${pid}?`,
      `What is the retail price, cost, and profit margin for product ID ${pid}?`,
      `Show the inventory stock levels and store locations for product ID ${pid}.`
    ];
  }
  return [
    `Show me a summary of all connected relations for this specific record.`,
    `What other tables reference the primary keys in this record?`
  ];
};

const getLocalMockSatellites = (): any[] => {
  return [
    { "id": 1, "status": "ACTIVE", "value": "Instance 1" },
    { "id": 2, "status": "ACTIVE", "value": "Instance 2" },
    { "id": 3, "status": "PENDING", "value": "Instance 3" }
  ];
};

export const GraphVisualizer: React.FC<GraphVisualizerProps> = ({
  graphData,
  onSelectSuggestion,
  brandPrimaryColor = "#3b82f6",
  brandLogoSvg,
  brandLogoUrl,
  brandLogoText,
  agentName,
  fetchTablePreview,
  isGraphAgent = true
}) => {
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [selectedInstance, setSelectedInstance] = useState<any | null>(null);
  
  const [activeTab, setActiveTab] = useState<"queries" | "preview">("queries");
  const [previewData, setPreviewData] = useState<{ columns: string[], rows: any[], recordSuggestions?: string[][] } | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState<boolean>(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // Interactive drag-to-pan & zoom states for the canvas
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });
  const mouseDownPos = useRef({ x: 0, y: 0 });


  const handleMouseDownPan = (e: React.MouseEvent<SVGSVGElement>) => {
    mouseDownPos.current = { x: e.clientX, y: e.clientY };
    const tagName = (e.target as SVGElement).tagName;
    if (tagName === "svg" || (e.target as SVGElement).id === "pan-bg-rect") {
      setIsPanning(true);
      setPanStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    }
  };

  const handleMouseMovePan = (e: React.MouseEvent<SVGSVGElement>) => {
    if (isPanning) {
      setPan({
        x: e.clientX - panStart.x,
        y: e.clientY - panStart.y
      });
    }
  };

  const handleMouseUpPan = () => {
    setIsPanning(false);
  };

  // Check if we should use the preset showcase layout
  const usePresetLayout = graphData.nodes.every(n => PRESET_COORDINATES[n.id]);

  // Dynamic Layout Engine: maps coordinates on the fly (supporting central schema root)
  const nodes: Node[] = graphData.nodes.map((n, idx) => {
    if (usePresetLayout && PRESET_COORDINATES[n.id]) {
      const dx = PRESET_COORDINATES[n.id].x - 300;
      const dy = PRESET_COORDINATES[n.id].y - 200;
      return {
        ...n,
        // Scale and center positions onto 800x460 widescreen canvas
        x: Math.round(400 + dx * 1.32),
        y: Math.round(230 + dy * 1.22)
      };
    }
    
    const hasSchemaRoot = graphData.nodes.some(node => node.id === "schema_root");
    
    if (n.id === "schema_root") {
      return {
        ...n,
        x: 400,
        y: 230
      };
    }
    
    if (hasSchemaRoot) {
      const otherNodes = graphData.nodes.filter(node => node.id !== "schema_root");
      const otherIdx = otherNodes.findIndex(node => node.id === n.id);
      const center = { x: 400, y: 230 };
      const radius = 180;
      const angle = (2 * Math.PI * otherIdx) / otherNodes.length - Math.PI / 2;
      
      return {
        ...n,
        x: Math.round(center.x + radius * Math.cos(angle)),
        y: Math.round(center.y + radius * Math.sin(angle))
      };
    }
    
    // Circular Layout distribution for custom graphs
    const center = { x: 400, y: 230 };
    const radius = 175;
    const angle = (2 * Math.PI * idx) / graphData.nodes.length - Math.PI / 2;
    
    return {
      ...n,
      x: Math.round(center.x + radius * Math.cos(angle)),
      y: Math.round(center.y + radius * Math.sin(angle))
    };
  });

  // Reset tab, selected instance, and fetch preview in background when selected node changes
  React.useEffect(() => {
    setSelectedInstance(null);
    if (!selectedNode) {
      setPreviewData(null);
      setActiveTab("queries");
      return;
    }
    
    if (selectedNode === "schema_root") {
      setPreviewData(null);
      setActiveTab("queries");
      return;
    }

    const fetchPreview = async () => {
      setIsPreviewLoading(true);
      setPreviewError(null);
      try {
        if (fetchTablePreview) {
          const data = await fetchTablePreview(selectedNode, agentName);
          setPreviewData(data);
        } else {
          const queryParams = new URLSearchParams({
            table_name: selectedNode,
            ...(agentName ? { agent_name: agentName } : {})
          });
          const res = await fetch(`/api/preview?${queryParams.toString()}`);
          if (!res.ok) throw new Error("Failed to load table data preview");
          const data = await res.json();
          setPreviewData(data);
        }
      } catch (err: any) {
        console.error("Preview fetch error:", err);
        setPreviewError(err.message || "Failed to load table data preview");
      } finally {
        setIsPreviewLoading(false);
      }
    };

    fetchPreview();
  }, [selectedNode, agentName, fetchTablePreview]);

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
    if (name.includes("table")) {
      return <Table size={size} color={color} />;
    }
    if (name.includes("db") || name.includes("database") || name.includes("schema")) {
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

  if (!isGraphAgent) {
    return (
      <div className="w-full flex flex-col gap-6 select-none max-w-4xl mx-auto animate-fadeIn">
        {/* Tables Grid Layout */}
        <div 
          className="relative w-full bg-slate-950/60 border border-white/10 rounded-3xl p-6 backdrop-blur-md shadow-2xl flex flex-col gap-5 overflow-hidden"
        >
          {/* Grid background */}
          <div className="absolute inset-0 bg-[radial-gradient(rgba(255,255,255,0.025)_1px,transparent_1px)] [background-size:20px_20px] pointer-events-none" />
          
          {/* Top Header */}
          <div className="relative z-10 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Database className="text-brand-primary" size={18} style={{ color: brandPrimaryColor }} />
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200">
                Connected Dataset Tables
              </h3>
            </div>
            <span className="text-[10px] bg-white/5 border border-white/6 px-2.5 py-1 rounded-full text-slate-400 font-semibold uppercase tracking-wider">
              {nodes.filter(n => n.id !== "schema_root").length} Tables Available
            </span>
          </div>

          {/* Tables Grid */}
          <div className="relative z-10 flex flex-wrap justify-center gap-4 w-full">
            {nodes.filter(n => n.id !== "schema_root").map((node, idx) => {
              const isSelected = selectedNode === node.id;
              const isHovered = hoveredNode === node.id;
              const nodeColor = getNodeColor(node.id, idx);
              
              return (
                <div
                  key={node.id}
                  onClick={() => {
                    setSelectedNode(isSelected ? null : node.id);
                  }}
                  onMouseEnter={() => setHoveredNode(node.id)}
                  onMouseLeave={() => setHoveredNode(null)}
                  className={`group relative p-4 rounded-xl border cursor-pointer flex flex-col gap-3 min-h-[120px] flex-1 min-w-[240px] max-w-[320px] table-card-3d ${
                    isSelected
                      ? "bg-brand-primary/10 border-brand-primary/60 shadow-[0_0_15px_rgba(59,130,246,0.15)]"
                      : "bg-slate-900/40 border-white/6 hover:bg-slate-950/60 hover:border-white/12"
                  }`}
                  style={isSelected ? { borderColor: `${nodeColor}60`, backgroundColor: `${nodeColor}10` } : {}}
                >
                  <div className="flex items-center justify-between">
                    <div 
                      className="p-2 rounded-lg bg-white/5 group-hover:bg-brand-primary/10 transition"
                      style={isSelected || isHovered ? { backgroundColor: `${nodeColor}15` } : {}}
                    >
                      {renderNodeIcon(node.icon, 16, isSelected || isHovered ? nodeColor : "#94a3b8")}
                    </div>
                    {isSelected && (
                      <span className="w-1.5 h-1.5 rounded-full bg-brand-primary animate-pulse" style={{ backgroundColor: nodeColor }} />
                    )}
                  </div>
                  <div>
                    <h4 
                      className={`text-xs font-bold transition ${isSelected ? "text-white" : "text-slate-200"}`}
                      style={isSelected ? { color: nodeColor } : {}}
                    >
                      {node.label}
                    </h4>
                    <p className="text-[10px] text-slate-400 font-medium mt-1 line-clamp-2">
                      {node.description || "Connected database table containing records for analytical queries."}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
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
                    style={{ borderColor: `${activeNodeColor}40`, backgroundColor: `${activeNodeColor}10` }}
                  >
                    {renderNodeIcon(activeNodeObj.icon, 20, activeNodeColor)}
                  </div>
                  <div>
                    <h3 className="text-xs font-extrabold uppercase tracking-wider text-white">
                      {activeNodeObj.label}
                    </h3>
                    <span 
                      className="text-[9px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded bg-white/5 border border-white/8 block mt-1 w-max"
                      style={{ color: activeNodeColor, borderColor: `${activeNodeColor}20` }}
                    >
                      Table
                    </span>
                  </div>
                </div>
                <p className="text-xs text-slate-300 leading-relaxed font-medium">
                  {activeNodeObj.description}
                </p>
              </div>

              {/* COLUMN 2: Tabs (Queries & Data Preview) */}
              <div className="flex flex-col gap-4 min-h-[160px]">
                <div className="flex items-center gap-4 border-b border-white/6 pb-2">
                  <button
                    onClick={() => setActiveTab("queries")}
                    className={`flex items-center gap-1.5 pb-1 text-xs font-bold uppercase tracking-wider transition cursor-pointer border-none bg-transparent ${
                      activeTab === "queries" 
                        ? "text-slate-200 border-b-2 border-brand-primary" 
                        : "text-slate-500 hover:text-slate-300"
                    }`}
                    style={activeTab === "queries" ? { borderBottomColor: activeNodeColor } : {}}
                  >
                    <HelpCircle size={13} />
                    Suggested Insights
                  </button>
                  <button
                    onClick={() => setActiveTab("preview")}
                    className={`flex items-center gap-1.5 pb-1 text-xs font-bold uppercase tracking-wider transition cursor-pointer border-none bg-transparent ${
                      activeTab === "preview" 
                        ? "text-slate-200 border-b-2 border-brand-primary" 
                        : "text-slate-500 hover:text-slate-300"
                    }`}
                    style={activeTab === "preview" ? { borderBottomColor: activeNodeColor } : {}}
                  >
                    <Database size={13} />
                    Data Preview
                  </button>
                </div>

                <div className="flex-1 overflow-y-auto max-h-[180px] custom-scrollbar pr-1">
                  {activeTab === "queries" ? (
                    <div className="flex flex-col gap-2">
                      {suggestions.map((q, qIdx) => (
                        <div 
                          key={qIdx}
                          onClick={() => onSelectSuggestion(q)}
                          className="flex items-center justify-between p-2.5 rounded-xl bg-white/4 hover:bg-white/8 border border-white/6 hover:border-white/12 transition cursor-pointer group"
                        >
                          <span className="text-xs text-slate-300 group-hover:text-white transition font-medium">
                            {q}
                          </span>
                          <ChevronRight size={14} className="text-slate-500 group-hover:text-white transition transform group-hover:translate-x-0.5" />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="w-full h-full min-h-[120px] flex flex-col justify-center">
                      {isPreviewLoading ? (
                        <div className="flex flex-col items-center justify-center gap-2.5 py-4">
                          <Loader2 size={24} className="text-brand-primary animate-spin" style={{ color: activeNodeColor }} />
                          <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider animate-pulse">
                            Fetching Live BigQuery Preview...
                          </span>
                        </div>
                      ) : previewError ? (
                        <div className="flex flex-col items-center justify-center gap-1.5 py-4 text-center">
                          <HelpCircle size={20} className="text-rose-400" />
                          <span className="text-[10.5px] text-rose-300 font-bold">
                            {previewError}
                          </span>
                        </div>
                      ) : previewData && previewData.rows.length > 0 ? (
                        <div className="w-full overflow-x-auto rounded-xl border border-white/6 bg-slate-950/30">
                          <table className="w-full text-left border-collapse">
                            <thead>
                              <tr className="border-b border-white/8 bg-slate-900/40">
                                {previewData.columns.map((col) => (
                                  <th 
                                    key={col} 
                                    className="px-3 py-2 text-[9px] font-bold text-slate-400 uppercase tracking-wider sticky top-0 bg-slate-900/80 backdrop-blur-sm"
                                  >
                                    {col}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {previewData.rows.map((row, rIdx) => (
                                <tr 
                                  key={rIdx} 
                                  className="border-b border-white/4 hover:bg-white/2 transition"
                                >
                                  {previewData.columns.map((col) => {
                                    const val = row[col];
                                    return (
                                      <td 
                                        key={col} 
                                        className="px-3 py-1.5 text-[10.5px] font-medium text-slate-300 truncate max-w-[150px]"
                                      >
                                        {val === null || val === undefined ? (
                                          <span className="text-[9px] text-slate-600 font-bold italic">null</span>
                                        ) : typeof val === "object" ? (
                                          JSON.stringify(val)
                                        ) : (
                                          String(val)
                                        )}
                                      </td>
                                    );
                                  })}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <div className="flex items-center justify-center py-6 text-slate-500 text-[10.5px] font-semibold italic">
                          No records found.
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="w-full p-6 bg-slate-950/40 border border-white/6 rounded-3xl flex flex-col items-center justify-center text-center gap-2.5 animate-fadeIn">
              <div className="p-3 rounded-full bg-white/4 border border-white/6">
                <Database className="text-slate-400" size={20} />
              </div>
              <div>
                <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                  Explore Dataset Tables
                </h4>
                <p className="text-[10.5px] text-slate-500 font-medium mt-1">
                  Select any table card above to inspect its columns, suggested queries, and live BigQuery data preview.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="w-full flex flex-col gap-6 items-center pt-0 pb-2 select-none max-w-7xl mx-auto animate-fadeIn">
      {/* 1. Interactive Animated SVG Graph Canvas */}
      <div 
        className="relative w-full bg-slate-950/60 border border-white/10 rounded-3xl p-4 backdrop-blur-md shadow-2xl flex items-center justify-center overflow-hidden aspect-[16/9] md:aspect-[2/1] w-full"
      >
        {/* Grid background */}
        <div className="absolute inset-0 bg-[radial-gradient(rgba(255,255,255,0.025)_1px,transparent_1px)] [background-size:20px_20px] pointer-events-none" />
        
        {/* Floating Pan & Zoom Controls UI */}
        <div className="absolute bottom-4 right-4 flex gap-1.5 z-20">
          <button 
            onClick={(e) => { e.stopPropagation(); setZoom(z => Math.min(z * 1.1, 2.5)); }}
            className="w-7 h-7 bg-slate-900/80 hover:bg-slate-800 border border-white/10 rounded-lg text-slate-300 flex items-center justify-center text-xs font-bold transition cursor-pointer select-none"
            title="Zoom In"
          >
            +
          </button>
          <button 
            onClick={(e) => { e.stopPropagation(); setZoom(z => Math.max(z / 1.1, 0.6)); }}
            className="w-7 h-7 bg-slate-900/80 hover:bg-slate-800 border border-white/10 rounded-lg text-slate-300 flex items-center justify-center text-xs font-bold transition cursor-pointer select-none"
            title="Zoom Out"
          >
            -
          </button>
          <button 
            onClick={(e) => { e.stopPropagation(); setPan({ x: 0, y: 0 }); setZoom(1); }}
            className="px-2 h-7 bg-slate-900/80 hover:bg-slate-800 border border-white/10 rounded-lg text-slate-300 flex items-center justify-center text-[10px] font-bold uppercase tracking-wider transition cursor-pointer select-none"
            title="Reset View"
          >
            Reset
          </button>
        </div>

        <svg 
          viewBox="0 -30 800 505" 
          className={`w-full h-full overflow-visible ${isPanning ? 'cursor-grabbing' : 'cursor-default'}`}
          onMouseDown={handleMouseDownPan}
          onMouseMove={handleMouseMovePan}
          onMouseUp={handleMouseUpPan}
          onMouseLeave={handleMouseUpPan}
          onWheel={(e) => {
            const zoomFactor = 1.08;
            if (e.deltaY < 0) {
              setZoom(z => Math.min(z * zoomFactor, 2.5));
            } else {
              setZoom(z => Math.max(z / zoomFactor, 0.6));
            }
          }}
          onClick={(e) => {
            const dx = e.clientX - mouseDownPos.current.x;
            const dy = e.clientY - mouseDownPos.current.y;
            const distance = Math.sqrt(dx * dx + dy * dy);
            if (distance > 5) return;

            if (e.target === e.currentTarget || (e.target as SVGElement).id === "pan-bg-rect") {
              setSelectedNode(null);
              setSelectedInstance(null);
            }
          }}
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
            
            {/* 3D sphere glossy glass shine overlay */}
            <radialGradient id="glossy-3d-gradient" cx="30%" cy="30%" r="70%">
              <stop offset="0%" stopColor="#ffffff" stopOpacity="0.3" />
              <stop offset="50%" stopColor="#ffffff" stopOpacity="0" />
              <stop offset="100%" stopColor="#000000" stopOpacity="0.45" />
            </radialGradient>
          </defs>
          
          {/* Invisible backdrop rect to capture panning drags anywhere in the SVG container */}
          <rect id="pan-bg-rect" width="1200" height="800" x="-200" y="-150" fill="transparent" />

          <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
          {/* Subtle watermark of the brand logo in the background */}
          {brandLogoSvg ? (
            <g 
              className="opacity-[0.02] pointer-events-none select-none text-slate-100"
              transform="translate(300, 200) scale(1.8)"
              dangerouslySetInnerHTML={{ __html: brandLogoSvg }}
              style={{ transformOrigin: "center" }}
            />
          ) : brandLogoUrl ? (
            <image
              href={brandLogoUrl}
              x="200"
              y="100"
              width="200"
              height="200"
              className="opacity-[0.02] pointer-events-none select-none"
            />
          ) : brandLogoText ? (
            <text
              x="300"
              y="215"
              textAnchor="middle"
              className="text-[42px] font-bold font-heading fill-white opacity-[0.015] uppercase tracking-[12px] pointer-events-none select-none"
            >
              {brandLogoText}
            </text>
          ) : null}

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

              const isSelfLoop = edge.source === edge.target;

              if (isSelfLoop) {
                // Render curved teardrop loop path for self-loops (spacious & beautiful!)
                const pathData = `M ${src.x + 10} ${src.y - 32} C ${src.x + 45} ${src.y - 85}, ${src.x - 45} ${src.y - 85}, ${src.x - 10} ${src.y - 32}`;
                return (
                  <g key={idx} className="transition-all duration-300">
                    {/* Glowing background line for highlighted connections */}
                    {highlighted && (
                      <path
                        d={pathData}
                        fill="none"
                        stroke={edgeColor}
                        strokeWidth="5"
                        strokeLinecap="round"
                        className="opacity-30 blur-sm"
                      />
                    )}
                    {/* Core relationship line */}
                    <path
                      d={pathData}
                      fill="none"
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
                          dur="2.5s"
                          repeatCount="indefinite"
                          path={pathData}
                        />
                      </circle>
                    )}
                  </g>
                );
              }

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

              // Calculate midpoint and normal vector offset for curvature
              const mx = (x1 + x2) / 2;
              const my = (y1 + y2) / 2;
              const curveOffset = 30; // Subtle curve
              const curveX = mx - uy * curveOffset;
              const curveY = my + ux * curveOffset;
              const pathData = `M ${x1} ${y1} Q ${curveX} ${curveY} ${x2} ${y2}`;

              return (
                <g key={idx} className="transition-all duration-300">
                  {/* Glowing background line for highlighted connections */}
                  {highlighted && (
                    <path
                      d={pathData}
                      fill="none"
                      stroke={edgeColor}
                      strokeWidth="5"
                      strokeLinecap="round"
                      className="opacity-30 blur-sm"
                    />
                  )}
                  {/* Core relationship line */}
                  <path
                    d={pathData}
                    fill="none"
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
                        path={pathData}
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

              const isSelfLoop = edge.source === edge.target;
              let xLabel, yLabel;
              if (isSelfLoop) {
                xLabel = src.x;
                yLabel = src.y - 72;
              } else {
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

                // Midpoint normal vector offset
                const mx = (x1 + x2) / 2;
                const my = (y1 + y2) / 2;
                const curveOffset = 30;
                const curveX = mx - uy * curveOffset;
                const curveY = my + ux * curveOffset;

                // Bezier curve midpoint calculation
                xLabel = 0.25 * x1 + 0.5 * curveX + 0.25 * x2;
                yLabel = 0.25 * y1 + 0.5 * curveY + 0.25 * y2;
              }

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
                        x={xLabel - rectWidth / 2}
                        y={yLabel - rectHeight / 2}
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
                    x={xLabel}
                    y={yLabel + 3}
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
              
              let satellites: any[] = [];
              if (isSelected && !isPreviewLoading) {
                if (previewData && previewData.rows && previewData.rows.length > 0) {
                  satellites = previewData.rows.slice(0, 3);
                } else if (previewError || !previewData) {
                  satellites = getLocalMockSatellites();
                }
              }

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
                  {/* Satellites Orbiting Nodes (Exploratory Data Nodes - SCALED UP FOR PREMIUM VISIBILITY) */}
                  {satellites.map((sat, sIdx) => {
                    const satelliteRadius = 92; // Spaced out further
                    const angle = (2 * Math.PI * sIdx) / satellites.length - Math.PI / 2;
                    const satX = satelliteRadius * Math.cos(angle);
                    const satY = satelliteRadius * Math.sin(angle);
                    
                    return (
                      <g key={sIdx} className="animate-fadeIn">
                        {/* Connection track to satellite */}
                        <line
                          x1={0}
                          y1={0}
                          x2={satX}
                          y2={satY}
                          stroke={nodeColor}
                          strokeWidth="2" // Thicker track
                          strokeDasharray="4,4"
                          className="opacity-60"
                        />
                        
                        {/* Interactive Satellite Circle */}
                        <g
                          transform={`translate(${satX}, ${satY})`}
                          className="cursor-pointer group/sat"
                          onClick={(e) => {
                            e.stopPropagation(); // Prevent toggling the main node
                            setSelectedInstance(selectedInstance === sat ? null : sat);
                          }}
                        >
                          {/* Pulsing glow on active satellite */}
                          {selectedInstance === sat && (
                            <circle
                              r="24" // Larger glow radius
                              fill={nodeColor}
                              className="opacity-35 blur-md animate-pulse"
                            />
                          )}
                          
                          {/* Hover ping indicator */}
                          <circle
                            r="24" // Larger hover ping radius
                            fill="none"
                            stroke={nodeColor}
                            strokeWidth="1.5"
                            className="opacity-0 group-hover/sat:opacity-100 group-hover/sat:animate-ping duration-300"
                          />
                          
                          {/* Satellite Core (Subnode) */}
                          <circle
                            r="18" // Subnode core radius increased from 12 to 18!
                            fill="rgba(15, 23, 42, 0.95)"
                            stroke={selectedInstance === sat ? "#ffffff" : nodeColor}
                            strokeWidth={selectedInstance === sat ? "2.5" : "1.8"} // Stronger borders
                            className="transition-all duration-200 hover:scale-110 shadow-lg"
                          />
                          <circle
                            r="18"
                            fill="url(#glossy-3d-gradient)"
                            className="pointer-events-none"
                          />
                          
                          {/* Satellite Text Label (Initials or entity indices) */}
                          <text
                            y="4.5" // Centered vertically for larger font
                            textAnchor="middle"
                            className="text-[10px] font-black fill-slate-200 select-none group-hover/sat:fill-white uppercase tracking-wider"
                          >
                            {getInstanceLabel(node.id, sat, sIdx)}
                          </text>
                        </g>
                      </g>
                    );
                  })}
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
                    className={`transition-all duration-300 graph-core-circle ${isDimmed ? "opacity-30" : "opacity-100"}`}
                  />
                  <circle
                    r="28"
                    fill="url(#glossy-3d-gradient)"
                    className={`pointer-events-none transition-all duration-300 graph-glossy-circle ${isDimmed ? "opacity-30" : "opacity-100"}`}
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
            {selectedInstance ? (
              /* ========================================================================= */
              /* STATE A: Specific Record Instance Inspector                               */
              /* ========================================================================= */
              <>
                {/* COLUMN 1: Dynamic Instance Fields */}
                <div className="flex flex-col gap-3.5">
                  <div className="flex items-center gap-3">
                    <div 
                      className="w-10 h-10 rounded-xl flex items-center justify-center border relative"
                      style={{ 
                        backgroundColor: `${activeNodeColor}15`,
                        borderColor: `${activeNodeColor}40`
                      }}
                    >
                      {renderNodeIcon(activeNodeObj.icon, 18, activeNodeColor)}
                      {/* Live verification badge */}
                      <div className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded-full bg-emerald-500 border border-slate-950 flex items-center justify-center text-[7px] font-bold text-white shadow-sm">
                        ✓
                      </div>
                    </div>
                    <div className="flex flex-col">
                      <h3 className="text-xs font-extrabold text-white tracking-tight uppercase">
                        {activeNodeObj.label.endsWith("s") || activeNodeObj.label.endsWith("S") ? activeNodeObj.label.slice(0, -1) : activeNodeObj.label} Record Instance
                      </h3>
                      <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400">
                        Live Database Entity
                      </span>
                    </div>
                  </div>
                  
                  {/* Grid of properties */}
                  <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 bg-white/2 border border-white/5 rounded-2xl p-3 text-[10.5px]">
                    {Object.entries(selectedInstance)
                      .slice(0, 6) // Show first 6 key-value properties
                      .map(([key, val]) => (
                        <div key={key} className="flex flex-col gap-0.5 py-0.5 border-b border-white/3">
                          <span className="text-[8px] uppercase font-bold text-slate-500 tracking-wider select-none">{key.replace("_", " ")}</span>
                          <span className="font-semibold text-slate-300 truncate" title={String(val)}>
                            {val !== null && val !== undefined ? String(val) : <span className="text-slate-600">NULL</span>}
                          </span>
                        </div>
                      ))}
                  </div>
                </div>
                
                {/* COLUMN 2: Contextual Suggestions */}
                <div className="flex flex-col gap-3 min-h-[180px]">
                  <div className="flex items-center border-b border-white/10 pb-1.5 gap-2">
                    <Sparkles size={11} className="animate-pulse" style={{ color: activeNodeColor }} />
                    <span className="text-[10px] font-bold uppercase tracking-widest text-white">Suggested Record Insights</span>
                  </div>
                  <div className="flex flex-col gap-2 max-h-[145px] overflow-y-auto pr-1">
                    {(() => {
                      const instanceIdx = previewData?.rows?.indexOf(selectedInstance);
                      const suggestionsList = (instanceIdx !== undefined && instanceIdx !== -1 && previewData?.recordSuggestions?.[instanceIdx] && previewData.recordSuggestions[instanceIdx].length > 0)
                        ? previewData.recordSuggestions[instanceIdx]
                        : getInstanceSuggestions(selectedNode, selectedInstance);
                      
                      return suggestionsList.map((suggestion, idx) => (
                        <button
                          key={idx}
                          onClick={() => onSelectSuggestion(suggestion)}
                          className="p-2.5 bg-white/4 border border-white/6 hover:bg-white/8 rounded-xl text-left text-[11px] text-slate-200 font-semibold transition cursor-pointer flex items-center justify-between group"
                        >
                          <span className="group-hover:text-white transition duration-150 leading-relaxed pr-2">{suggestion}</span>
                          <ChevronRight 
                            size={12} 
                            className="shrink-0 opacity-0 group-hover:opacity-100 transition-all duration-200 group-hover:translate-x-0.5"
                            style={{ color: activeNodeColor }}
                          />
                        </button>
                      ));
                    })()}
                  </div>
                </div>
              </>
            ) : (
              /* ========================================================================= */
              /* STATE B: Standard Table Schema Inspector                                  */
              /* ========================================================================= */
              <>
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

                {/* COLUMN 2: Tabs for Suggestions vs. Data Preview */}
                <div className="flex flex-col gap-3 min-h-[180px]">
                  {/* Tab Headers */}
                  <div className="flex items-center border-b border-white/10 pb-1.5 gap-4">
                    <button
                      onClick={() => setActiveTab("queries")}
                      className={`text-[10px] font-bold uppercase tracking-widest flex items-center gap-1.5 pb-1 cursor-pointer transition border-b-2 border-transparent bg-transparent p-0 ${activeTab === "queries" ? "text-white border-white" : "text-slate-400 hover:text-slate-300"}`}
                      style={activeTab === "queries" ? { borderBottomColor: activeNodeColor } : {}}
                    >
                      <Sparkles size={11} className={activeTab === "queries" ? "animate-pulse" : ""} style={{ color: activeNodeColor }} />
                      Suggested Insights
                    </button>
                    {selectedNode !== "schema_root" && (
                      <button
                        onClick={() => setActiveTab("preview")}
                        className={`text-[10px] font-bold uppercase tracking-widest flex items-center gap-1.5 pb-1 cursor-pointer transition border-b-2 border-transparent bg-transparent p-0 ${activeTab === "preview" ? "text-white border-white" : "text-slate-400 hover:text-slate-300"}`}
                        style={activeTab === "preview" ? { borderBottomColor: activeNodeColor } : {}}
                      >
                        <Database size={11} style={{ color: activeNodeColor }} />
                        Data Preview
                      </button>
                    )}
                  </div>

                  {/* Tab Contents */}
                  <div className="flex-1 flex flex-col min-h-0">
                    {activeTab === "queries" ? (
                      /* TAB 1: Suggestions List */
                      <div className="flex flex-col gap-2 max-h-[145px] overflow-y-auto pr-1">
                        {suggestions.map((suggestion, idx) => (
                          <button
                            key={idx}
                            onClick={() => onSelectSuggestion(suggestion)}
                            className="p-2.5 bg-white/4 border border-white/6 hover:bg-white/8 rounded-xl text-left text-[11px] text-slate-200 font-semibold transition cursor-pointer flex items-center justify-between group"
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
                    ) : (
                      /* TAB 2: Data Preview Table Grid */
                      <div className="flex-1 flex flex-col justify-center min-h-0 max-h-[145px]">
                        {isPreviewLoading ? (
                          <div className="flex items-center justify-center gap-2 text-slate-400 py-6">
                            <Loader2 size={16} className="animate-spin" style={{ color: activeNodeColor }} />
                            <span className="text-[10px] font-bold uppercase tracking-widest">Fetching live preview...</span>
                          </div>
                        ) : previewError ? (
                          <div className="text-center py-4 text-xs text-rose-400/80 font-medium">
                            {previewError}
                          </div>
                        ) : previewData && previewData.rows.length > 0 ? (
                          <div className="w-full overflow-x-auto border border-white/10 rounded-xl max-h-[140px] overflow-y-auto">
                            <table className="w-full text-left border-collapse text-[10px]">
                              <thead>
                                <tr className="bg-slate-950 border-b border-white/10">
                                  {previewData.columns.map((col) => (
                                    <th 
                                      key={col} 
                                      className="px-3 py-2 text-slate-400 font-bold uppercase tracking-wider whitespace-nowrap sticky top-0 bg-slate-950"
                                    >
                                      {col}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {previewData.rows.map((row, rIdx) => (
                                  <tr key={rIdx} className="border-b border-white/5 hover:bg-white/3 transition">
                                    {previewData.columns.map((col) => (
                                      <td key={col} className="px-3 py-2 text-slate-200 font-medium whitespace-nowrap">
                                        {row[col] !== null && row[col] !== undefined ? String(row[col]) : <span className="text-slate-600">NULL</span>}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : (
                          <div className="text-center py-6 text-[10px] font-bold text-slate-500 uppercase tracking-widest">
                            No data records available.
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}
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
