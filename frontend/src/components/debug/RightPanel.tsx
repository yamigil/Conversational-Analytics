import React, { useState, useEffect } from "react";
import { Activity, Database, RefreshCw, X, Maximize2, Minimize2, User, Cpu, Cloud, Layers } from "lucide-react";
import { authenticatedFetch } from "../../utils/api";

interface TraceSpan {
  span_id: string;
  parent_span_id: string | null;
  name: string;
  service: string;
  status: string;
  latency_ms: number;
  timestamp: string;
  metadata?: Record<string, any>;
  request_payload?: Record<string, any>;
  response_payload?: Record<string, any>;
}

interface TraceSessionData {
  conversation_name: string;
  spans: TraceSpan[];
}

interface RightPanelProps {
  isOpen: boolean;
  onClose: () => void;
  conversationName: string;
  messagesLength?: number;
}

export const RightPanel: React.FC<RightPanelProps> = ({ isOpen, onClose, conversationName, messagesLength }) => {
  const [traceData, setTraceData] = useState<TraceSessionData | null>(null);
  const [loading, setLoading] = useState(false);
  const [isExpandedWidth, setIsExpandedWidth] = useState(false);
  const [selectedFlowNode, setSelectedFlowNode] = useState<string>("gemini_engine");

  const fetchTrace = async () => {
    if (!conversationName) return;
    setLoading(true);
    try {
      const res = await authenticatedFetch(`/api/debug/trace/session/${encodeURIComponent(conversationName)}`);
      if (res.ok) {
        const data = await res.json();
        setTraceData(data);
      }
    } catch (e) {
      console.error("Failed to load trace session data:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!conversationName || messagesLength === 0) {
      setTraceData(null);
      return;
    }
    if (isOpen && conversationName) {
      fetchTrace();
    }
  }, [isOpen, conversationName, messagesLength]);

  if (!isOpen) return null;



  return (
    <aside className={`${isExpandedWidth ? "w-[760px]" : "w-[450px]"} shrink-0 bg-slate-950/95 border-l border-white/10 flex flex-col h-full z-30 shadow-2xl animate-slideInRight backdrop-blur-xl transition-all duration-300`}>
      {/* Header */}
      <div className="p-4 border-b border-white/10 flex items-center justify-between bg-white/2">
        <div className="flex items-center gap-2">
          <Activity className="text-sky-400" size={18} />
          <h3 className="font-heading font-semibold text-sm text-white tracking-tight">OpenTelemetry Trace Inspector</h3>
        </div>
        <div className="flex items-center gap-2">
          <button 
            onClick={() => setIsExpandedWidth(!isExpandedWidth)}
            title={isExpandedWidth ? "Compact View (450px)" : "Widescreen Deep Inspection (760px)"}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5 transition cursor-pointer flex items-center gap-1 text-[11px]"
          >
            {isExpandedWidth ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
          <button 
            onClick={fetchTrace}
            disabled={loading}
            title="Refresh Trace Spans"
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5 transition cursor-pointer"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
          <button 
            onClick={onClose}
            title="Close Inspector"
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5 transition cursor-pointer"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
        {loading && !traceData ? (
          <div className="flex flex-col items-center justify-center py-12 gap-3 text-slate-400">
            <RefreshCw size={24} className="animate-spin text-sky-400" />
            <p className="text-xs font-medium">Inspecting OpenTelemetry session spans...</p>
          </div>
        ) : !traceData || traceData.spans.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 gap-2 text-slate-500 text-center">
            <Database size={28} className="text-slate-600 mb-1" />
            <p className="text-xs font-medium text-slate-400">No active trace spans detected.</p>
            <p className="text-[11px] max-w-[240px]">Ask a conversational question to inspect real-time Gemini LLM SQL generation and tool execution latencies.</p>
          </div>
        ) : (
          (() => {
            const spanRoot = traceData.spans.find(s => s.name === "invoke_agent");
            const spanSchema = traceData.spans.find(s => s.name === "schema_discovery");
            const spanLlm = traceData.spans.find(s => s.name === "call_llm");
            const spanTool = traceData.spans.find(s => s.name === "tool_intercept");

            const isFreeForm = spanRoot?.metadata?.mode === "Free Form Mode" || spanSchema?.metadata?.mode === "Free Form Mode";

            const flowNodes = [
              {
                id: "frontend",
                label: "🖥️ Frontend Portal",
                sub: "React Client",
                icon: <User size={22} className="text-sky-400" />,
                time: "Start",
                color: "border-sky-500/50 bg-sky-500/15 text-sky-300",
                input: { action: "Submit Chat Prompt / Free Form SQL", client: "React Dashboard v0.13.1", auth_mode: spanRoot?.metadata?.auth_mode || "Bearer Token / ADC" },
                output: { event_stream: "Server-Sent Events (SSE)", messages_inspected: spanRoot?.metadata?.messages_inspected || 0 }
              },
              {
                id: "agent_context",
                label: isFreeForm ? "⚡ Free Form Mode" : "🤖 Data Agent Engine",
                sub: isFreeForm ? "Inline Schema Context" : "RAG Hybrid Search",
                icon: <Layers size={22} className="text-purple-400" />,
                time: `${spanSchema?.latency_ms || 0} ms`,
                color: "border-purple-500/50 bg-purple-500/15 text-purple-300",
                input: { agent_id: spanRoot?.metadata?.agent_id || "inline_context", retrieval_strategy: spanSchema?.metadata?.retrieval_strategy || "Hybrid Vector + Keyword Search" },
                output: { active_tables: spanSchema?.metadata?.tables_referenced || ["Dynamic Agent Context"], grounding_status: "Validated against BigQuery INFORMATION_SCHEMA" }
              },
              {
                id: "ca_api",
                label: "☁️ CA API Service",
                sub: "chat_stream (v1alpha)",
                icon: <Cloud size={22} className="text-blue-400" />,
                time: `${spanRoot?.latency_ms || 0} ms`,
                color: "border-blue-500/50 bg-blue-500/15 text-blue-300",
                input: { conversation_name: traceData.conversation_name, stream: true, total_turn_latency_ms: spanRoot?.latency_ms || 0 },
                output: { status: spanRoot?.status || "OK", session_state: "Persisted in Google Cloud Conversational Analytics Service" }
              },
              {
                id: "gemini_engine",
                label: "🧠 Gemini Engine",
                sub: "Reasoning & SQL Gen",
                icon: <Cpu size={22} className="text-emerald-400" />,
                time: `${spanLlm?.latency_ms || 0} ms`,
                color: "border-emerald-500/50 bg-emerald-500/15 text-emerald-300",
                input: spanLlm?.request_payload || { system_instruction: "Loading instructions...", temperature: 0.2, top_p: 0.95 },
                output: spanLlm?.response_payload || { sql_generated: "No SQL generated", status: "COMPLETED" }
              },
              {
                id: "bigquery",
                label: "🗄️ BigQuery Engine",
                sub: "execute_sql_query",
                icon: <Database size={22} className="text-amber-400" />,
                time: `${spanTool?.latency_ms || 0} ms`,
                color: "border-amber-500/50 bg-amber-500/15 text-amber-300",
                input: { tool_name: "execute_sql_query", sql_query: spanLlm?.response_payload?.sql_generated || "SELECT ..." },
                output: spanTool?.metadata || { rows_returned: 0, bytes_billed: 0, status: "OK" }
              }
            ];

            const activeNodeObj = flowNodes.find(n => n.id === selectedFlowNode) || flowNodes[3];

            return (
              <div className="flex flex-col gap-5">
                {/* Visual Architecture Flowchart */}
                <div className="p-4 bg-slate-900/90 border border-white/10 rounded-2xl flex flex-col gap-3 shadow-xl">
                  <div className="flex items-center justify-between border-b border-white/10 pb-2.5">
                    <span className="text-xs font-heading font-bold text-slate-200 flex items-center gap-1.5">
                      <Activity size={15} className="text-sky-400" /> Interactive Architecture Flowchart
                    </span>
                    <span className="text-[10px] text-sky-400 font-medium bg-sky-500/10 px-2.5 py-0.5 rounded-full border border-sky-500/20">
                      Click any node below to inspect raw input/output
                    </span>
                  </div>

                  <div className="flex items-center justify-between gap-1.5 overflow-x-auto py-2 px-1 custom-scrollbar">
                    {flowNodes.map((node, i) => {
                      const isSelected = selectedFlowNode === node.id;
                      return (
                        <React.Fragment key={node.id}>
                          <div 
                            onClick={() => setSelectedFlowNode(node.id)}
                            className={`flex flex-col items-center p-3 rounded-xl border cursor-pointer transition-all duration-200 select-none min-w-[125px] flex-1 text-center ${isSelected ? `${node.color} ring-2 ring-white/20 shadow-lg scale-[1.03]` : 'bg-white/2 border-white/8 hover:bg-white/5 text-slate-300 hover:border-white/15'}`}
                          >
                            <div className="mb-2 p-1.5 rounded-lg bg-black/30 border border-white/5">{node.icon}</div>
                            <span className="text-[11.5px] font-bold tracking-tight text-center leading-snug w-full whitespace-normal">{node.label}</span>
                            <span className="text-[9.5px] text-slate-400 text-center leading-tight w-full whitespace-normal mt-1">{node.sub}</span>
                            <span className="mt-2.5 px-2 py-0.5 rounded text-[9.5px] font-mono font-bold bg-black/50 border border-white/10 text-slate-200">
                              {node.time}
                            </span>
                          </div>
                          {i < flowNodes.length - 1 && (
                            <div className="text-slate-500 shrink-0 flex items-center justify-center font-bold text-sm select-none px-0.5">
                              ➔
                            </div>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </div>
                </div>

                {/* Selected Node Deep-Dive Inspector */}
                <div className="p-4 bg-slate-900/70 border border-white/12 rounded-2xl flex flex-col gap-3 shadow-lg">
                  <div className="flex items-center justify-between border-b border-white/10 pb-2.5">
                    <div className="flex items-center gap-2">
                      {activeNodeObj.icon}
                      <span className="text-xs font-heading font-bold text-white">{activeNodeObj.label} — Raw Input & Output</span>
                    </div>
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-white/5 border border-white/10 text-slate-300 font-semibold">
                      {activeNodeObj.sub} ({activeNodeObj.time})
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div className="flex flex-col gap-1.5 bg-slate-950/90 p-3 rounded-xl border border-white/10 shadow-inner">
                      <span className="text-[10.5px] uppercase tracking-wider font-sans font-bold text-sky-400 flex items-center gap-1.5">
                        📥 Raw Input Payload / Calling Arguments
                      </span>
                      <pre className="p-2.5 bg-black/70 rounded-lg border border-white/10 text-sky-300/90 text-[10.5px] overflow-x-auto overflow-y-auto max-h-72 custom-scrollbar whitespace-pre-wrap leading-relaxed font-mono">
                        {JSON.stringify(activeNodeObj.input, null, 2)}
                      </pre>
                    </div>

                    <div className="flex flex-col gap-1.5 bg-slate-950/90 p-3 rounded-xl border border-white/10 shadow-inner">
                      <span className="text-[10.5px] uppercase tracking-wider font-sans font-bold text-emerald-400 flex items-center gap-1.5">
                        📤 Raw Output Payload / Returned Results
                      </span>
                      <pre className="p-2.5 bg-black/70 rounded-lg border border-white/10 text-emerald-300/90 text-[10.5px] overflow-x-auto overflow-y-auto max-h-72 custom-scrollbar whitespace-pre-wrap leading-relaxed font-mono">
                        {JSON.stringify(activeNodeObj.output, null, 2)}
                      </pre>
                    </div>
                  </div>
                </div>
              </div>
            );
          })()
        )}
      </div>
    </aside>
  );
};
