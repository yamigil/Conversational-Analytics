import React, { useState, useEffect } from "react";
import { Activity, Database, ChevronRight, ChevronDown, RefreshCw, X, Code, CheckCircle2, Maximize2, Minimize2 } from "lucide-react";
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
  const [expandedSpans, setExpandedSpans] = useState<Record<string, boolean>>({
    "span-root-invoke-agent": true,
    "span-call-llm": true
  });

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
  }, [isOpen, conversationName, messagesLength]);

  if (!isOpen) return null;

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
                      <pre className="p-2.5 bg-black/50 rounded-lg border border-white/10 text-slate-300 text-[11px] overflow-x-auto overflow-y-auto max-h-52 custom-scrollbar whitespace-pre-wrap leading-relaxed">
                        {JSON.stringify(span.metadata, null, 2)}
                      </pre>
                    </div>
                  )}
                  {span.request_payload && (
                    <div className="flex flex-col gap-1">
                      <span className="text-[10px] uppercase tracking-wider font-sans font-semibold text-sky-400 flex items-center gap-1">
                        <Code size={11} /> Raw LLM Request / System Instruction
                      </span>
                      <pre className="p-2.5 bg-black/50 rounded-lg border border-white/10 text-sky-300/90 text-[11px] overflow-x-auto overflow-y-auto max-h-52 custom-scrollbar whitespace-pre-wrap leading-relaxed">
                        {JSON.stringify(span.request_payload, null, 2)}
                      </pre>
                    </div>
                  )}
                  {span.response_payload && (
                    <div className="flex flex-col gap-1">
                      <span className="text-[10px] uppercase tracking-wider font-sans font-semibold text-emerald-400 flex items-center gap-1">
                        <CheckCircle2 size={11} /> Raw LLM Response / SQL Output
                      </span>
                      <pre className="p-2.5 bg-black/50 rounded-lg border border-white/10 text-emerald-300/90 text-[11px] overflow-x-auto overflow-y-auto max-h-52 custom-scrollbar whitespace-pre-wrap leading-relaxed">
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
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between text-[11px] text-slate-400 font-medium px-1">
              <span>Session: <span className="font-mono text-slate-300">{traceData.conversation_name.split("/").pop()}</span></span>
              <span className="text-emerald-400 font-mono">{traceData.spans.length} Spans</span>
            </div>
            {renderSpanTree(null)}
          </div>
        )}
      </div>
    </aside>
  );
};
