import React, { useState } from "react";
import { X, Database, MessageSquare, Network, Brain } from "lucide-react";

interface ArchitectureModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ArchitectureModal: React.FC<ArchitectureModalProps> = ({
  isOpen,
  onClose
}) => {
  const [selectedComponent, setSelectedComponent] = useState<string>("storage");

  if (!isOpen) return null;

  const FlowConnector = ({ colorClass = "bg-blue-400" }: { colorClass?: string }) => (
    <>
      {/* Desktop Flow Connector (Horizontal) */}
      <div className="hidden md:flex items-center justify-center shrink-0 mx-1 relative w-16 h-6 select-none">
        {/* Background track line */}
        <div className="absolute top-1/2 left-0 right-0 h-[2px] bg-slate-800/80 -translate-y-1/2 rounded-full overflow-hidden">
          {/* Animated flow background gradient */}
          <div className="absolute top-0 bottom-0 left-0 w-full bg-gradient-to-r from-transparent via-slate-500/10 to-transparent animate-flowLine" />
        </div>
        
        {/* Moving Particles */}
        <div 
          className={`absolute top-1/2 w-1 h-1 rounded-full ${colorClass} shadow-[0_0_6px_currentColor] -translate-y-1/2 animate-flowParticle`} 
          style={{ animationDelay: "0s" }}
        />
        <div 
          className={`absolute top-1/2 w-1 h-1 rounded-full ${colorClass} shadow-[0_0_6px_currentColor] -translate-y-1/2 animate-flowParticle`} 
          style={{ animationDelay: "0.6s" }}
        />
        <div 
          className={`absolute top-1/2 w-1 h-1 rounded-full ${colorClass} shadow-[0_0_6px_currentColor] -translate-y-1/2 animate-flowParticle`} 
          style={{ animationDelay: "1.2s" }}
        />
      </div>

      {/* Mobile Flow Connector (Vertical) */}
      <div className="flex md:hidden items-center justify-center shrink-0 my-1 relative w-6 h-10 select-none">
        {/* Background track line */}
        <div className="absolute left-1/2 top-0 bottom-0 w-[2px] bg-slate-800/80 -translate-x-1/2 rounded-full overflow-hidden">
          {/* Animated flow background gradient */}
          <div className="absolute left-0 right-0 top-0 h-full bg-gradient-to-b from-transparent via-slate-500/10 to-transparent animate-flowLineVert" />
        </div>
        
        {/* Moving Particles */}
        <div 
          className={`absolute left-1/2 w-1 h-1 rounded-full ${colorClass} shadow-[0_0_6px_currentColor] -translate-x-1/2 animate-flowParticleVert`} 
          style={{ animationDelay: "0s" }}
        />
        <div 
          className={`absolute left-1/2 w-1 h-1 rounded-full ${colorClass} shadow-[0_0_6px_currentColor] -translate-x-1/2 animate-flowParticleVert`} 
          style={{ animationDelay: "0.6s" }}
        />
        <div 
          className={`absolute left-1/2 w-1 h-1 rounded-full ${colorClass} shadow-[0_0_6px_currentColor] -translate-x-1/2 animate-flowParticleVert`} 
          style={{ animationDelay: "1.2s" }}
        />
      </div>
    </>
  );

  const componentDetails: Record<"chat", Record<string, { title: string; subtitle: string; whatItDoes: string; whyNeeded: string }>> = {
    chat: {
      storage: {
        title: "BigQuery Data Storage",
        subtitle: "Enterprise Data Warehouse",
        whatItDoes: "Stores all structural raw business data, transaction logs, and customer records in structured database tables.",
        whyNeeded: "Serves as the high-speed, secure analytical storage engine that holds the underlying records queried by the reasoning engine."
      },
      catalog: {
        title: "Knowledge Catalog",
        subtitle: "Business Metadata & Context Engine (Formerly Dataplex)",
        whatItDoes: "Powers semantic understanding of the data by storing table/column descriptions, business glossaries, column metadata, and table relationships (ERDs).",
        whyNeeded: "Provides the reasoning engine with crucial business context and structural schemas so it knows what the data represents without needing hardcoded logic."
      },
      reasoning: {
        title: "Conversational Analytics API (Reasoning Engine)",
        subtitle: "Natural Language SQL Generator",
        whatItDoes: "Intercepts natural language questions from the client, queries the Knowledge Catalog for semantic context, generates valid SQL, and executes it securely on BigQuery.",
        whyNeeded: "Enables users to ask complex questions in plain English, transforming high-level business queries into optimized, precise database operations."
      },
      display: {
        title: "Custom UI App",
        subtitle: "React & FastAPI Client Interface",
        whatItDoes: "Provides a responsive web interface for typing natural language queries, reviewing data tables, and visualizing results with Vega charts.",
        whyNeeded: "Gives business users a polished, intuitive, and secure environment to interact with their data without writing any code."
      }
    }
  };

  return (
    <div 
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fadeIn"
    >
      <style>{`
        @keyframes flowLine {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(100%); }
        }
        @keyframes flowParticle {
          0% { left: 0%; opacity: 0; }
          10% { opacity: 1; }
          90% { opacity: 1; }
          100% { left: 100%; opacity: 0; }
        }
        @keyframes flowLineVert {
          0% { transform: translateY(-100%); }
          100% { transform: translateY(100%); }
        }
        @keyframes flowParticleVert {
          0% { top: 0%; opacity: 0; }
          10% { opacity: 1; }
          90% { opacity: 1; }
          100% { top: 100%; opacity: 0; }
        }
        .animate-flowLine {
          animation: flowLine 3s linear infinite;
        }
        .animate-flowParticle {
          animation: flowParticle 1.8s linear infinite;
        }
        .animate-flowLineVert {
          animation: flowLineVert 3s linear infinite;
        }
        .animate-flowParticleVert {
          animation: flowParticleVert 1.8s linear infinite;
        }
      `}</style>
      {/* Modal Card Box */}
      <div 
        onClick={(e) => e.stopPropagation()}
        className="glass-panel w-full max-w-5xl rounded-2xl overflow-hidden shadow-2xl flex flex-col max-h-[85vh] bg-slate-950/95 border-white/10"
      >
        
        {/* Modal Header */}
        <div className="flex justify-between items-center px-8 py-5 border-b border-white/6 bg-white/2">
          <div>
            <h2 className="font-heading font-bold text-lg text-white">System Architecture & Orchestration</h2>
            <p className="text-slate-400 text-xs">Understand the pipeline flow from ingestion to display.</p>
          </div>
          <button 
            onClick={onClose}
            className="text-slate-400 hover:text-white cursor-pointer transition p-1 hover:bg-white/5 rounded-lg"
          >
            <X size={20} />
          </button>
        </div>

        {/* Modal Body / Scroll Content */}
        <div className="flex-1 overflow-y-auto p-8">
          
          {/* Conversational Flow Diagram */}
          <div className="flex flex-col gap-8 animate-fadeIn">
            <div>
              <p className="text-slate-400 text-xs leading-relaxed max-w-3xl">
                This diagram demonstrates how data, semantic metadata, reasoning engines, and custom user interfaces unify to power the conversational analytics workspace.
              </p>
              <div className="flex flex-wrap gap-2 mt-3">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20 select-none">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                  Interactive Diagram: Click any component node below to explore details
                </span>
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-medium bg-purple-500/10 text-purple-400 border border-purple-500/20 select-none">
                  📊 Detailed breakdowns are displayed below
                </span>
              </div>
            </div>
            
            {/* Flow Nodes Grid */}
            <div className="flex flex-col md:flex-row justify-between gap-2 items-center bg-slate-900/20 border border-white/5 p-6 rounded-2xl">
              
              {/* Node 1: Storage */}
              <div 
                onClick={() => setSelectedComponent("storage")}
                className={`glass-panel p-4 rounded-xl flex flex-col items-center text-center w-40 shrink-0 cursor-pointer select-none transition duration-300 ${selectedComponent === "storage" ? "border-blue-500 bg-blue-500/10 shadow-[0_0_12px_rgba(59,130,246,0.3)]" : "border-white/6 hover:border-blue-500/30"}`}
              >
                <Database size={24} className="text-blue-400 mb-2" />
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">01. Storage</span>
                <span className="text-xs font-semibold text-white mt-1">BigQuery</span>
                <span className="text-[9px] text-slate-400 mt-1">Data Warehouse</span>
              </div>
              
              <FlowConnector colorClass="bg-blue-400" />

              {/* Node 2: Catalog */}
              <div 
                onClick={() => setSelectedComponent("catalog")}
                className={`glass-panel p-4 rounded-xl flex flex-col items-center text-center w-40 shrink-0 cursor-pointer select-none transition duration-300 ${selectedComponent === "catalog" ? "border-amber-500 bg-amber-500/10 shadow-[0_0_12px_rgba(245,158,11,0.3)]" : "border-white/6 hover:border-amber-500/30"}`}
              >
                <Network size={24} className="text-amber-400 mb-2" />
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">02. Metadata</span>
                <span className="text-xs font-semibold text-white mt-1">Knowledge Catalog</span>
                <span className="text-[9px] text-slate-400 mt-1">Formerly Dataplex</span>
              </div>

              <FlowConnector colorClass="bg-amber-400" />

              {/* Node 3: Reasoning Engine */}
              <div 
                onClick={() => setSelectedComponent("reasoning")}
                className={`glass-panel p-4 rounded-xl flex flex-col items-center text-center w-40 shrink-0 cursor-pointer select-none transition duration-300 ${selectedComponent === "reasoning" ? "border-purple-500 bg-purple-500/10 shadow-[0_0_12px_rgba(139,92,246,0.3)]" : "border-white/6 hover:border-purple-500/30"}`}
              >
                <Brain size={24} className="text-purple-400 mb-2" />
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">03. Engine</span>
                <span className="text-xs font-semibold text-white mt-1">Reasoning Engine</span>
                <span className="text-[9px] text-slate-400 mt-1">Conversational API</span>
              </div>

              <FlowConnector colorClass="bg-purple-400" />

              {/* Node 4: Custom UI */}
              <div 
                onClick={() => setSelectedComponent("display")}
                className={`glass-panel p-4 rounded-xl flex flex-col items-center text-center w-40 shrink-0 cursor-pointer select-none transition duration-300 ${selectedComponent === "display" ? "border-brand-primary bg-brand-primary/10 shadow-[0_0_12px_hsl(var(--primary-color)/0.3)]" : "border-brand-primary/45 hover:border-brand-primary"}`}
              >
                <MessageSquare size={24} className="text-brand-primary mb-2" />
                <span className="text-[10px] font-bold uppercase tracking-wider text-brand-primary">04. Interface</span>
                <span className="text-xs font-semibold text-white mt-1">Custom UI</span>
                <span className="text-[9px] text-slate-400 mt-1">React / FastAPI App</span>
              </div>

            </div>
          </div>

          {/* Architecture Detail Panel */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-6">
            
            {/* Left Card: General Flow Concept */}
            <div className="glass-panel p-6 rounded-xl border-white/6 flex flex-col justify-center bg-white/1">
              <h4 className="font-heading font-semibold text-xs text-white mb-2 uppercase tracking-wider text-brand-primary">Pipeline Core Concept</h4>
              <p className="text-slate-400 text-xs leading-relaxed">
                This architecture leverages semantic metadata from the Knowledge Catalog to translate natural language queries into secure BigQuery SQL, presenting answers in a customized, responsive web workspace.
              </p>
            </div>

            {/* Right Card: Dynamic Component Detail */}
            <div className="glass-panel p-6 rounded-xl border-brand-primary/30 bg-brand-primary/2 flex flex-col relative overflow-hidden transition-all duration-300 min-h-[170px]">
              <div className="absolute top-0 right-0 w-24 h-24 bg-brand-primary/5 rounded-full blur-2xl -mr-5 -mt-5" />
              
              <span className="text-[9px] font-bold uppercase tracking-wider text-brand-primary mb-1">
                Component Breakdown
              </span>
              
              <h4 className="font-heading font-semibold text-sm text-white mb-0.5">
                {componentDetails.chat[selectedComponent]?.title || "Select Component"}
              </h4>
              <span className="text-[10px] text-slate-400 italic mb-3 block">
                {componentDetails.chat[selectedComponent]?.subtitle || ""}
              </span>
              
              <div className="flex flex-col gap-2.5">
                <div>
                  <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest block mb-0.5">What it does</span>
                  <p className="text-slate-300 text-xs leading-relaxed">
                    {componentDetails.chat[selectedComponent]?.whatItDoes || "Click a node icon to inspect its role."}
                  </p>
                </div>
                <div>
                  <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest block mb-0.5">Why it was needed</span>
                  <p className="text-slate-300 text-xs leading-relaxed">
                    {componentDetails.chat[selectedComponent]?.whyNeeded || "Details will be dynamically loaded."}
                  </p>
                </div>
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
};
