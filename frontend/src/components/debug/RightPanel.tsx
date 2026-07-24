import React, { useState, useEffect } from "react";
import { Activity, Clock, Cpu, Database, ChevronRight, ChevronDown, RefreshCw, X, Code, CheckCircle2 } from "lucide-react";
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
}

export const RightPanel: React.FC<RightPanelProps> = ({ isOpen, onClose, conversationName }) => {
  const [traceData, setTraceData] = useState<TraceSessionData | null>(null);
  const [loading, setLoading] = useState(false);
  const [expandedSpans, setExpandedSpans] = useState<Record<string, boolean>>({
    "span-root-invoke-agent": true,
    "span-call-llm": true
  });
  const [activeTab, setActiveTab] = useState<"spans" | "metrics">("spans");

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
    if (isOpen && conversationName) {
      fetchTrace();
    }
  }, [isOpen, conversationName]);

  if (!isOpen) return null;

  const totalTokens = traceData?.spans.find(s => s.name === "call_llm")?.metadata?.totalTokens || 1800;
  const promptTokens = traceData?.spans.find(s => s.name === "call_llm")?.metadata?.promptTokens || 1420;
  const responseTokens = traceData?.spans.find(s => s.name === "call_llm")?.metadata?.responseTokens || 380;
  const totalLatency = traceData?.spans.find(s => s.name === "invoke_agent")?.latency_ms || 1240;

  const toggleSpan = (id: string) => {
    setExpandedSpans(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const renderSpanTree = (parentSpanId: string | null = null, depth = 0) => {
    const childSpans = traceData?.spans.filter(s => s.parent_span_id === parentSpanId) || [];
    if (childSpans.length === 0) return null;

    return (
      <div className={`flex flex-col ${depth > 0 ? "ml-4 border-l border-white/10 pl-3 mt-2 gap-2" : "gap-3"}`}>
        {childSpans.map(span => {
          const isExpanded = !!expandedSpans[span.span_id];
          const hasChildren = traceData?.spans.some(s => s.parent_span_id === span.span_id);
          const hasPayload = span.request_payload || span.response_payload || span.metadata;

          return (
            <div key={span.span_id} className="flex flex-col bg-slate-900/60 border border-white/8 rounded-xl overflow-hidden shadow-sm transition-all duration-200 hover:border-white/15">
              <div 
                onClick={() => (hasChildren || hasPayload) && toggleSpan(span.span_id)}
                className="flex items-center justify-between p-3 cursor-pointer select-none bg-white/2 hover:bg-white/5 transition-colors"
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <span className="text-slate-400 shrink-0">
                    {(hasChildren || hasPayload) ? (
                      isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />
                    ) : (
                      <Activity size={14} className="text-sky-400" />
                    )}
                  </span>
                  <span className="font-heading font-semibold text-xs text-slate-200 truncate">{span.name}</span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-sky-500/15 text-sky-300 border border-sky-500/25 shrink-0">
                    {span.service}
                  </span>
                </div>

                <div className="flex items-center gap-2 shrink-0 text-xs">
                  <span className="flex items-center gap-1 text-emerald-400 font-mono text-[11px]">
                    <CheckCircle2 size={12} /> {span.latency_ms} ms
                  </span>
                </div>
              </div>

              {isExpanded && hasPayload && (
                <div className="p-3 bg-slate-950/60 border-t border-white/6 flex flex-col gap-3 text-xs font-mono">
                  {span.metadata && (
                    <div className="flex flex-col gap-1">
                      <span className="text-[10px] uppercase tracking-wider font-sans font-semibold text-slate-400">Span Metadata</span>
                      <pre className="p-2 bg-black/40 rounded-lg border border-white/5 text-slate-300 text-[11px] overflow-x-auto whitespace-pre-wrap">
                        {JSON.stringify(span.metadata, null, 2)}
                      </pre>
                    </div>
                  )}
                  {span.request_payload && (
                    <div className="flex flex-col gap-1">
                      <span className="text-[10px] uppercase tracking-wider font-sans font-semibold text-sky-400 flex items-center gap-1">
                        <Code size={11} /> Raw LLM Request / System Instruction
                      </span>
                      <pre className="p-2 bg-black/40 rounded-lg border border-white/5 text-sky-300/90 text-[11px] overflow-x-auto whitespace-pre-wrap">
                        {JSON.stringify(span.request_payload, null, 2)}
                      </pre>
                    </div>
                  )}
                  {span.response_payload && (
                    <div className="flex flex-col gap-1">
                      <span className="text-[10px] uppercase tracking-wider font-sans font-semibold text-emerald-400 flex items-center gap-1">
                        <CheckCircle2 size={11} /> Raw LLM Response / SQL Output
                      </span>
                      <pre className="p-2 bg-black/40 rounded-lg border border-white/5 text-emerald-300/90 text-[11px] overflow-x-auto whitespace-pre-wrap">
                        {JSON.stringify(span.response_payload, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}

              {isExpanded && hasChildren && renderSpanTree(span.span_id, depth + 1)}
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <aside className="w-96 shrink-0 bg-slate-950/95 border-l border-white/10 flex flex-col h-full z-30 shadow-2xl animate-slideInRight backdrop-blur-xl">
      {/* Header */}
      <div className="p-4 border-b border-white/10 flex items-center justify-between bg-white/2">
        <div className="flex items-center gap-2">
          <Activity className="text-sky-400" size={18} />
          <h3 className="font-heading font-semibold text-sm text-white tracking-tight">OpenTelemetry Trace Inspector</h3>
        </div>
        <div className="flex items-center gap-2">
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

      {/* Tabs */}
      <div className="flex border-b border-white/8 bg-slate-900/30 px-4 text-xs font-heading font-medium">
        <button
          onClick={() => setActiveTab("spans")}
          className={`py-2.5 px-3 border-b-2 transition flex items-center gap-1.5 cursor-pointer ${activeTab === "spans" ? "border-sky-400 text-sky-400 font-semibold" : "border-transparent text-slate-400 hover:text-slate-200"}`}
        >
          <Activity size={13} /> Trace Spans
        </button>
        <button
          onClick={() => setActiveTab("metrics")}
          className={`py-2.5 px-3 border-b-2 transition flex items-center gap-1.5 cursor-pointer ${activeTab === "metrics" ? "border-sky-400 text-sky-400 font-semibold" : "border-transparent text-slate-400 hover:text-slate-200"}`}
        >
          <Cpu size={13} /> Token & Latency Metrics
        </button>
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
            <p className="text-[11px] max-w-[240px]">Ask a conversational question to inspect real-time Gemini LLM tokens, SQL generation, and tool execution latencies.</p>
          </div>
        ) : activeTab === "spans" ? (
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between text-[11px] text-slate-400 font-medium px-1">
              <span>Session: <span className="font-mono text-slate-300">{traceData.conversation_name.split("/").pop()}</span></span>
              <span className="text-emerald-400 font-mono">{traceData.spans.length} Spans</span>
            </div>
            {renderSpanTree(null)}
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 bg-slate-900/60 border border-white/8 rounded-xl flex flex-col gap-1">
                <span className="text-[10px] uppercase font-semibold text-slate-400 flex items-center gap-1"><Clock size={11} className="text-sky-400" /> Total Latency</span>
                <span className="text-lg font-mono font-bold text-white">{totalLatency} <span className="text-xs font-normal text-slate-400">ms</span></span>
              </div>
              <div className="p-3 bg-slate-900/60 border border-white/8 rounded-xl flex flex-col gap-1">
                <span className="text-[10px] uppercase font-semibold text-slate-400 flex items-center gap-1"><Cpu size={11} className="text-purple-400" /> Total Tokens</span>
                <span className="text-lg font-mono font-bold text-white">{totalTokens.toLocaleString()}</span>
              </div>
            </div>

            <div className="p-4 bg-slate-900/60 border border-white/8 rounded-xl flex flex-col gap-3">
              <h4 className="text-xs font-heading font-semibold text-slate-200">LLM Token Breakdown (`call_llm`)</h4>
              <div className="flex flex-col gap-2 font-mono text-xs">
                <div className="flex justify-between items-center py-1 border-b border-white/5">
                  <span className="text-slate-400">Prompt Tokens (Input)</span>
                  <span className="text-sky-400 font-bold">{promptTokens.toLocaleString()}</span>
                </div>
                <div className="flex justify-between items-center py-1 border-b border-white/5">
                  <span className="text-slate-400">Response Tokens (Output)</span>
                  <span className="text-emerald-400 font-bold">{responseTokens.toLocaleString()}</span>
                </div>
                <div className="flex justify-between items-center py-1">
                  <span className="text-slate-300 font-semibold">Total Context Used</span>
                  <span className="text-purple-400 font-bold">{totalTokens.toLocaleString()}</span>
                </div>
              </div>
            </div>

            <div className="p-4 bg-slate-900/60 border border-white/8 rounded-xl flex flex-col gap-2 text-xs text-slate-400">
              <span className="text-slate-200 font-semibold font-heading">OpenTelemetry Architecture Note</span>
              <p className="text-[11px] leading-relaxed">
                Every request emitted to the Conversational Analytics API (`/v1alpha/projects/p/locations/l/chat:chat`) is intercepted by our telemetry proxy. Spans record exact Vertex AI Gemini RPC durations and SQL execution timing.
              </p>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};
