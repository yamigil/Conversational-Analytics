import React from "react";
import { MessageSquare, History, ChevronRight } from "lucide-react";

interface BrandConfig {
  name: string;
  welcomeMessage: string;
  logoText: string;
}

interface Conversation {
  name: string;
  createTime?: string;
  lastUsedTime?: string;
}

interface DashboardProps {
  activeBrand: BrandConfig | undefined;
  renderLogoSvg: () => React.ReactNode;
  onNavigate: (page: "chat" | "settings" | "home") => void;
  conversations: Conversation[];
  onSelectConversation: (convoName: string) => void;
  tourStep?: number;
}

export const Dashboard: React.FC<DashboardProps> = ({
  activeBrand,
  renderLogoSvg,
  onNavigate,
  conversations,
  onSelectConversation,
  tourStep
}) => {
  // Format date and time for the conversation title
  const formatConvoTitle = (convo: Conversation) => {
    const date = new Date(convo.createTime || convo.lastUsedTime || "");
    return date.toLocaleString([], { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  };

  // Get the top 4 most recent conversations to display in the grid
  const recentChats = conversations.slice(0, 4);

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

      {/* Recent Chat History Panel (Replaces Executive Insights) */}
      <div 
        id="dashboard-recent-chats"
        className={`w-full max-w-5xl glass-panel p-4 sm:p-8 rounded-2xl mb-8 animate-slideIn flex flex-col gap-5 ${tourStep === 7 ? 'tour-highlight' : ''}`} 
        style={{ animationDelay: "0.1s" }}
      >
        <div className="flex flex-col sm:flex-row justify-between items-start gap-4">
          <div>
            <div id="dashboard-insights-title" className="flex items-center gap-2 text-xs font-semibold text-brand-primary uppercase tracking-wider mb-2">
              <History size={14} className="text-brand-primary" />
              Recent Chat History
            </div>
            <h3 className="font-heading font-semibold text-lg text-white mb-1">Recent Conversations</h3>
            <p className="text-slate-400 text-xs leading-relaxed">
              Resume your past data analysis sessions or start a new chat with your AI agents.
            </p>
          </div>
          
          {/* Ask a New Question button - always visible if conversations exist */}
          {conversations.length > 0 && (
            <button
              id="dashboard-launch-chat-btn"
              onClick={() => onNavigate("chat")}
              className={`py-2.5 px-4 text-xs font-semibold bg-brand-primary hover:opacity-90 rounded-xl text-white transition cursor-pointer select-none border-none flex items-center gap-1.5 shrink-0 shadow-lg ${tourStep === 8 ? 'tour-highlight' : ''}`}
            >
              <MessageSquare size={13} />
              Ask a New Question
            </button>
          )}
        </div>

        {conversations.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full">
            {recentChats.map((convo, index) => (
              <div 
                key={convo.name} 
                onClick={() => onSelectConversation(convo.name)}
                className="p-4 bg-white/2 border border-white/5 hover:border-brand-primary/30 hover:bg-brand-primary/5 rounded-xl flex justify-between items-center transition duration-300 cursor-pointer group hover:scale-[1.01] hover:shadow-lg"
              >
                <div className="flex gap-3 items-center min-w-0">
                  <span className="flex-shrink-0 w-8 h-8 rounded-xl bg-white/5 border border-white/6 text-slate-300 flex items-center justify-center text-xs font-bold transition duration-300 group-hover:bg-brand-primary/15 group-hover:border-brand-primary/30 group-hover:text-brand-primary select-none">
                    {index + 1}
                  </span>
                  <div className="flex flex-col min-w-0">
                    <span className="text-sm font-semibold text-white truncate">
                      Conversation {formatConvoTitle(convo)}
                    </span>
                    <span className="text-[10px] text-slate-500 font-medium group-hover:text-slate-400 transition-colors">
                      Click to resume this session
                    </span>
                  </div>
                </div>
                <ChevronRight size={14} className="text-slate-500 group-hover:text-brand-primary group-hover:translate-x-1 transition duration-300 shrink-0" />
              </div>
            ))}
          </div>
        ) : (
          <div className="text-xs text-slate-400 italic py-8 bg-white/1 border border-white/5 rounded-xl text-center w-full flex flex-col items-center gap-4">
            <span>No recent conversations found. Start a new session to begin your data analysis.</span>
            <button
              id="dashboard-launch-chat-btn"
              onClick={() => onNavigate("chat")}
              className={`py-2.5 px-5 text-xs font-semibold bg-brand-primary hover:opacity-90 rounded-xl text-white transition cursor-pointer select-none border-none flex items-center gap-2 ${tourStep === 8 ? 'tour-highlight' : ''}`}
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
