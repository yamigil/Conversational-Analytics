import React from "react";
import { MessageSquare, TrendingUp } from "lucide-react";

interface BrandConfig {
  name: string;
  welcomeMessage: string;
  logoText: string;
}

interface DashboardProps {
  activeBrand: BrandConfig | undefined;
  renderLogoSvg: () => React.ReactNode;
  onNavigate: (page: "chat" | "settings" | "home") => void;
  insightsData: { summary: string; insights: string[] } | null;
  isLoadingInsights: boolean;
  tourStep?: number;
}

export const Dashboard: React.FC<DashboardProps> = ({
  activeBrand,
  renderLogoSvg,
  onNavigate,
  insightsData,
  isLoadingInsights,
  tourStep
}) => {
  return (
    <div className="flex-1 overflow-y-auto px-4 sm:px-10 py-6 sm:py-12 flex flex-col items-center relative">

      {/* Hero Header Section */}
      <div className="text-center max-w-2xl mt-4 mb-10 animate-slideIn">
        <div className="flex justify-center mb-6">
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center shadow-lg select-none scale-110">
            {renderLogoSvg()}
          </div>
        </div>
        
        <h1 className="font-heading text-3xl sm:text-4xl font-bold tracking-tight mb-4 text-white">
          {activeBrand?.name || "Retail"} AI Experience Hub
        </h1>
        
        <p className="text-slate-300/80 text-sm sm:text-md leading-relaxed font-medium">
          Welcome to your conversational analytics workspace. Ask questions, build charts, and generate predictive insights on {activeBrand?.name || "your company"}'s performance in real time.
        </p>
      </div>

      {/* Executive Insights & Highlights Panel */}
      <div 
        id="dashboard-executive-insights"
        className={`w-full max-w-5xl glass-panel p-4 sm:p-8 rounded-2xl mb-8 animate-slideIn flex flex-col gap-5 ${tourStep === 6 ? 'tour-highlight' : ''}`} 
        style={{ animationDelay: "0.1s" }}
      >
        <div className="flex flex-col sm:flex-row justify-between items-start gap-4">
          <div>
            <div id="dashboard-insights-title" className="flex items-center gap-2 text-xs font-semibold text-brand-primary uppercase tracking-wider mb-2">
              <TrendingUp size={14} className="text-brand-primary" />
              Executive Insights & Highlights
            </div>
            <h3 className="font-heading font-semibold text-lg text-white mb-1">Recent Analytics Activity</h3>
            <p className="text-slate-400 text-xs leading-relaxed">
              {isLoadingInsights ? "Summarizing recent conversations..." : insightsData?.summary || "No recent activity summaries."}
            </p>
          </div>
          
          {!isLoadingInsights && insightsData && insightsData.insights.length > 0 && (
            <button
              id="dashboard-launch-chat-btn"
              onClick={() => onNavigate("chat")}
              className={`py-2.5 px-4 text-xs font-semibold bg-brand-primary hover:opacity-90 rounded-xl text-white transition cursor-pointer select-none border-none flex items-center gap-1.5 shrink-0 shadow-lg ${tourStep === 7 ? 'tour-highlight' : ''}`}
            >
              <MessageSquare size={13} />
              Ask a Question
            </button>
          )}
        </div>

        {isLoadingInsights ? (
          <div className="flex items-center gap-2 py-4">
            <span className="w-2.5 h-2.5 bg-brand-primary rounded-full animate-bounce" />
            <span className="w-2.5 h-2.5 bg-brand-primary rounded-full animate-bounce [animation-delay:0.2s]" />
            <span className="w-2.5 h-2.5 bg-brand-primary rounded-full animate-bounce [animation-delay:0.4s]" />
          </div>
        ) : insightsData && insightsData.insights.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full">
            {insightsData.insights.map((insight, index) => (
              <div key={index} className="p-4 bg-white/2 border border-white/5 hover:border-white/10 rounded-xl flex gap-3 items-start transition duration-200">
                <span className="flex-shrink-0 w-5 h-5 rounded-full bg-brand-primary/10 border border-brand-primary/20 text-brand-primary flex items-center justify-center text-[10px] font-bold mt-0.5 select-none">
                  0{index + 1}
                </span>
                <span className="text-xs text-slate-300 leading-relaxed">
                  {insight}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-xs text-slate-400 italic py-8 bg-white/1 border border-white/5 rounded-xl text-center w-full flex flex-col items-center gap-4">
            <span>Start a conversational analytics session to auto-compile insights here.</span>
            <button
              id="dashboard-launch-chat-btn"
              onClick={() => onNavigate("chat")}
              className={`py-2.5 px-5 text-xs font-semibold bg-brand-primary hover:opacity-90 rounded-xl text-white transition cursor-pointer select-none border-none flex items-center gap-2 ${tourStep === 7 ? 'tour-highlight' : ''}`}
            >
              <MessageSquare size={14} />
              Launch Conversational Analytics
            </button>
          </div>
        )}
      </div>

    </div>
  );
};
