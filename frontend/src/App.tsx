import React, { useState, useEffect, useRef } from "react";
import { marked } from "marked";
import vegaEmbed from "vega-embed";
import { 
  Send, 
  Plus, 
  ChevronDown, 
  ChevronRight,
  Copy, 
  Check, 
  ArrowLeft,
  Trash2,
  Network,
  Sparkles,
  Loader2,
  AlertTriangle,
  Settings,
  LogOut,
  Menu,
  X,
  Upload
} from "lucide-react";

import { Dashboard } from "./components/Dashboard";
import { ArchitectureModal } from "./components/ArchitectureModal";
import { GraphVisualizer } from "./components/GraphVisualizer";
import { auth, signInWithGoogle, requestGCPToken } from "./firebase";

// Interfaces
interface BrandConfig {
  name: string;
  primaryColor: string;
  secondaryColor: string;
  backgroundColorStart: string;
  backgroundColorEnd: string;
  welcomeMessage: string;
  logoUrl: string;
  logoText: string;
  logoSvg?: string;
  gcpProjectId?: string;
  gcpLocation?: string;
}

interface BrandingData {
  activeBrand: string;
  brands: Record<string, BrandConfig>;
}

interface Agent {
  name: string;
  displayName?: string;
  description?: string;
  createTime?: string;
  welcomeSubtitle?: string;
  suggestions?: string[];
  isGraphAgent?: boolean;
  graphData?: any;
}

interface Conversation {
  name: string;
  createTime?: string;
  lastUsedTime?: string;
}


interface ChatMessage {
  userMessage?: { text: string };
  systemMessage?: any; // Contains text, schema, data, chart
  isStreaming?: boolean;
}

// React Component to Render Vega Charts
// Markdown bullet normalizer
const formatMarkdown = (text: string): string => {
  if (!text) return "";
  return text.split("\n").map(line => {
    // Normalize bullets like: •, -, *, + followed by space(s)
    const match = line.match(/^(\s*)([•\-\*\+])\s+(.*)$/);
    if (match) {
      const indent = match[1];
      const content = match[3];
      return `${indent}* ${content}`;
    }
    return line;
  }).join("\n");
};

// Follow-up suggestions resolver based on agent context and branding
const getAgentSuggestions = (displayName: string, agentId: string, brandKey: string): string[] => {
  const nameLower = (displayName || "").toLowerCase();
  const idLower = (agentId || "").toLowerCase();
  const brandNormalized = brandKey.toLowerCase().replace(/[^a-z0-9]/g, "");

  // 1. If it is a Marketing or GA4 agent
  if (nameLower.includes("marketing") || idLower.includes("marketing") || nameLower.includes("ga4") || idLower.includes("ga4")) {
    return [
      "What are the top 10 best-selling product categories by total sales revenue?",
      "How does our monthly order volume compare across different countries?",
      "Can we see the distribution of users by traffic source and country?"
    ];
  }

  // 2. If it is a Home Depot custom brand agent
  if (brandNormalized === "homedepot") {
    return [
      "What is the average ROAS for each month in the available data?",
      "Predict the revenue for the next 3 months based on this historical trend.",
      "Compare the performance of Google AdWords vs Bing Ads for the peak month of July 2023."
    ];
  }

  // 3. If it is a Target custom brand agent
  if (brandNormalized === "target") {
    return [
      "What is the total revenue for each product category this year?",
      "How many unique visitors did we have each day last week?",
      "Predict the daily revenue for the next 30 days based on the last year of data."
    ];
  }

  // 4. Default Retail / Ecommerce (The Look) suggestions
  return [
    "Show me the monthly trend of cost and revenue for this year.",
    "What are the top 5 brands by number of items sold?",
    "What is the average order value (AOV) for each month?"
  ];
};

// Helper to identify status texts
const isStatus = (str: string) => {
  const s = str.trim();
  return s === "Analyzing context" || 
         s.startsWith("Retrieved context for") || 
         s.startsWith("Running query") ||
         s.startsWith("Executing query") ||
         s.startsWith("Generating visualization");
};

// Parses a single, un-merged system message text parts list using boundary invariant
const parseSingleSystemMessageText = (parts: string[]): SystemMessagePart => {
  const statuses: string[] = [];
  const thoughts: { title: string; body: string }[] = [];
  let answer = "";
  let insights = "";
  const suggestions: string[] = [];

  if (!parts || parts.length === 0) {
    return { statuses, thoughts, answer, insights, suggestions };
  }

  if (parts.length === 2) {
    if (isStatus(parts[0])) {
      statuses.push(parts[0].trim());
      statuses.push(parts[1].trim());
    } else {
      thoughts.push({
        title: parts[0].trim(),
        body: parts[1].trim()
      });
    }
  } else if (parts.length === 1) {
    const trimmed = parts[0].trim();
    if (trimmed.startsWith("### Insights") || trimmed.startsWith("Insights") || trimmed.toLowerCase().startsWith("**insights**")) {
      insights = parts[0];
    } else {
      answer = parts[0];
    }
  } else if (parts.length >= 3) {
    suggestions.push(...parts.map(p => p.trim()));
  }

  return { statuses, thoughts, answer, insights, suggestions };
};

// Interface for parsed system message parts
interface SystemMessagePart {
  statuses: string[];
  thoughts: { title: string; body: string }[];
  answer: string;
  insights: string;
  suggestions: string[];
}



// Groups consecutive system messages between user queries into a single system message
const groupConversationalMessages = (rawMessages: ChatMessage[]): ChatMessage[] => {
  const grouped: ChatMessage[] = [];
  let currentSystemMsg: any = null;

  for (const msg of rawMessages) {
    if (msg.userMessage) {
      if (currentSystemMsg) {
        grouped.push({ systemMessage: currentSystemMsg });
        currentSystemMsg = null;
      }
      grouped.push(msg);
    } else if (msg.systemMessage) {
      if (!currentSystemMsg) {
        currentSystemMsg = {
          statuses: [],
          thoughts: [],
          answer: "",
          insights: "",
          suggestions: [],
          schema: null,
          data: null,
          chart: null
        };
      }
      
      const sys = msg.systemMessage;
      if (sys.text && sys.text.parts) {
        const parsed = parseSingleSystemMessageText(sys.text.parts);
        currentSystemMsg.statuses.push(...parsed.statuses);
        currentSystemMsg.thoughts.push(...parsed.thoughts);
        
        if (parsed.answer) {
          currentSystemMsg.answer = currentSystemMsg.answer 
            ? currentSystemMsg.answer + "\n\n" + parsed.answer 
            : parsed.answer;
        }
        if (parsed.insights) {
          currentSystemMsg.insights = currentSystemMsg.insights 
            ? currentSystemMsg.insights + "\n\n" + parsed.insights 
            : parsed.insights;
        }
        currentSystemMsg.suggestions.push(...parsed.suggestions);
      }
      
      if (sys.error && sys.error.message) {
        const errMsg = sys.error.message;
        currentSystemMsg.answer = currentSystemMsg.answer 
          ? currentSystemMsg.answer + "\n\n" + errMsg 
          : errMsg;
      }
      
      if (sys.schema) {
        currentSystemMsg.schema = { ...(currentSystemMsg.schema || {}), ...sys.schema };
      }
      if (sys.data) {
        currentSystemMsg.data = { ...(currentSystemMsg.data || {}), ...sys.data };
      }
      if (sys.chart) {
        currentSystemMsg.chart = { ...(currentSystemMsg.chart || {}), ...sys.chart };
      }
    }
  }

  if (currentSystemMsg) {
    grouped.push({ systemMessage: currentSystemMsg });
  }

  return grouped;
};


// Collapsible thinking component
const MessageThinkingBlock: React.FC<{ 
  statuses: string[]; 
  thoughts: { title: string; body: string }[]; 
  isStreaming?: boolean;
  tourStep?: number;
  setTourStep?: (step: number) => void;
}> = ({ statuses, thoughts, isStreaming, tourStep, setTourStep }) => {
  const [isOpen, setIsOpen] = useState(false);

  // Inject mock thoughts/statuses during Step 18 & 19 of the walkthrough to guarantee the collapsible panel is visible and interactive!
  const isTourThinkingStep = tourStep === 18 || tourStep === 19;
  const displayStatuses = (statuses.length === 0 && isTourThinkingStep)
    ? ["Analyzing user greeting", "Checking database schemas", "Preparing capabilities response"]
    : statuses;
  const displayThoughts = (thoughts.length === 0 && isTourThinkingStep)
    ? [
        {
          title: "Bypassing SQL compilation",
          body: "The user submitted a conversational capabilities query. Bypassing SQL query compilation to optimize response latency."
        },
        {
          title: "Formulating response",
          body: "Rendering capabilities overview narrative for the active retail brand dataset."
        }
      ]
    : thoughts;

  // If statuses and thoughts are empty and we are not streaming, do not render
  if (displayStatuses.length === 0 && displayThoughts.length === 0 && !isStreaming) return null;

  // If not streaming and thoughts are empty, render inline statuses directly
  if (!isStreaming && displayThoughts.length === 0) {
    return (
      <div className="mb-4 flex flex-col gap-2 p-3 bg-slate-950/20 border border-white/4 rounded-xl backdrop-blur-sm">
        {displayStatuses.map((status, idx) => (
          <div key={idx} className="flex items-center gap-2 font-medium text-slate-400 text-xs">
            <span className="flex items-center justify-center w-4 h-4 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              ✓
            </span>
            <span>{status}</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="mb-4 flex flex-col gap-2">
      {/* Header Pill */}
      <div className="inline-flex items-center gap-3 px-3 py-1.5 bg-slate-950/40 border border-white/6 rounded-xl w-fit backdrop-blur-sm select-none">
        <div className="flex items-center gap-1.5 text-xs">
          {/* Sparkle Icon */}
          <svg viewBox="0 0 24 24" className="w-3.5 h-3.5 text-sky-400 fill-current animate-pulse">
            <path d="M12,3 C12,7.97 16.03,12 21,12 C16.03,12 12,16.03 12,21 C12,16.03 7.97,12 3,12 C7.97,12 12,7.97 12,3 Z" />
          </svg>
          <span className="font-semibold text-slate-300">
            {isStreaming ? "Thinking..." : "Thought process"}
          </span>
        </div>
        
        {(displayStatuses.length > 0 || displayThoughts.length > 0) && (
          <button
            id="show-thinking-btn"
            onClick={() => {
              setIsOpen(!isOpen);
              if (tourStep === 19 && setTourStep) {
                setTourStep(20);
              }
            }}
            className={`text-[11px] font-semibold text-sky-400 hover:text-sky-300 transition cursor-pointer flex items-center gap-1 select-none border-none bg-transparent p-0 ${tourStep === 19 ? 'tour-highlight px-1.5 py-0.5 rounded bg-sky-400/10' : ''}`}
          >
            {isOpen ? "Hide thinking" : "Show thinking"}
            <ChevronDown size={11} className={`transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`} />
          </button>
        )}
      </div>

      {/* Expanded Content Box */}
      {isOpen && (displayStatuses.length > 0 || displayThoughts.length > 0) && (
        <div className="p-4 bg-slate-950/30 border border-white/6 rounded-xl flex flex-col gap-4 max-h-[300px] overflow-y-auto text-xs text-slate-300 w-full backdrop-blur-sm">
          {/* Status steps */}
          {displayStatuses.length > 0 && (
            <div className="flex flex-col gap-2">
              {displayStatuses.map((status, idx) => (
                <div key={idx} className="flex items-center gap-2 font-medium text-slate-400">
                  <span className="flex items-center justify-center w-4 h-4 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                    ✓
                  </span>
                  <span>{status}</span>
                </div>
              ))}
            </div>
          )}

          {/* Thought process body */}
          {displayThoughts.length > 0 && (
            <div className="flex flex-col gap-4 border-t border-white/6 pt-3 mt-1">
              {displayThoughts.map((t, idx) => (
                <div key={idx} className="flex flex-col gap-1.5">
                  <h4 className="font-heading font-semibold text-slate-200">{t.title}</h4>
                  <p className="leading-relaxed whitespace-pre-wrap text-slate-400">{formatMarkdown(t.body)}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// SQL widget
const SqlWidget: React.FC<{ data: any }> = ({ data }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    if (!data.generatedSql) return;
    navigator.clipboard.writeText(data.generatedSql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="mt-4 border border-white/6 rounded-lg overflow-hidden bg-slate-950">
      <div className="bg-white/2 px-4 py-2 border-b border-white/6 flex justify-between items-center text-xs text-slate-400">
        <span className="font-heading font-medium">Generated SQL Query</span>
        <button 
          onClick={handleCopy}
          className="flex items-center gap-1.5 hover:text-white transition cursor-pointer"
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
          {copied ? "Copied!" : "Copy SQL"}
        </button>
      </div>
      <pre className="p-4 font-mono text-xs text-sky-400 overflow-x-auto whitespace-pre-wrap">
        <code>{data.generatedSql}</code>
      </pre>
    </div>
  );
};

// Data Table widget
const DataTableOnlyWidget: React.FC<{ data: any }> = ({ data }) => {
  if (!data.result?.data || !data.result?.schema) return null;
  return (
    <div className="mt-4 border border-white/6 rounded-xl overflow-hidden bg-slate-900/30">
      <div className="overflow-x-auto max-h-64">
        <table className="w-full border-collapse text-xs text-left">
          <thead>
            <tr className="bg-white/3 border-b border-white/6 text-slate-400 font-medium">
              {data.result.schema.fields?.map((f: any, idx: number) => (
                <th key={idx} className="px-4 py-2.5 whitespace-nowrap">{f.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.result.data.map((row: any, rIdx: number) => (
              <tr key={rIdx} className="hover:bg-white/2 border-b border-white/3 text-slate-300">
                {data.result.schema.fields?.map((f: any, fIdx: number) => (
                  <td key={fIdx} className="px-4 py-2.5 whitespace-nowrap">
                    {row[f.name] !== undefined ? String(row[f.name]) : "-"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// Unified Visualizer widget (Chart + Table tabs)
interface VisualizerWidgetProps {
  chart: any;
  data: any;
  primaryColorHsl: string;
}

const VisualizerWidget: React.FC<VisualizerWidgetProps> = ({ chart, data, primaryColorHsl }) => {
  const [activeTab, setActiveTab] = useState<"chart" | "table">("chart");
  const chartRef = useRef<HTMLDivElement>(null);

  const getTableData = () => {
    if (data?.result?.data && data?.result?.schema?.fields) {
      return {
        headers: data.result.schema.fields.map((f: any) => f.name),
        rows: data.result.data
      };
    }

    const vegaConfig = chart?.result?.vegaConfig;
    if (vegaConfig) {
      let values = vegaConfig.data?.values;
      if (!values && vegaConfig.data?.name && vegaConfig.datasets) {
        values = vegaConfig.datasets[vegaConfig.data.name];
      }
      if (Array.isArray(values) && values.length > 0) {
        return {
          headers: Object.keys(values[0]),
          rows: values
        };
      }
    }
    return null;
  };

  const tableData = getTableData();
  const hasChart = !!chart?.result?.vegaConfig;
  const hasData = !!tableData;

  useEffect(() => {
    if (!hasChart && hasData) {
      setActiveTab("table");
    } else if (hasChart) {
      setActiveTab("chart");
    }
  }, [hasChart, hasData]);

  useEffect(() => {
    if (activeTab !== "chart" || !chartRef.current || !chart?.result?.vegaConfig) return;

    const element = chartRef.current;
    
    const getHexColorFromHsl = (hslString: string) => {
      if (!hslString) return "#4285F4";
      const parts = hslString.split(" ");
      if (parts.length < 3) return "#4285F4";
      
      const h = parseInt(parts[0]);
      const s = parseInt(parts[1].replace("%", "")) / 100;
      const l = parseInt(parts[2].replace("%", "")) / 100;

      const a = s * Math.min(l, 1 - l);
      const f = (n: number) => {
        const k = (n + h / 30) % 12;
        const color = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
        return Math.round(255 * color).toString(16).padStart(2, "0");
      };
      return `#${f(0)}${f(8)}${f(4)}`;
    };

    const runEmbed = async () => {
      try {
        const vegaSpec = JSON.parse(JSON.stringify(chart.result.vegaConfig));
        const hexColor = getHexColorFromHsl(primaryColorHsl);
        
        if (vegaSpec.config && vegaSpec.config.range) {
          vegaSpec.config.range.category = [hexColor, "#10b981", "#f59e0b", "#ef4444", "#8b5cf6"];
        }

        await vegaEmbed(element, vegaSpec, {
          actions: false,
          theme: "dark"
        });
      } catch (err) {
        console.error("Vega rendering error:", err);
      }
    };

    runEmbed();
  }, [activeTab, chart, primaryColorHsl]);

  if (!hasChart && !hasData) return null;

  return (
    <div className="w-full flex flex-col mt-4 bg-slate-900/40 border border-white/6 rounded-2xl overflow-hidden shadow-lg">
      <div className="px-5 py-3 bg-white/2 border-b border-white/6 flex justify-between items-center">
        <span className="text-xs font-semibold text-slate-400">
          {hasChart ? (chart.result?.vegaConfig?.title || "Data Insights") : "Data Grid"}
        </span>
        {hasChart && hasData && (
          <div className="flex gap-1.5 p-0.5 bg-slate-950/60 rounded-lg border border-white/6">
            <button
              onClick={() => setActiveTab("chart")}
              className={`px-3 py-1 text-xs font-medium rounded-md transition select-none cursor-pointer ${
                activeTab === "chart"
                  ? "bg-brand-primary text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Chart
            </button>
            <button
              onClick={() => setActiveTab("table")}
              className={`px-3 py-1 text-xs font-medium rounded-md transition select-none cursor-pointer ${
                activeTab === "table"
                  ? "bg-brand-primary text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Table
            </button>
          </div>
        )}
      </div>

      <div className="p-5">
        {activeTab === "chart" && hasChart && (
          <div ref={chartRef} className="w-full overflow-x-auto bg-transparent"></div>
        )}

        {activeTab === "table" && tableData && (
          <div className="overflow-x-auto max-h-64 rounded-xl border border-white/6 bg-slate-950/30">
            <table className="w-full border-collapse text-xs text-left">
              <thead>
                <tr className="bg-white/3 border-b border-white/6 text-slate-400 font-semibold">
                  {tableData.headers.map((h: string, idx: number) => (
                    <th key={idx} className="px-4 py-2.5 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tableData.rows.map((row: any, rIdx: number) => (
                  <tr key={rIdx} className="hover:bg-white/2 border-b border-white/3 text-slate-300">
                    {tableData.headers.map((h: string, fIdx: number) => (
                      <td key={fIdx} className="px-4 py-2.5 whitespace-nowrap">
                        {row[h] !== undefined ? String(row[h]) : "-"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

// Authenticated fetch wrapper that automatically injects the Firebase ID Token
const authenticatedFetch = async (url: string, options: RequestInit = {}): Promise<Response> => {
  if (import.meta.env.VITE_MOCK_AUTH === "true") {
    options.headers = {
      ...options.headers,
      "Authorization": `Bearer mock-token-123`,
    };
    
    // Inject mock selected GCP project if present
    const selectedProject = localStorage.getItem("gcp_selected_project");
    if (selectedProject) {
      options.headers = {
        "X-GCP-Project-Id": selectedProject,
        ...options.headers,
      };
    }

    // Inject mock selected GCP location if present
    const selectedLocation = localStorage.getItem("gcp_selected_location");
    if (selectedLocation) {
      options.headers = {
        "X-GCP-Location": selectedLocation,
        ...options.headers,
      };
    }
  } else {
    const currentUser = auth.currentUser;
    if (currentUser) {
      try {
        const token = await currentUser.getIdToken();
        options.headers = {
          ...options.headers,
          "Authorization": `Bearer ${token}`,
        };

        // Inject the GCP user access token if user SSO credentials mode is active
        const ssoMode = localStorage.getItem("gcp_credentials_mode") === "user_sso";
        const gcpToken = sessionStorage.getItem("gcp_user_access_token");
        if (ssoMode && gcpToken) {
          options.headers = {
            "X-GCP-User-Token": gcpToken,
            ...options.headers,
          };
        }

        // Inject the dynamically selected GCP Project ID and Location only if user SSO credentials mode is active
        if (ssoMode) {
          const selectedProject = localStorage.getItem("gcp_selected_project");
          if (selectedProject) {
            options.headers = {
              "X-GCP-Project-Id": selectedProject,
              ...options.headers,
            };
          }

          const selectedLocation = localStorage.getItem("gcp_selected_location");
          if (selectedLocation) {
            options.headers = {
              "X-GCP-Location": selectedLocation,
              ...options.headers,
            };
          }
        }
      } catch (error) {
        console.error("Failed to fetch Firebase ID Token for request:", error);
      }
    }
  }
  
  const response = await fetch(url, options);
  
  // Intercept Google Cloud 401 Unauthenticated errors (expired or missing Google OAuth token)
  if (response.status === 401 && localStorage.getItem("gcp_credentials_mode") === "user_sso") {
    console.warn("Detected expired or missing Google Cloud credentials (401). Triggering automatic re-authentication...");
    try {
      // Trigger Google Consent screen popup to get a fresh GCP access token!
      await requestGCPToken();
      
      // Retry the original request with the fresh token!
      const freshToken = sessionStorage.getItem("gcp_user_access_token");
      if (freshToken && options.headers) {
        (options.headers as any)["X-GCP-User-Token"] = freshToken;
      }
      return fetch(url, options);
    } catch (err) {
      console.error("Silent Google Cloud re-authentication was cancelled or failed:", err);
    }
  }
  
  return response;
};

// Helper to strip the hidden system instruction suffix from user messages before rendering them in the UI
const cleanUserMessage = (text: string | undefined): string => {
  if (!text) return "";
  return text.replace(/\n\n\[System Instruction: .*?\]/g, "");
};

// Main App Component
const App: React.FC = () => {
  // Authentication State
  const [user, setUser] = useState<any>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isSchemaExpanded, setIsSchemaExpanded] = useState(false);

  const isAllowedDomain = (email: string | null | undefined): boolean => {
    if (!email) return false;
    const lower = email.toLowerCase();
    
    const restrictToGoogle = import.meta.env.VITE_RESTRICT_TO_GOOGLE !== "false";
    const allowedDomainsEnv = import.meta.env.VITE_ALLOWED_DOMAINS;
    
    if (allowedDomainsEnv) {
      const allowedDomains = allowedDomainsEnv.split(",").map((d: string) => d.trim().toLowerCase());
      const emailDomain = lower.split("@")[1];
      return allowedDomains.some((domain: string) => emailDomain === domain || emailDomain.endsWith("." + domain));
    }
    
    if (restrictToGoogle) {
      return lower.endsWith("@google.com") || lower.endsWith("altostrat.com");
    }
    
    return true; // No restrictions
  };

  const getAuthErrorMessage = (): string => {
    const allowedDomainsEnv = import.meta.env.VITE_ALLOWED_DOMAINS;
    if (allowedDomainsEnv) {
      return `Access restricted to ${allowedDomainsEnv.split(",").map((d: string) => `@${d.trim()}`).join(", ")} accounts only.`;
    }
    return "Access restricted to @google.com and Argolis accounts only.";
  };

  useEffect(() => {
    if (import.meta.env.VITE_MOCK_AUTH === "true") {
      if (localStorage.getItem("mock_logout") === "true") {
        setUser(null);
        setAuthLoading(false);
      } else {
        // Support URL parameter for mock profile selection
        const params = new URLSearchParams(window.location.search);
        const isGmailMock = params.get("mock") === "gmail";
        
        if (!isAllowedDomain(isGmailMock ? "sandbox-user@gmail.com" : "admin@google.com")) {
          setUser(null);
          setAuthError(getAuthErrorMessage());
        } else {
          const email = isGmailMock 
            ? "sandbox-user@gmail.com" 
            : (import.meta.env.VITE_RESTRICT_TO_GOOGLE !== "false" ? "admin@google.com" : "admin@corporate.altostrat.com");
          setUser({
            email: email,
            displayName: isGmailMock ? "Gmail Test User" : "Argolis Test User",
            uid: "mock-user-123",
          });
        }
        setAuthLoading(false);
      }
      return;
    }

    const unsubscribe = auth.onAuthStateChanged((currentUser) => {
      if (currentUser && currentUser.email && !isAllowedDomain(currentUser.email)) {
        auth.signOut();
        setUser(null);
        setAuthError(getAuthErrorMessage());
      } else {
        setUser(currentUser);
      }
      setAuthLoading(false);
    });
    return () => unsubscribe();
  }, []);


  const handleLogin = async () => {
    const restrictToGoogle = import.meta.env.VITE_RESTRICT_TO_GOOGLE !== "false";
    setAuthError(null);
    try {
      if (import.meta.env.VITE_MOCK_AUTH === "true") {
        localStorage.removeItem("mock_logout");
        const params = new URLSearchParams(window.location.search);
        const isGmailMock = params.get("mock") === "gmail";
        
        if (restrictToGoogle && isGmailMock) {
          setUser(null);
          setAuthError("Access restricted to @google.com and Argolis accounts only.");
          return;
        }
        
        const email = isGmailMock 
          ? "sandbox-user@gmail.com" 
          : (restrictToGoogle ? "admin@google.com" : "admin@corporate.altostrat.com");
        setUser({
          email: email,
          displayName: isGmailMock ? "Gmail Test User" : "Argolis Test User",
          uid: "mock-user-123",
        });
        return;
      }
      await signInWithGoogle();
    } catch (err: any) {
      setAuthError(err.message || "Failed to sign in. Please try again.");
    }
  };

  const handleSignOut = async () => {
    trackClick("sign_out");
    try {
      if (import.meta.env.VITE_MOCK_AUTH === "true") {
        localStorage.setItem("mock_logout", "true");
      }
      await auth.signOut();
      sessionStorage.removeItem("gcp_user_access_token");
      setUser(null);
      setCurrentPage("home");
    } catch (err) {
      console.error("Failed to sign out:", err);
    }
  };

  // Google Analytics (GA4) Telemetry initialization
  useEffect(() => {
    const measurementId = import.meta.env.VITE_GA_MEASUREMENT_ID;
    if (measurementId) {
      if (!document.getElementById("google-tag-manager")) {
        const script = document.createElement("script");
        script.id = "google-tag-manager";
        script.async = true;
        script.src = `https://www.googletagmanager.com/gtag/js?id=${measurementId}`;
        document.head.appendChild(script);

        (window as any).dataLayer = (window as any).dataLayer || [];
        (window as any).gtag = function gtag() {
          (window as any).dataLayer.push(arguments);
        };
        (window as any).gtag("js", new Date());
      }
      
      (window as any).gtag("config", measurementId, {
        user_id: user ? user.email : undefined,
        anonymize_ip: true
      });
    }
  }, [user]);

  // Telemetry Audit log triggers
  const logAudit = async (eventType: string, details: any = {}) => {
    try {
      await authenticatedFetch("/api/telemetry/audit", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ event_type: eventType, details })
      });
    } catch (err) {
      console.error("Failed to post audit log:", err);
    }
  };

  const trackClick = (buttonName: string, category: string = "button_click") => {
    if ((window as any).gtag) {
      (window as any).gtag("event", "click", {
        event_category: category,
        event_label: buttonName
      });
    }
  };

  // Audit log login event
  useEffect(() => {
    if (user) {
      logAudit("LOGIN", { login_time: new Date().toISOString() });
    }
  }, [user]);

  // Navigation & Branding State
  const [currentPage, setCurrentPage] = useState<"home" | "chat" | "settings">(() => {
    return (sessionStorage.getItem("ca_current_page") as "home" | "chat" | "settings") || "home";
  });

  useEffect(() => {
    sessionStorage.setItem("ca_current_page", currentPage);

    // GA4 Page view tracking
    if ((window as any).gtag) {
      const measurementId = import.meta.env.VITE_GA_MEASUREMENT_ID;
      if (measurementId) {
        (window as any).gtag("event", "page_view", {
          page_title: currentPage,
          page_path: `/${currentPage}`,
          send_to: measurementId
        });
      }
    }

    // Log page view audit
    logAudit("PAGE_VIEW", { page: currentPage });
  }, [currentPage]);

  const [isArchModalOpen, setIsArchModalOpen] = useState(false);
  const [branding, setBranding] = useState<BrandingData | null>(null);
  const [activeBrandKey, setActiveBrandKey] = useState<string>("default");
  const [appActiveBrandKey, setAppActiveBrandKey] = useState<string>("default");

  const renderLogoSvg = (brandKey: string) => {
    const brand = branding?.brands?.[brandKey];
    if (brand && brand.logoSvg) {
      const isImg = brand.logoSvg.includes("<img") && !brand.logoSvg.includes("google_cloud_logo");
      return (
        <span 
          className={`w-full h-full flex items-center justify-center svg-logo-container ${isImg ? 'bg-white/95 p-0.5 rounded-lg' : ''}`} 
          dangerouslySetInnerHTML={{ __html: brand.logoSvg }} 
        />
      );
    }

    const normalizedKey = brandKey.toLowerCase().replace(/[^a-z0-9]/g, "");
    switch (normalizedKey) {
      case "target":
        return (
          <svg viewBox="0 0 24 24" className="w-full h-full text-red-600 fill-current">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2.5" fill="none" />
            <circle cx="12" cy="12" r="4.5" fill="currentColor" />
          </svg>
        );
      case "homedepot":
        return (
          <svg viewBox="0 0 24 24" className="w-full h-full text-orange-500 fill-current">
            <rect x="2" y="2" width="20" height="20" rx="3" />
            <text x="12" y="15" fill="white" fontSize="9" fontWeight="bold" fontFamily="sans-serif" textAnchor="middle">HD</text>
          </svg>
        );
      case "fleetpride":
        return (
          <svg viewBox="0 0 24 24" className="w-full h-full text-sky-500 fill-current">
            <path d="M12 2L3 6v6c0 5.55 3.85 10.73 9 12 5.15-1.27 9-6.45 9-12V6l-9-4zm0 2.18l7 3.11v4.88c0 4.19-2.73 8.16-7 9.17-4.27-1.01-7-4.98-7-9.17V7.29l7-3.11z" />
            <polygon points="12,7 8,11 11,11 11,17 13,17 13,13 16,13" className="text-orange-500 fill-current" />
          </svg>
        );
      case "tractorsupply":
        return (
          <svg viewBox="0 0 48 44" className="w-full h-full fill-current text-brand-primary">
            <path d="M0 1.14282L13.0253 42.9524L39.0723 34.2354L47.8055 1.14282H0Z" fill="white" />
            <path d="M0 1.14282L13.0253 42.9524L39.0723 34.2354L47.8055 1.14282H0ZM16.722 8.61842H14.1537V6.71721H13.3333V21.1242L14.2645 21.682V24.4777H8.68467V21.682L9.61578 21.1242V6.71721H8.81966V8.61842H6.27207V2.77535H16.722V8.61842ZM26.8709 12.9582H24.0118V12.0467C23.991 9.57753 21.2946 9.64895 21.6165 11.4855C21.7584 12.295 23.5895 15.1043 25.154 18.1483C29.3493 26.3177 23.316 31.5486 19.9377 27.7904L19.3666 28.5556H17.4524V21.8929H20.4396V23.5934C20.3011 26.0014 25.5867 26.4197 21.2219 18.6448C19.6123 15.7743 18.9512 14.6588 18.3835 13.0296C16.857 8.66944 19.9792 6.75122 22.0388 6.81244C22.853 6.79701 23.6422 7.08918 24.2437 7.6287L24.801 6.85325H26.8709V12.9582ZM38.5151 28.0591C38.5151 31.8581 35.9848 33.7695 34.0014 33.7763C31.0177 33.7831 28.2762 32.1574 28.5462 21.1854C28.8543 8.50278 35.6317 11.2237 35.7875 12.0399L36.3448 11.3597H38.4147V17.4647L35.5036 17.4579V16.3695C35.2752 13.4888 32.0457 13.5262 32.1876 21.546C32.2949 27.6135 32.4368 30.0181 34.2818 30.0215C35.4898 30.0215 35.4898 28.4162 35.5002 28.423V26.032H38.5151V28.0625V28.0591Z" fill="currentColor" />
          </svg>
        );
      default:
        return (
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="-1 0 32 28" className="w-full h-full">
            <path fill="#ea4335" d="M21.85,7.41l1,0,2.85-2.85.14-1.21A12.81,12.81,0,0,0,5,9.6a1.55,1.55,0,0,1,1-.06l5.7-.94s.29-.48.44-.45a7.11,7.11,0,0,1,9.73-.74Z"/>
            <path fill="#4285f4" d="M29.76,9.6a12.84,12.84,0,0,0-3.87-6.24l-4,4A7.11,7.11,0,0,1,24.5,13v.71a3.56,3.56,0,1,1,0,7.12H17.38l-.71.72v4.27l.71.71H24.5A9.26,9.26,0,0,0,29.76,9.6Z"/>
            <path fill="#34a853" d="M10.25,26.49h7.12v-5.7H10.25a3.54,3.54,0,0,1-1.47-.32l-1,.31L4.91,23.63l-.25,1A9.21,9.21,0,0,0,10.25,26.49Z"/>
            <path fill="#fbbc05" d="M10.25,8A9.26,9.26,0,0,0,4.66,24.6l4.13-4.13a3.56,3.56,0,1,1,4.71-4.71l4.13-4.13A9.25,9.25,0,0,0,10.25,8Z"/>
          </svg>
        );
    }
  };

  const handleOpenArchitecture = () => {
    setIsArchModalOpen(true);
  };
  
  // Workspace Session State
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string>("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedConvo, setSelectedConvo] = useState<string>("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loadingAgentSchema, setLoadingAgentSchema] = useState<boolean>(false);


  // Connection and Reasoning Modes
  const [credentialsMode, setCredentialsMode] = useState<"service_account" | "user_sso">(
    (localStorage.getItem("gcp_credentials_mode") as any) || "service_account"
  );
  const [chatMode, setChatMode] = useState<"fast" | "thinking">("fast");
  const [showChatModeDropdown, setShowChatModeDropdown] = useState(false);
  const [showConnDropdown, setShowConnDropdown] = useState(false);
  const [deletingConvoName, setDeletingConvoName] = useState<string | null>(null);
  const [isCreatingConvo, setIsCreatingConvo] = useState(false);
  
  // Dynamic GCP Projects States
  const [gcpProjects, setGcpProjects] = useState<{ projectId: string; name: string }[]>([]);
  const [selectedProject, setSelectedProject] = useState<string>(
    localStorage.getItem("gcp_selected_project") || ""
  );

  const fetchGcpProjects = async () => {
    try {
      const res = await authenticatedFetch("/api/gcp/projects");
      if (res.ok) {
        const data = await res.json();
        setGcpProjects(data);
        
        if (data.length > 0) {
          const currentProj = localStorage.getItem("gcp_selected_project") || "";
          const exists = data.some((p: any) => p.projectId === currentProj);
          if (!exists || !currentProj) {
            setSelectedProject(data[0].projectId);
            localStorage.setItem("gcp_selected_project", data[0].projectId);
          }
        } else {
          setSelectedProject("");
          localStorage.removeItem("gcp_selected_project");
        }
      }
    } catch (e) {
      console.error("Failed to fetch GCP projects list:", e);
    }
  };

  const handleProjectChange = (projectId: string) => {
    setSelectedProject(projectId);
    localStorage.setItem("gcp_selected_project", projectId);
    
    // Reset active agent and conversations when switching projects to avoid cross-project leaks
    setSelectedAgent("");
    setConversations([]);
    setMessages([]);
    sessionStorage.removeItem("activeAgentName");
    
    // Reload the agents list for the new project
    fetchAgents();
  };

  const handleLocationChange = (location: string) => {
    localStorage.setItem("gcp_selected_location", location);
    
    // Reset active agent and conversations when switching locations to avoid cross-location leaks
    setSelectedAgent("");
    setConversations([]);
    setMessages([]);
    sessionStorage.removeItem("activeAgentName");
    
    // Reload the agents list for the new location
    fetchAgents();
  };

  const isCorporateUser = (email: string | null): boolean => {
    if (!email) return false;
    const lowerEmail = email.toLowerCase();
    return lowerEmail.endsWith("altostrat.com");
  };

  const handleCredentialsModeChange = async (mode: "service_account" | "user_sso") => {
    // If they switched to SSO, verify corporate membership and request GCP scope incrementally
    if (mode === "user_sso") {
      const email = user?.email || auth.currentUser?.email || null;
      if (!isCorporateUser(email)) {
        alert("SSO credentials mode is restricted to Argolis accounts only.");
        return;
      }
      
      const gcpToken = sessionStorage.getItem("gcp_user_access_token");
      if (!gcpToken) {
        try {
          // Trigger Google Consent screen popup to get a fresh GCP access token!
          await requestGCPToken();
        } catch (err) {
          console.error("Failed to authenticate user for SSO credentials:", err);
          // Revert back to service account if they cancel the login popup
          setCredentialsMode("service_account");
          localStorage.setItem("gcp_credentials_mode", "service_account");
          return;
        }
      }
    }

    setCredentialsMode(mode);
    localStorage.setItem("gcp_credentials_mode", mode);
    // Fetch projects first for the new mode, then reload the agents
    await fetchGcpProjects();
    await fetchAgents();
  };
  const getDisplayStepInfo = (actualStep: number) => {
    if (actualStep >= 14 && actualStep <= 20) {
      const hasConvos = conversations.length > 0;
      if (hasConvos) {
        return {
          num: actualStep - 13,
          text: actualStep === 14 ? "Demo: Select AI Agent"
              : actualStep === 15 ? "Demo: Choose Thinking Mode"
              : actualStep === 16 ? "Demo: Clean Slate"
              : actualStep === 17 ? "Demo: Toggle Schema"
              : actualStep === 18 ? "Demo: Ask a Question"
              : actualStep === 19 ? "Demo: Show Thinking Process"
              : "Demo: Multi-turn & Follow-ups",
          total: 7
        };
      } else {
        const num = actualStep === 14 ? 1
                  : actualStep === 15 ? 2
                  : actualStep === 17 ? 3
                  : actualStep === 18 ? 4
                  : actualStep === 19 ? 5
                  : 6;
        return {
          num,
          text: actualStep === 14 ? "Demo: Select AI Agent"
              : actualStep === 15 ? "Demo: Choose Thinking Mode"
              : actualStep === 17 ? "Demo: Toggle Schema"
              : actualStep === 18 ? "Demo: Ask a Question"
              : actualStep === 19 ? "Demo: Show Thinking Process"
              : "Demo: Multi-turn & Follow-ups",
          total: 6
        };
      }
    }
    if (window.innerWidth < 768 && actualStep === 1) {
      return {
        num: 1,
        text: "Guided Tour: Available on Desktop",
        total: 1
      };
    }
    const isGmailUser = !isCorporateUser(user?.email || auth.currentUser?.email || null);
    if (isGmailUser) {
      if (actualStep === 1) return { num: 1, text: "1. Configure Portal", total: 11 };
      if (actualStep === 3) return { num: 2, text: "2. Customize Branding", total: 11 };
      if (actualStep === 4) return { num: 3, text: "3. Live Portal Preview", total: 11 };
      if (actualStep === 5) return { num: 4, text: "4. Save Branding Config", total: 11 };
      if (actualStep === 6) return { num: 5, text: "5. Return to Dashboard", total: 11 };
      if (actualStep === 7) return { num: 6, text: "6. Recent Chat History", total: 11 };
      if (actualStep === 8) return { num: 7, text: "7. Launch Chat Workspace", total: 11 };
      if (actualStep === 9) return { num: 8, text: "8. Select AI Agent", total: 11 };
      if (actualStep === 10) return { num: 9, text: "9. Manage History", total: 11 };
      if (actualStep === 11) return { num: 10, text: "10. Switch Chat Mode", total: 11 };
      if (actualStep === 13) return { num: 11, text: "11. Reference Architecture", total: 11 };
    }
    return {
      num: actualStep,
      text: actualStep === 1 ? "1. Configure Portal"
          : actualStep === 2 ? "2. Connection & Credentials"
          : actualStep === 3 ? "3. Customize Branding"
          : actualStep === 4 ? "4. Live Portal Preview"
          : actualStep === 5 ? "5. Save Branding Config"
          : actualStep === 6 ? "6. Return to Dashboard"
          : actualStep === 7 ? "7. Recent Chat History"
          : actualStep === 8 ? "8. Launch Chat Workspace"
          : actualStep === 9 ? "9. Select AI Agent"
          : actualStep === 10 ? "10. Manage History"
          : actualStep === 11 ? "11. Switch Chat Mode"
          : actualStep === 12 ? "12. Override Connection"
          : actualStep === 13 ? "13. Reference Architecture"
          : "",
      total: 13
    };
  };

  // Chat inputs & states
  const [inputText, setInputText] = useState("");
  const [isQuerying, setIsQuerying] = useState(false);

  const [streamingMessages, setStreamingMessages] = useState<any[]>([]);
  const [connectionStatus, setConnectionStatus] = useState<"online" | "loading" | "error">("online");

  // Settings form states
  const [settingsActiveTab, setSettingsActiveTab] = useState<"general" | "branding">(() => {
    return (sessionStorage.getItem("ca_settings_tab") as "general" | "branding") || "general";
  });

  useEffect(() => {
    const email = user?.email || auth.currentUser?.email || null;
    if (!isCorporateUser(email)) {
      if (settingsActiveTab !== "branding") {
        setSettingsActiveTab("branding");
      }
    } else {
      sessionStorage.setItem("ca_settings_tab", settingsActiveTab);
    }
  }, [settingsActiveTab, user]);

  const [settingsProjectId, setSettingsProjectId] = useState("");
  const [settingsLocation, setSettingsLocation] = useState<string>(
    localStorage.getItem("gcp_selected_location") || "all"
  );
  const [settingsTestResult, setSettingsTestResult] = useState("");
  const [settingsTestSuccess, setSettingsTestSuccess] = useState<boolean | null>(null);
  const [settingsSaveResult, setSettingsSaveResult] = useState("");

  // Branding config inputs
  const [brandName, setBrandName] = useState("");
  const [brandPrimary, setBrandPrimary] = useState("");
  const [brandSecondary, setBrandSecondary] = useState("");
  const [brandBgStart, setBrandBgStart] = useState("");
  const [brandBgEnd, setBrandBgEnd] = useState("");
  const [brandLogoText, setBrandLogoText] = useState("");
  const [brandWelcome, setBrandWelcome] = useState("");
  const [brandLogoSvg, setBrandLogoSvg] = useState("");
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  
  // Onboarding Tour State
  const [tourStep, setTourStep] = useState<number>(0);
  const [tooltipStyle, setTooltipStyle] = useState<React.CSSProperties>({});
  // Logo Web Search States
  const [logoSearchQuery, setLogoSearchQuery] = useState("");
  const [logoSearchResults, setLogoSearchResults] = useState<{ title: string; url: string; source: string }[]>([]);
  const [isSearchingLogo, setIsSearchingLogo] = useState(false);
  const [logoSearchError, setLogoSearchError] = useState("");
  const [isGeneratingFromLogo, setIsGeneratingFromLogo] = useState(false);


  const messagesEndRef = useRef<HTMLDivElement>(null);
  const logoFileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const connDropdownRef = useRef<HTMLDivElement>(null);
  const chatModeDropdownRef = useRef<HTMLDivElement>(null);
  // Responsive Tour Sidebar Auto-Toggle Effect
  useEffect(() => {
    if (window.innerWidth < 768) {
      if (tourStep === 9 || tourStep === 10 || tourStep === 14 || tourStep === 16) {
        setIsSidebarOpen(true);
      } else if (tourStep === 11 || tourStep === 15 || tourStep === 17 || tourStep === 19) {
        setIsSidebarOpen(false);
      }
    }
  }, [tourStep]);

  // Click outside and Escape key listeners to close connection/chat-mode dropdowns
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (connDropdownRef.current && !connDropdownRef.current.contains(e.target as Node)) {
        setShowConnDropdown(false);
      }
      if (chatModeDropdownRef.current && !chatModeDropdownRef.current.contains(e.target as Node)) {
        console.log("handleClickOutside closed chatModeDropdown! target:", e.target);
        setShowChatModeDropdown(false);
      }
    };
    
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setShowConnDropdown(false);
        setShowChatModeDropdown(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    window.addEventListener("keydown", handleKeyDown);
    
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  // Initialize and Fetch Branding
  const fetchBranding = async () => {
    try {
      const res = await authenticatedFetch("/api/branding");
      if (res.ok) {
        const data: BrandingData = await res.json();
        setBranding(data);
        
        // Always default to the standard GCP theme ("default") upon fresh page load or login
        const sessionActiveKey = "default";
        setActiveBrandKey(sessionActiveKey);
        setAppActiveBrandKey(sessionActiveKey);
        
        const active = data.brands[sessionActiveKey] || data.brands["default"];
        applyBrandingCSS(active);
        
        // Update branding edit fields
        setBrandName(active.name);
        setBrandPrimary(active.primaryColor);
        setBrandSecondary(active.secondaryColor);
        setBrandBgStart(active.backgroundColorStart);
        setBrandBgEnd(active.backgroundColorEnd);
        setBrandLogoText(active.logoText);
        setBrandWelcome(active.welcomeMessage);
        setBrandLogoSvg(active.logoSvg || "");
        
        // Sync active workspace settings with the brand defaults to overwrite stale localStorage
        const resolvedProj = active.gcpProjectId || "";
        const resolvedLoc = active.gcpLocation || "all";
        
        setSettingsProjectId(resolvedProj);
        setSettingsLocation(resolvedLoc);
        
        setSelectedProject(resolvedProj);
        localStorage.setItem("gcp_selected_project", resolvedProj);
        
        localStorage.setItem("gcp_selected_location", resolvedLoc);
      }
    } catch (e) {
      console.error("Failed to load branding configuration:", e);
    }
  };

  const applyBrandingCSS = (brand: BrandConfig) => {
    if (brand.primaryColor) {
      document.documentElement.style.setProperty("--primary-color", brand.primaryColor);
    }
    if (brand.secondaryColor) {
      document.documentElement.style.setProperty("--secondary-color", brand.secondaryColor);
    }
    if (brand.backgroundColorStart) {
      document.documentElement.style.setProperty("--bg-start", brand.backgroundColorStart);
    }
    if (brand.backgroundColorEnd) {
      document.documentElement.style.setProperty("--bg-end", brand.backgroundColorEnd);
    }
    document.title = `${brand.name} - Data Workspace`;
  };

  // Lazy-load detailed schema and suggestions for a selected agent on-demand
  const fetchAgentSchema = async (agentName: string, currentAgentsList?: Agent[]) => {
    if (!agentName) return;
    
    const targetList = currentAgentsList || agents;
    const agent = targetList.find(a => a.name === agentName);
    if (!agent) return;
    
    if (agent.isGraphAgent && !agent.graphData) {
      setLoadingAgentSchema(true);
      try {
        const res = await authenticatedFetch(`/api/agents/${encodeURIComponent(agentName)}/schema`);
        if (res.ok) {
          const enriched = await res.json();
          setAgents(prev => prev.map(a => a.name === agentName ? { 
            ...a, 
            graphData: enriched.graphData,
            welcomeSubtitle: enriched.welcomeSubtitle,
            suggestions: enriched.suggestions
          } : a));
        }
      } catch (err) {
        console.error("Failed to lazy-load agent schema:", err);
      } finally {
        setLoadingAgentSchema(false);
      }
    }
  };

  // Fetch Agents
  const fetchAgents = async () => {
    try {
      const res = await authenticatedFetch("/api/agents");
      if (res.ok) {
        const data = await res.json();
        

        setAgents(data);
        setConnectionStatus("online");
        
        if (data.length > 0) {
          const nameParts = data[0].name.split("/");
          if (nameParts[0] === "projects") {
            setSettingsProjectId(nameParts[1]);
          }
        }

        // Restore active agent from session storage or fallback to auto-selecting the first agent
        const savedAgent = sessionStorage.getItem("activeAgentName");
        const activeAgentName = (savedAgent && data.some((a: Agent) => a.name === savedAgent)) ? savedAgent : (data.length > 0 ? data[0].name : "");
        
        if (activeAgentName) {
          setSelectedAgent(activeAgentName);
          if (!savedAgent && data.length > 0) {
            sessionStorage.setItem("activeAgentName", activeAgentName);
          }
          fetchConversations(activeAgentName);
          // Trigger lazy loading of the graph schema for the resolved active agent!
          fetchAgentSchema(activeAgentName, data);
        }
      } else {
        setConnectionStatus("error");
      }
    } catch (e: any) {
      console.error("Error loading agent list:", e);
      setConnectionStatus("error");
    }
  };

  // Fetch Conversations for selected Agent
  const fetchConversations = async (agentName: string, selectConvoName?: string, skipFetchMessages = false) => {
    try {
      const res = await authenticatedFetch(`/api/conversations/${encodeURIComponent(agentName)}`);
      if (res.ok) {
        const data = await res.json();
        setConversations(data);
        
        if (selectConvoName) {
          setSelectedConvo(selectConvoName);
          if (!skipFetchMessages) {
            fetchMessages(selectConvoName);
          }
        } else if (data.length > 0) {
          const targetConvo = data[0].name;
          setSelectedConvo(targetConvo);
          fetchMessages(targetConvo);
        } else {
          setSelectedConvo("");
          setMessages([]);
        }
      }
    } catch (e) {
      console.error("Error loading conversation list:", e);
    }
  };

  // Fetch past messages
  const fetchMessages = async (convoName: string) => {
    try {
      const res = await authenticatedFetch(`/api/messages/${encodeURIComponent(convoName)}`);
      if (res.ok) {
        const data = await res.json();
        setMessages(groupConversationalMessages(data));
        
        // Auto-detect and restore the chat mode (Fast vs Thinking) based on the user prompt's hidden instruction
        const userMsgs = data.filter((m: any) => !!m.userMessage);
        if (userMsgs.length > 0) {
          const lastUserText = userMsgs[userMsgs.length - 1].userMessage?.text || "";
          if (lastUserText.includes("Please think step-by-step")) {
            setChatMode("thinking");
          } else if (lastUserText.includes("Please provide a fast, direct")) {
            setChatMode("fast");
          }
        }
      }
    } catch (e) {
      console.error("Error loading messages:", e);
    }
  };



  useEffect(() => {
    if (user) {
      const init = async () => {
        await fetchBranding();
        // If credentialsMode is user_sso, check if we have the Google OAuth token!
        if (credentialsMode === "user_sso") {
          const email = user?.email || auth.currentUser?.email || null;
          if (!isCorporateUser(email)) {
            // Revert back to service account for non-corporate users
            setCredentialsMode("service_account");
            localStorage.setItem("gcp_credentials_mode", "service_account");
          } else {
            const gcpToken = sessionStorage.getItem("gcp_user_access_token");
            if (!gcpToken) {
              try {
                // Automatically trigger consent popup to get a fresh GCP access token!
                await requestGCPToken();
              } catch (err) {
                console.error("Failed to authenticate user for SSO credentials on startup:", err);
                // Fallback to service account if cancelled
                setCredentialsMode("service_account");
                localStorage.setItem("gcp_credentials_mode", "service_account");
              }
            }
          }
        }
        await fetchGcpProjects();
        await fetchAgents();
      };
      init();
    }
  }, [user]);



  // Scroll to bottom when messages list updates or during streaming
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingMessages]);

  // Dynamically update document title and browser favicon based on active branding
  useEffect(() => {
    const activeBrand = branding?.brands[appActiveBrandKey] || branding?.brands["default"];
    if (activeBrand) {
      // 1. Update document title
      document.title = activeBrand.name ? `${activeBrand.name} AI Experience Hub` : "AI Experience Hub";

      // 2. Update favicon
      const faviconLink = document.querySelector("link[rel~='icon']") as HTMLLinkElement;
      if (faviconLink) {
        let logoUrl = "";
        let svgString = "";
        
        if (activeBrand.logoSvg) {
          if (activeBrand.logoSvg.includes("<svg")) {
            svgString = activeBrand.logoSvg;
          } else if (activeBrand.logoSvg.includes("<img")) {
            // Extract src URL from the img element string
            const srcMatch = activeBrand.logoSvg.match(/src=["']([^"']+)["']/);
            if (srcMatch) {
              logoUrl = srcMatch[1].replace(/&amp;/g, "&"); // Replace html-encoded entities
            }
          }
        }
        
        if (!logoUrl && !svgString) {
          if (activeBrand.logoUrl) {
            logoUrl = activeBrand.logoUrl;
          } else {
            // Fallback to static SVG definitions
            const normalizedKey = appActiveBrandKey.toLowerCase().replace(/[^a-z0-9]/g, "");
            if (normalizedKey === "target") {
              svgString = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="#dc2626" stroke-width="2.5" fill="none" /><circle cx="12" cy="12" r="4.5" fill="#dc2626" /></svg>`;
            } else if (normalizedKey === "homedepot") {
              svgString = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect x="2" y="2" width="20" height="20" rx="3" fill="#f97316" /><text x="12" y="15" fill="white" font-size="9" font-weight="bold" font-family="sans-serif" text-anchor="middle">HD</text></svg>`;
            } else if (normalizedKey === "fleetpride") {
              svgString = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12 2L3 6v6c0 5.55 3.85 10.73 9 12 5.15-1.27 9-6.45 9-12V6l-9-4zm0 2.18l7 3.11v4.88c0 4.19-2.73 8.16-7 9.17-4.27-1.01-7-4.98-7-9.17V7.29l7-3.11z" fill="#0284c7" /><polygon points="12,7 8,11 11,11 11,17 13,17 13,13 16,13" fill="#f97316" /></svg>`;
            } else if (normalizedKey === "tractorsupply") {
              svgString = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 44"><path d="M0 1.14282L13.0253 42.9524L39.0723 34.2354L47.8055 1.14282H0Z" fill="white" /><path d="M0 1.14282L13.0253 42.9524L39.0723 34.2354L47.8055 1.14282H0ZM16.722 8.61842H14.1537V6.71721H13.3333V21.1242L14.2645 21.682V24.4777H8.68467V21.682L9.61578 21.1242V6.71721H8.81966V8.61842H6.27207V2.77535H16.722V8.61842ZM26.8709 12.9582H24.0118V12.0467C23.991 9.57753 21.2946 9.64895 21.6165 11.4855C21.7584 12.295 23.5895 15.1043 25.154 18.1483C29.3493 26.3177 23.316 31.5486 19.9377 27.7904L19.3666 28.5556H17.4524V21.8929H20.4396V23.5934C20.3011 26.0014 25.5867 26.4197 21.2219 18.6448C19.6123 15.7743 18.9512 14.6588 18.3835 13.0296C16.857 8.66944 19.9792 6.75122 22.0388 6.81244C22.853 6.79701 23.6422 7.08918 24.2437 7.6287L24.801 6.85325H26.8709V12.9582ZM38.5151 28.0591C38.5151 31.8581 35.9848 33.7695 34.0014 33.7763C31.0177 33.7831 28.2762 32.1574 28.5462 21.1854C28.8543 8.50278 35.6317 11.2237 35.7875 12.0399L36.3448 11.3597H38.4147V17.4647L35.5036 17.4579V16.3695C35.2752 13.4888 32.0457 13.5262 32.1876 21.546C32.2949 27.6135 32.4368 30.0181 34.2818 30.0215C35.4898 30.0215 35.4898 28.4162 35.5002 28.423V26.032H38.5151V28.0625V28.0591Z" fill="#f97316" /></svg>`;
            } else {
              // Default Google Cloud logo
              svgString = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 35 32"><path fill="#ea4335" d="M21.85,7.41l1,0,2.85-2.85.14-1.21A12.81,12.81,0,0,0,5,9.6a1.55,1.55,0,0,1,1-.06l5.7-.94s.29-.48.44-.45a7.11,7.11,0,0,1,9.73-.74Z"/><path fill="#4285f4" d="M29.76,9.6a12.84,12.84,0,0,0-3.87-6.24l-4,4A7.11,7.11,0,0,1,24.5,13v.71a3.56,3.56,0,1,1,0,7.12H17.38l-.71.72v4.27l.71.71H24.5A9.26,9.26,0,0,0,29.76,9.6Z"/><path fill="#34a853" d="M10.25,26.49h7.12v-5.7H10.25a3.54,3.54,0,0,1-1.47-.32l-1,.31L4.91,23.63l-.25,1A9.21,9.21,0,0,0,10.25,26.49Z"/><path fill="#fbbc05" d="M10.25,8A9.26,9.26,0,0,0,4.66,24.6l4.13-4.13a3.56,3.56,0,1,1,4.71-4.71l4.13-4.13A9.25,9.25,0,0,0,10.25,8Z"/></svg>`;
            }
          }
        }

        if (logoUrl) {
          faviconLink.href = logoUrl;
        } else if (svgString) {
          const svgBlob = new Blob([svgString], { type: 'image/svg+xml' });
          const blobUrl = URL.createObjectURL(svgBlob);
          faviconLink.href = blobUrl;
          
          return () => {
            URL.revokeObjectURL(blobUrl);
          };
        }
      }
    }
  }, [appActiveBrandKey, branding]);

  // Onboarding Tour Effects & Handlers
  useEffect(() => {
    if (user) {
      const seen = sessionStorage.getItem("ca_visited_tour") === "true";
      if (!seen) {
        const t = setTimeout(() => {
          setTourStep(-1);
        }, 1500);
        return () => clearTimeout(t);
      }
    }
  }, [user]);

  useEffect(() => {
    if (tourStep === 0 || tourStep === -1) return;

    // Self-healing: If we navigated to the chat page while on Step 8, advance to Step 9!
    if (currentPage === "chat" && tourStep === 8) {
      setTourStep(9);
      return;
    }

    let targetId = "";
    if (tourStep === 1) targetId = "settings-gear-btn";
    else if (tourStep === 2) targetId = "settings-sidebar-nav";
    else if (tourStep === 3) targetId = "settings-branding-controls";
    else if (tourStep === 4) targetId = "settings-trigger-preview-btn";
    else if (tourStep === 5) targetId = "settings-save-branding-btn";
    else if (tourStep === 6) targetId = "settings-back-home";
    else if (tourStep === 7) targetId = "dashboard-recent-chats";
    else if (tourStep === 8) targetId = "dashboard-launch-chat-btn";
    else if (tourStep === 9) targetId = "agent-select-container";
    else if (tourStep === 10) targetId = "conversations-panel-container";
    else if (tourStep === 11) targetId = "chat-mode-btn";
    else if (tourStep === 12) targetId = "project-override-container";
    else if (tourStep === 13) targetId = window.innerWidth < 768 ? "sidebar-arch-diagram-btn" : "arch-diagram-btn";
    else if (tourStep === 14) targetId = "agent-select-container";
    else if (tourStep === 15) targetId = "chat-mode-btn";
    else if (tourStep === 16) targetId = "new-convo-btn";
    else if (tourStep === 17) targetId = "toggle-schema-btn";
    else if (tourStep === 18) targetId = "chat-input-container";
    else if (tourStep === 19) targetId = "show-thinking-btn";
    else if (tourStep === 20) targetId = "chat-suggestions-container";

    const isElementVisible = (element: HTMLElement, checkTop = false): boolean => {
      const rect = element.getBoundingClientRect();
      
      // Identify if the element resides inside the top fixed header
      const isHeaderElement = !!element.closest('header');
      
      // 1. Viewport check (completely offscreen or too close to the edges)
      // For header elements, the minimum visible Y is 0.
      // For body elements, the minimum Y is 64px (to prevent clipping under the header).
      const minVisibleY = isHeaderElement ? 0 : 64;
      const bottomBuffer = isHeaderElement ? 0 : 30;
      
      if (rect.bottom < minVisibleY || rect.top > window.innerHeight - bottomBuffer) {
        return false;
      }
      
      // If we specifically care about the top of the element (only applicable to body elements).
      // For very tall elements like the branding card, we allow the top to sit under the header
      // (down to Y = 0px) when centered on shorter viewports to prevent hiding the tooltip.
      const minTopY = 0;
      if (!isHeaderElement && checkTop && rect.top < minTopY) {
        return false;
      }
      
      // 2. Scroll parent clipping check
      let parent = element.parentElement;
      while (parent && parent !== document.body) {
        const style = window.getComputedStyle(parent);
        const isScrollable = style.overflowY === 'auto' || style.overflowY === 'scroll';
        
        if (isScrollable) {
          const parentRect = parent.getBoundingClientRect();
          // Hide if the bottom of the element is above the parent's top boundary
          // or the top of the element is below the parent's bottom boundary
          if (rect.top >= parentRect.bottom - 30 || rect.bottom <= parentRect.top + 30) {
            return false;
          }
          // If checking top clipping, also hide if the top of the element is above the parent's top boundary
          if (checkTop && rect.top < parentRect.top) {
            return false;
          }
        }
        parent = parent.parentElement;
      }
      
      return true;
    };

    const updatePosition = (shouldScroll = false) => {
      if (window.innerWidth < 768) {
        setTooltipStyle({
          position: 'fixed',
          bottom: '24px',
          left: '50%',
          transform: 'translateX(-50%)',
          width: 'calc(100% - 32px)',
          maxWidth: '400px',
          zIndex: 2200,
          opacity: 1,
          transition: 'opacity 0.15s ease'
        });
        return;
      }

      let activeTargetId = targetId;
      if (tourStep === 19) {
        activeTargetId = document.getElementById("show-thinking-btn") ? "show-thinking-btn" : "agent-thinking-bubble";
      }
      const el = document.getElementById(activeTargetId);
      if (!el) {
        setTimeout(() => updatePosition(shouldScroll), 100);
        return;
      }
      
      const checkTop = (tourStep === 3 || tourStep === 12);
      
      // Auto-scroll target element into view only on initial step change
      if (shouldScroll) {
        const alignBlock = checkTop ? 'start' : 'nearest';
        el.scrollIntoView({ behavior: 'auto', block: alignBlock });
      }
      if (!isElementVisible(el, checkTop)) {
        setTooltipStyle({
          position: 'fixed',
          opacity: 0,
          pointerEvents: 'none',
          zIndex: -1,
          transition: 'opacity 0.15s ease'
        });
        return;
      }
      
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) {
        setTimeout(() => updatePosition(shouldScroll), 100);
        return;
      }
      
      const isThinkingBubble = (tourStep === 19 && activeTargetId === "agent-thinking-bubble");

      if (tourStep === 1 || tourStep === 6 || tourStep === 13 || tourStep === 17 || isThinkingBubble) {
        setTooltipStyle({
          position: 'fixed',
          top: `${rect.bottom + 12}px`,
          right: (tourStep === 1 || tourStep === 13 || tourStep === 17) ? `${window.innerWidth - rect.right}px` : undefined,
          left: (tourStep === 6 || isThinkingBubble) ? `${rect.left}px` : undefined,
          zIndex: 9999,
          opacity: 1,
          transition: 'opacity 0.15s ease, transform 0.15s ease'
        });
      } else if (tourStep === 2 || tourStep === 9 || tourStep === 10 || tourStep === 14 || tourStep === 16) {
        setTooltipStyle({
          position: 'fixed',
          top: `${rect.top - 10}px`,
          left: `${rect.right + 16}px`,
          zIndex: 9999,
          opacity: 1,
          transition: 'opacity 0.15s ease, transform 0.15s ease'
        });
      } else if (tourStep === 11 || tourStep === 15) {
        setTooltipStyle({
          position: 'fixed',
          bottom: `${window.innerHeight - rect.bottom - 10}px`,
          left: `${rect.right + 16}px`,
          zIndex: 9999,
          opacity: 1,
          transition: 'opacity 0.15s ease, transform 0.15s ease'
        });
      } else if (tourStep === 3 || tourStep === 12) {
        setTooltipStyle({
          position: 'fixed',
          top: `${rect.top - 10}px`,
          left: `${rect.left - 356}px`,
          zIndex: 9999,
          opacity: 1,
          transition: 'opacity 0.15s ease, transform 0.15s ease'
        });
      } else if (tourStep === 4 || tourStep === 5 || tourStep === 7 || tourStep === 8 || tourStep === 18 || (tourStep === 19 && !isThinkingBubble) || tourStep === 20) {
        const useRightAlign = (tourStep === 4 || tourStep === 5);
        setTooltipStyle({
          position: 'fixed',
          bottom: `${window.innerHeight - rect.top + 12}px`,
          left: useRightAlign ? undefined : `${rect.left}px`,
          right: useRightAlign ? `${window.innerWidth - rect.right}px` : undefined,
          zIndex: 9999,
          opacity: 1,
          transition: 'opacity 0.15s ease, transform 0.15s ease'
        });
      }
    };

    // Trigger initial snap-scroll and positioning
    const t = setTimeout(() => updatePosition(true), 50);
    const t2 = setTimeout(() => updatePosition(false), 250); // Capture late-rendering elements after tab/modal transitions
    
    // Position updates (without snapping back scroll)
    const handleResize = () => updatePosition(false);
    const handleScroll = () => updatePosition(false);

    window.addEventListener("resize", handleResize);
    window.addEventListener("scroll", handleScroll, { capture: true });

    return () => {
      clearTimeout(t);
      clearTimeout(t2);
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("scroll", handleScroll, { capture: true });
    };
  }, [tourStep, currentPage, settingsActiveTab]);

  const startDemoWalkthrough = () => {
    setIsArchModalOpen(false);
    setCurrentPage("chat");
    setTourStep(14);
  };

  const handleNextTour = () => {
    const email = user?.email || auth.currentUser?.email || null;
    if (tourStep === 1) {
      setCurrentPage("settings");
      if (!isCorporateUser(email)) {
        setSettingsActiveTab("branding");
        setTourStep(3);
      } else {
        setSettingsActiveTab("general");
        setTourStep(2);
      }
    } else if (tourStep === 2) {
      setSettingsActiveTab("branding");
      setTourStep(3);
    } else if (tourStep === 3) {
      setTourStep(4);
    } else if (tourStep === 4) {
      setShowPreviewModal(false);
      setTourStep(5);
    } else if (tourStep === 5) {
      setTourStep(6);
    } else if (tourStep === 6) {
      setCurrentPage("home");
      setTourStep(7);
    } else if (tourStep === 7) {
      setTourStep(8);
    } else if (tourStep === 8) {
      setCurrentPage("chat");
      setTourStep(9);
    } else if (tourStep === 9) {
      setTourStep(10);
    } else if (tourStep === 10) {
      setTourStep(11);
    } else if (tourStep === 11) {
      if (!isCorporateUser(email)) {
        setTourStep(13);
      } else {
        setTourStep(12);
      }
    } else if (tourStep === 12) {
      setTourStep(13);
    } else if (tourStep === 13) {
      setIsArchModalOpen(false);
      setTourStep(0);
      sessionStorage.setItem("ca_visited_tour", "true");
    } else if (tourStep === 15) {
      if (conversations.length === 0) {
        setTourStep(17);
      } else {
        setTourStep(16);
      }
    } else if (tourStep >= 14 && tourStep <= 19) {
      setTourStep(tourStep + 1);
    } else if (tourStep === 20) {
      setTourStep(0);
      sessionStorage.setItem("ca_visited_tour", "true");
    }
  };

  const handleBackTour = () => {
    const email = user?.email || auth.currentUser?.email || null;
    if (tourStep === 2) {
      setCurrentPage("home");
      setTourStep(1);
    } else if (tourStep === 3) {
      if (!isCorporateUser(email)) {
        setCurrentPage("home");
        setTourStep(1);
      } else {
        setSettingsActiveTab("general");
        setTourStep(2);
      }
    } else if (tourStep === 4) {
      setShowPreviewModal(false);
      setTourStep(3);
    } else if (tourStep === 5) {
      setShowPreviewModal(false);
      setTourStep(4);
    } else if (tourStep === 6) {
      setTourStep(5);
    } else if (tourStep === 7) {
      setCurrentPage("settings");
      setSettingsActiveTab("branding");
      setTourStep(6);
    } else if (tourStep === 8) {
      setTourStep(7);
    } else if (tourStep === 9) {
      setCurrentPage("home");
      setTourStep(8);
    } else if (tourStep === 10) {
      setTourStep(9);
    } else if (tourStep === 11) {
      setTourStep(10);
    } else if (tourStep === 12) {
      setTourStep(11);
    } else if (tourStep === 13) {
      setIsArchModalOpen(false);
      if (!isCorporateUser(email)) {
        setTourStep(11);
      } else {
        setTourStep(12);
      }
    } else if (tourStep === 14) {
      setCurrentPage("chat");
      setTourStep(13);
    } else if (tourStep === 17) {
      if (conversations.length === 0) {
        setTourStep(15);
      } else {
        setTourStep(16);
      }
    } else if (tourStep >= 15 && tourStep <= 20) {
      setTourStep(tourStep - 1);
    }
  };

  const handleSkipTour = () => {
    setIsArchModalOpen(false);
    setTourStep(0);
    sessionStorage.setItem("ca_visited_tour", "true");
  };

  // Close schema drawer when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const drawer = document.getElementById("schema-drawer-container");
      const toggleBtn = document.getElementById("toggle-schema-btn");
      if (
        isSchemaExpanded &&
        drawer &&
        !drawer.contains(event.target as Node) &&
        toggleBtn &&
        !toggleBtn.contains(event.target as Node)
      ) {
        setIsSchemaExpanded(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isSchemaExpanded]);


  const handleAgentChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    setSelectedAgent(val);
    sessionStorage.setItem("activeAgentName", val);
    setSelectedConvo("");
    setMessages([]);
    fetchConversations(val);
    fetchAgentSchema(val);
    setIsSidebarOpen(false);
    setIsSchemaExpanded(false);
    if (tourStep === 14) {
      setTourStep(15);
    }
  };

  const handleConvoClick = (convoName: string) => {
    setSelectedConvo(convoName);
    fetchMessages(convoName);
    setIsSidebarOpen(false);
  };

  const handleDeleteConvo = async (e: React.MouseEvent, convoName: string) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this conversation?")) return;

    setDeletingConvoName(convoName);
    try {
      const res = await authenticatedFetch(`/api/conversations/${encodeURIComponent(convoName)}`, {
        method: "DELETE"
      });
      if (res.ok) {
        if (selectedConvo === convoName) {
          const remaining = conversations.filter(c => c.name !== convoName);
          if (remaining.length > 0) {
            setSelectedConvo(remaining[0].name);
            fetchMessages(remaining[0].name);
          } else {
            setSelectedConvo("");
            setMessages([]);
          }
        }
        if (selectedAgent) {
          await fetchConversations(selectedAgent, undefined, true);
        }
      } else {
        alert("Failed to delete conversation.");
      }
    } catch (e) {
      console.error(e);
      alert("Failed to delete conversation.");
    } finally {
      setDeletingConvoName(null);
    }
  };

  const handleStartNewConvo = async () => {
    if (!selectedAgent) return;
    setIsCreatingConvo(true);
    setIsSidebarOpen(false);
    try {
      const res = await authenticatedFetch("/api/conversations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_name: selectedAgent })
      });
      if (res.ok) {
        const newConvo = await res.json();
        setSelectedConvo(newConvo.name);
        setMessages([]);
        await fetchConversations(selectedAgent, newConvo.name, true);
        if (tourStep === 16) {
          setTourStep(17);
        }
      }
    } catch (e) {
      console.error(e);
      alert("Failed to start a new conversation.");
    } finally {
      setIsCreatingConvo(false);
    }
  };

  // Send message & stream parser
  const handleSendMessage = async (overrideText?: unknown) => {
    const text = (typeof overrideText === "string" ? overrideText : inputText).trim();
    if (!text || !selectedAgent) return;

    if (tourStep === 18) {
      setTourStep(19);
    }

    setInputText("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    // Add user bubble immediately
    setMessages(prev => [...prev, { userMessage: { text } }]);
    setIsQuerying(true);
    setConnectionStatus("loading");
    setStreamingMessages([]);

    let activeConvo = selectedConvo;

    // Automatically spin up a new conversation if none is selected
    if (!activeConvo) {
      try {
        const res = await authenticatedFetch("/api/conversations", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ agent_name: selectedAgent })
        });
        if (res.ok) {
          const newConvo = await res.json();
          activeConvo = newConvo.name;
          setSelectedConvo(newConvo.name);
          await fetchConversations(selectedAgent, newConvo.name, true);
        } else {
          throw new Error("Failed to spin up a new conversation");
        }
      } catch (e) {
        console.error(e);
        alert("Failed to start a new conversation. Please try again.");
        setIsQuerying(false);
        setConnectionStatus("online");
        setMessages(prev => prev.slice(0, -1)); // Remove the added user bubble
        setInputText(text); // Restore the input text
        return;
      }
    }

    try {
      const response = await authenticatedFetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_name: activeConvo,
          agent_name: selectedAgent,
          message_text: text,
          chat_mode: chatMode // Send reasoning mode (fast vs thinking)
        })
      });

      if (!response.ok) throw new Error("Chat stream error");

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      const receivedMessages: any[] = [];

      let buffer = "";
      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith("data: ")) {
              const dataStr = trimmed.slice(6).trim();
              if (dataStr === "[DONE]") break;

              try {
                const payload = JSON.parse(dataStr);
                if (payload.systemMessage) {
                  receivedMessages.push(payload.systemMessage);
                  setStreamingMessages([...receivedMessages]);
                }
              } catch (e) {
                // Ignore parsing errors on fragmented SSE lines
              }
            }
          }
        }
      }

      // Once streaming finishes, commit the full message to the main message array
      const groupedStreaming = groupConversationalMessages(
        receivedMessages.map(m => ({ systemMessage: m }))
      );
      if (groupedStreaming.length > 0) {
        setMessages(prev => [...prev, ...groupedStreaming]);
      }
      setStreamingMessages([]);

    } catch (err) {
      console.error(err);
      setMessages(prev => [
        ...prev,
        { systemMessage: { text: { parts: ["An error occurred trying to connect to the Conversational Analytics API. Please verify you are authenticated."] } } }
      ]);
    } finally {
      setIsQuerying(false);
      setConnectionStatus("online");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleInputResize = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  };

  // Test connection function
  const handleTestConnection = async () => {
    setSettingsTestResult("Testing connection...");
    setSettingsTestSuccess(null);
    
    try {
      // Explicitly pass the X-GCP-Project-Id header to test the currently previewed project in the dropdown
      const res = await authenticatedFetch("/api/agents", {
        headers: {
          "X-GCP-Project-Id": settingsProjectId
        }
      });
      
      if (res.ok) {
        const data = await res.json();
        setSettingsTestResult(`Success! Connected to GCP. Loaded ${data.length} agent(s).`);
        setSettingsTestSuccess(true);
      } else {
        let errMsg = "GCP API call returned failure";
        try {
          const errData = await res.json();
          if (errData && errData.detail) {
            errMsg = errData.detail;
          }
        } catch {}
        throw new Error(errMsg);
      }
    } catch (e: any) {
      setSettingsTestResult(`Connection failed: ${e.message}`);
      setSettingsTestSuccess(false);
    }
  };

  // Save general configuration (Default GCP Project ID)
  const handleSaveGeneralConfig = async () => {
    if (!branding) return;
    setSettingsSaveResult("Saving...");
    
    const updated = {
      ...branding,
      brands: {
        ...branding.brands,
        [activeBrandKey]: {
          ...branding.brands[activeBrandKey],
          gcpProjectId: settingsProjectId,
          gcpLocation: settingsLocation
        }
      }
    };

    try {
      const res = await authenticatedFetch("/api/branding", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updated)
      });

      if (res.ok) {
        setBranding(updated);
        setSettingsSaveResult("Connection settings saved successfully!");
        
        // Instantly sync and switch the active workspace to this project!
        handleProjectChange(settingsProjectId);
        
        // Also reload the projects list to reflect the new default option
        await fetchGcpProjects();
        
        setTimeout(() => setSettingsSaveResult(""), 3000);
      } else {
        throw new Error("API call returned failure");
      }
    } catch (e: any) {
      setSettingsSaveResult(`Error saving settings: ${e.message}`);
    }
  };

  // Save branding settings
  const handleSaveBranding = async () => {
    if (!branding) return;
    setSettingsSaveResult("Saving...");
    
    const updated = {
      ...branding,
      activeBrand: activeBrandKey,
      brands: {
        ...branding.brands,
        [activeBrandKey]: {
          name: brandName,
          primaryColor: brandPrimary,
          secondaryColor: brandSecondary,
          backgroundColorStart: brandBgStart,
          backgroundColorEnd: brandBgEnd,
          welcomeMessage: brandWelcome,
          logoUrl: "",
          logoText: brandLogoText,
          logoSvg: brandLogoSvg
        }
      }
    };

    try {
      const res = await authenticatedFetch("/api/branding", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updated)
      });

      if (res.ok) {
        setBranding(updated);
        setAppActiveBrandKey(activeBrandKey);
        localStorage.setItem("ca_active_brand", activeBrandKey);
        applyBrandingCSS(updated.brands[activeBrandKey]);
        setSettingsSaveResult("Branding settings saved successfully!");
        setTimeout(() => setSettingsSaveResult(""), 3000);
      } else {
        throw new Error("API call returned failure");
      }
    } catch (e: any) {
      setSettingsSaveResult(`Error saving settings: ${e.message}`);
    }
  };
 
  const handleLogoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsGeneratingFromLogo(true);
    setLogoSearchError("");

    const processUpload = async (svgContent: string | null, base64Image: string | null, mimeType: string | null, fileName: string) => {
      try {
        const promptText = fileName.replace(/\.[^/.]+$/, "") || brandName || "Custom Brand";
        const res = await authenticatedFetch("/api/branding/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            prompt: promptText,
            logo_image: base64Image,
            logo_mime_type: mimeType,
            logo_svg_content: svgContent
          })
        });

        if (res.ok) {
          const data = await res.json();
          const rawName = data.name || promptText;
          const finalName = rawName
            .replace(/^(speculative:\s*|domain:\s*)/i, "")
            .replace(/\.(com|org|net|co|io|edu|gov)$/i, "")
            .split(/[\s_-]+/)
            .map((word: string) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
            .join(" ");
          const brandKey = finalName.toLowerCase().trim().replace(/[^a-z0-9]+/g, "_");

          let finalLogoSvg = "";
          if (data.logoSvg && data.logoSvg.includes("<svg") && !data.logoSvg.includes("polygon points='12 2")) {
            finalLogoSvg = data.logoSvg;
          } else if (base64Image) {
            finalLogoSvg = `<img src="data:${mimeType};base64,${base64Image}" alt="${finalName}" class="w-full h-full object-contain" />`;
          } else if (svgContent) {
            finalLogoSvg = svgContent;
          }

          const rawLogoText = data.logoText || finalName;
          const finalLogoText = rawLogoText
            .replace(/^(speculative:\s*|domain:\s*)/i, "")
            .replace(/\.(com|org|net|co|io|edu|gov)$/i, "")
            .toUpperCase();

          setBrandName(finalName);
          if (data.primaryColor) setBrandPrimary(data.primaryColor);
          if (data.secondaryColor) setBrandSecondary(data.secondaryColor);
          if (data.backgroundColorStart) setBrandBgStart(data.backgroundColorStart);
          if (data.backgroundColorEnd) setBrandBgEnd(data.backgroundColorEnd);
          setBrandLogoText(finalLogoText);
          if (data.welcomeMessage) setBrandWelcome(data.welcomeMessage);
          setBrandLogoSvg(finalLogoSvg);
          setActiveBrandKey(brandKey);
        } else {
          const errText = await res.text().catch(() => "");
          setLogoSearchError(`Logo analysis failed (Status ${res.status}: ${errText || res.statusText}).`);
        }
      } catch (err: any) {
        setLogoSearchError(err.message || "An error occurred during custom logo theme generation.");
      } finally {
        setIsGeneratingFromLogo(false);
      }
    };

    try {
      const reader = new FileReader();
      if (file.type === "image/svg+xml") {
        reader.onload = async (event) => {
          const text = event.target?.result as string;
          await processUpload(text, null, null, file.name);
        };
        reader.readAsText(file);
      } else {
        reader.onload = async (event) => {
          const dataUrl = event.target?.result as string;
          const base64Data = dataUrl.split(",")[1];
          await processUpload(null, base64Data, file.type, file.name);
        };
        reader.readAsDataURL(file);
      }
    } catch (err: any) {
      setLogoSearchError(err.message || "Failed to read file.");
      setIsGeneratingFromLogo(false);
    } finally {
      if (logoFileInputRef.current) {
        logoFileInputRef.current.value = "";
      }
    }
  };

  const handleSearchLogo = async () => {
    if (!logoSearchQuery.trim()) return;
    setIsSearchingLogo(true);
    setLogoSearchError("");
    try {
      const res = await authenticatedFetch(`/api/branding/search-logo?query=${encodeURIComponent(logoSearchQuery)}`);
      if (res.ok) {
        const data = await res.json();
        setLogoSearchResults(data);
      } else {
        const errText = await res.text().catch(() => "");
        setLogoSearchError(`Failed to fetch search results (Status ${res.status}: ${errText || res.statusText}).`);
      }
    } catch (e: any) {
      setLogoSearchError(e.message || "An error occurred during search.");
    } finally {
      setIsSearchingLogo(false);
    }
  };

  const handleSelectSearchLogo = async (logoUrl: string, logoTitle: string) => {
    setIsGeneratingFromLogo(true);
    setLogoSearchError("");
    try {
      const res = await authenticatedFetch("/api/branding/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: logoTitle || logoSearchQuery || brandName || "Custom Brand",
          logo_url: logoUrl
        })
      });
      if (res.ok) {
        const data = await res.json();
        const rawName = data.name || logoTitle || "Custom Brand";
        const finalName = rawName
          .replace(/^(speculative:\s*|domain:\s*)/i, "")
          .replace(/\.(com|org|net|co|io|edu|gov)$/i, "")
          .split(/[\s_-]+/)
          .map((word: string) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
          .join(" ");
        const brandKey = finalName.toLowerCase().trim().replace(/[^a-z0-9]+/g, "_");

        let finalLogoSvg = "";
        if (data.logoSvg && data.logoSvg.includes("<svg") && !data.logoSvg.includes("polygon points='12 2")) {
          finalLogoSvg = data.logoSvg;
        } else {
          finalLogoSvg = `<img src="${logoUrl}" alt="${logoTitle}" class="w-full h-full object-contain" />`;
        }

        const rawLogoText = data.logoText || finalName;
        const finalLogoText = rawLogoText
          .replace(/^(speculative:\s*|domain:\s*)/i, "")
          .replace(/\.(com|org|net|co|io|edu|gov)$/i, "")
          .toUpperCase();

        // Set editing form inputs
        setBrandName(finalName);
        if (data.primaryColor) setBrandPrimary(data.primaryColor);
        if (data.secondaryColor) setBrandSecondary(data.secondaryColor);
        if (data.backgroundColorStart) setBrandBgStart(data.backgroundColorStart);
        if (data.backgroundColorEnd) setBrandBgEnd(data.backgroundColorEnd);
        setBrandLogoText(finalLogoText);
        if (data.welcomeMessage) setBrandWelcome(data.welcomeMessage);
        setBrandLogoSvg(finalLogoSvg);

        // Set active profile key so saving will save under this brand key
        setActiveBrandKey(brandKey);
      } else {
        setLogoSearchError("Failed to generate theme from selected logo.");
      }
    } catch (e: any) {
      setLogoSearchError(e.message || "An error occurred while generating the theme.");
    } finally {
      setIsGeneratingFromLogo(false);
    }
  };

  const handleDeleteBrand = async () => {
    if (!branding) return;
    if (activeBrandKey === "default") {
      alert("The default Google Cloud theme cannot be deleted.");
      return;
    }

    if (!window.confirm(`Are you sure you want to delete the theme "${branding.brands[activeBrandKey]?.name}"?`)) {
      return;
    }

    const updatedBrands = { ...branding.brands };
    delete updatedBrands[activeBrandKey];

    const updated: BrandingData = {
      activeBrand: "default",
      brands: updatedBrands
    };

    try {
      const res = await authenticatedFetch("/api/branding", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updated)
      });

      if (res.ok) {
        setBranding(updated);
        setActiveBrandKey("default");
        setAppActiveBrandKey("default");
        localStorage.setItem("ca_active_brand", "default");
        const defaultBrand = updated.brands["default"];
        setBrandName(defaultBrand.name);
        setBrandPrimary(defaultBrand.primaryColor);
        setBrandSecondary(defaultBrand.secondaryColor);
        setBrandBgStart(defaultBrand.backgroundColorStart);
        setBrandBgEnd(defaultBrand.backgroundColorEnd);
        setBrandLogoText(defaultBrand.logoText);
        setBrandWelcome(defaultBrand.welcomeMessage);
        setBrandLogoSvg(defaultBrand.logoSvg || "");
        applyBrandingCSS(defaultBrand);

        setSettingsSaveResult("Theme deleted successfully!");
        setTimeout(() => setSettingsSaveResult(""), 3000);
      } else {
        throw new Error("API call returned failure");
      }
    } catch (e: any) {
      setSettingsSaveResult(`Error deleting theme: ${e.message}`);
    }
  };





  const activeBrand = branding?.brands[appActiveBrandKey] || branding?.brands["default"];


  // Structured Item Renderers (React equivalents)
  const SchemaWidget: React.FC<{ schema: any }> = ({ schema }) => {
    const [open, setOpen] = useState(false);
    if (!schema?.result?.datasources) return null;

    return (
      <>
        {schema.result.datasources.map((ds: any, idx: number) => {
          const dsName = ds.bigqueryTableReference ? 
            `${ds.bigqueryTableReference.projectId}.${ds.bigqueryTableReference.datasetId}.${ds.bigqueryTableReference.tableId}` : 
            (ds.studioDatasourceId || "Data Source");
          
          return (
            <div key={idx} className="mt-4 bg-slate-950/50 border border-white/6 rounded-lg overflow-hidden">
              <div 
                className="px-4 py-2 bg-white/2 border-b border-white/6 font-semibold text-xs text-slate-400 flex justify-between items-center cursor-pointer select-none"
                onClick={() => setOpen(!open)}
              >
                <span>Schema: {dsName}</span>
                <span>{open ? "▲" : "▼"}</span>
              </div>
              {open && (
                <div className="max-h-52 overflow-y-auto p-2">
                  <table className="w-full border-collapse text-xs text-left">
                    <thead>
                      <tr className="text-slate-400 font-medium border-b border-white/6">
                        <th className="p-2">Field</th>
                        <th className="p-2">Type</th>
                        <th className="p-2">Mode</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ds.schema?.fields?.map((f: any, fidx: number) => (
                        <tr key={fidx} className="border-b border-white/2">
                          <td className="p-2 font-semibold">{f.name}</td>
                          <td className="p-2">{f.type}</td>
                          <td className="p-2">{f.mode || "NULLABLE"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          );
        })}
      </>
    );
  };

  

  if (authLoading) {
    return (
      <div className="flex min-h-screen w-full flex-col items-center justify-center bg-[#070913] text-white">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-10 w-10 animate-spin text-indigo-500" />
          <p className="text-sm font-medium text-slate-400">Verifying session...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="relative flex min-h-screen w-full items-center justify-center bg-gradient-to-br from-[#070913] via-[#0b0f19] to-[#05060c] px-4 overflow-hidden">
        {/* Animated ambient background lights */}
        <div className="absolute top-1/4 left-1/4 w-[500px] h-[500px] rounded-full bg-indigo-500/10 blur-[120px] animate-pulse pointer-events-none" />
        <div className="absolute bottom-1/4 right-1/4 w-[500px] h-[500px] rounded-full bg-violet-600/10 blur-[120px] animate-pulse pointer-events-none" style={{ animationDelay: "2s" }} />
        
        {/* Login Card */}
        <div className="relative w-full max-w-[440px] bg-slate-900/40 backdrop-blur-xl border border-white/6 rounded-2xl p-8 shadow-2xl flex flex-col gap-6 text-center transition-all duration-300 hover:border-white/10">
          {/* Header Logo */}
          <div className="flex flex-col items-center gap-3">
            <div className="w-16 h-16 rounded-2xl bg-slate-950/40 border border-white/6 flex items-center justify-center p-3 shadow-lg shadow-black/30">
              <img src="/google_cloud_logo.svg" className="w-full h-full object-contain" alt="Google Cloud Logo" />
            </div>
            <h1 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-200 to-slate-400 tracking-tight mt-2">
              Google Cloud Agent Hub
            </h1>
            <p className="text-[10px] font-semibold text-indigo-400 tracking-widest uppercase mt-0.5">
              Enterprise Agentic Workspace
            </p>
          </div>

          <div className="h-[1px] w-full bg-gradient-to-r from-transparent via-white/10 to-transparent" />

          {/* Welcoming Text */}
          <div className="flex flex-col gap-2">
            <p className="text-sm text-slate-300 leading-relaxed">
              Welcome to your collaborative conversational analytics workspace. Sign in to analyze databases, view dashboards, and generate insights.
            </p>
          </div>

          <p className="text-xs text-slate-400">
            {import.meta.env.VITE_RESTRICT_TO_GOOGLE !== "false" ? (
              <>
                Sign in using your <strong className="text-slate-300 font-semibold">Google</strong> or <strong className="text-slate-300 font-semibold">Argolis</strong> account.
              </>
            ) : (
              <>
                Sign in using your <strong className="text-slate-300 font-semibold">Gmail</strong> account.
              </>
            )}
          </p>

          {/* Google Sign In Button */}
          <button
            onClick={handleLogin}
            className="w-full flex items-center justify-center gap-3 py-3.5 px-4 bg-white hover:bg-slate-50 text-slate-900 font-semibold rounded-xl border border-slate-200 shadow-md hover:shadow-lg hover:scale-[1.02] active:scale-[0.98] transition-all duration-300 cursor-pointer text-sm"
          >
            <img src="/google_logo.svg" className="h-5 w-5 object-contain" alt="Google Logo" />
            Sign in with Google
          </button>
          
          {authError && (
            <div className="p-3 bg-red-950/30 border border-red-500/20 rounded-xl text-xs text-red-400 font-medium animate-pulse">
              {authError}
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen w-screen bg-slate-950 text-slate-100 overflow-hidden font-sans">
      
      {/* Global Header Banner */}
      {user && (
        <header className={`h-16 bg-slate-950/80 backdrop-blur-md border-b border-white/6 px-4 md:px-8 flex items-center justify-between shrink-0 select-none animate-fadeIn ${tourStep > 0 ? 'z-[1010]' : 'z-40'}`}>
          {/* Left: Hamburger Button (mobile chat only) & Logo/Title (Click to go Home) */}
          <div className="flex items-center gap-3 min-w-0">
            {currentPage === "chat" && (
              <button
                onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                className="p-2 -ml-1 bg-white/4 border border-white/6 hover:bg-white/10 rounded-lg text-slate-300 hover:text-white md:hidden cursor-pointer flex items-center justify-center shrink-0"
                title="Toggle Sidebar"
              >
                <Menu size={16} />
              </button>
            )}
            <div 
              id="settings-back-home"
              onClick={() => {
                trackClick("logo_home_link");
                if (currentPage !== "home") {
                  setCurrentPage("home");

                }
                if (tourStep > 0) {
                  if (tourStep === 6) {
                    setTourStep(7);
                  } else {
                    setTourStep(0);
                    sessionStorage.setItem("ca_visited_tour", "true");
                  }
                }
              }}
              className={`flex items-center gap-3 min-w-0 cursor-pointer hover:opacity-90 active:scale-[0.98] transition select-none group ${tourStep === 6 ? 'tour-highlight p-1 rounded-xl' : ''}`}
              title="Return to Dashboard"
            >
              <div className="w-8 h-8 rounded-lg bg-white/5 border border-white/6 flex items-center justify-center p-1 text-white shrink-0 group-hover:border-brand-primary/30 group-hover:bg-brand-primary/5 transition">
                {renderLogoSvg(appActiveBrandKey)}
              </div>
              <span className="font-heading font-bold text-md tracking-tight truncate min-w-0 hidden sm:inline group-hover:text-brand-primary transition">
                {activeBrand?.logoText || "Google Cloud Analytics"}
              </span>
            </div>
          </div>

          {/* Right: Contextual Tools, GCP Connection Selector, Session User, Settings, Sign Out */}
          <div className="flex items-center gap-4 shrink-0">
            
            {/* Show Architecture Button (Desktop Only) */}
            {currentPage === "chat" && (
              <button 
                id="arch-diagram-btn"
                onClick={handleOpenArchitecture}
                className={`hidden md:flex items-center gap-2 text-xs font-semibold text-brand-primary bg-brand-primary/10 border border-brand-primary/20 px-3 py-2 rounded-xl hover:bg-brand-primary hover:text-white transition duration-200 cursor-pointer shrink-0 animate-slideIn ${tourStep === 13 ? 'tour-highlight' : ''}`}
              >
                <Network size={12} />
                <span className="hidden md:inline">Show Architecture</span>
              </button>
            )}

            {/* Interactive Connection & Identity Selector */}
            <div id="project-override-container" className={`relative ${tourStep === 12 ? 'tour-highlight' : ''}`} ref={connDropdownRef}>
              {!isCorporateUser(user?.email || auth.currentUser?.email || null) ? (
                <div className="flex items-center gap-2 text-[10px] text-slate-300 bg-white/4 border border-white/6 px-3.5 py-1.5 rounded-full select-none font-semibold transition whitespace-nowrap">
                  <span className={`w-2 h-2 rounded-full ${
                    connectionStatus === "error" ? "bg-rose-500 shadow-[0_0_8px_#ef4444]" : "bg-emerald-500 shadow-[0_0_8px_#10b981]"
                  }`} />
                  <span>
                    {connectionStatus === "error" ? "Connection Error" : "GCP: Online"}
                  </span>
                </div>
              ) : (
                <>
                  <button 
                    onClick={() => setShowConnDropdown(!showConnDropdown)}
                    className="flex items-center gap-2 text-[10px] text-slate-300 bg-white/4 hover:bg-white/6 border border-white/6 px-3.5 py-1.5 rounded-full cursor-pointer select-none font-semibold transition whitespace-nowrap"
                  >
                    <span className={`w-2 h-2 rounded-full ${
                      connectionStatus === "error" ? "bg-rose-500 shadow-[0_0_8px_#ef4444]" : "bg-emerald-500 shadow-[0_0_8px_#10b981]"
                    }`} />
                    <span>
                      <span className="hidden sm:inline">
                        {connectionStatus === "error" ? "Connection Error" : (credentialsMode === "service_account" ? "GCP: Service Account" : "GCP: SSO User")}
                      </span>
                      <span className="inline sm:hidden">
                        {connectionStatus === "error" ? "Error" : (credentialsMode === "service_account" ? "SA" : "SSO")}
                      </span>
                    </span>
                    <ChevronDown size={10} className="text-slate-400" />
                  </button>
                  
                  {showConnDropdown && (
                    <div className={`absolute top-full right-0 mt-2 w-64 bg-slate-950/95 border border-white/8 rounded-xl shadow-xl overflow-hidden backdrop-blur-md animate-slideDown flex flex-col ${tourStep > 0 ? 'z-[2000]' : 'z-50'}`}>
                      <div className="px-3 py-2 bg-white/3 border-b border-white/6 text-[9px] font-bold uppercase tracking-wider text-slate-400 select-none text-left">
                        Active Identity
                      </div>
                      <button
                        onClick={() => {
                          handleCredentialsModeChange("service_account");
                        }}
                        className={`w-full px-4 py-2.5 text-left hover:bg-white/4 transition text-xs font-semibold text-slate-200 cursor-pointer border-none bg-transparent flex items-center justify-between ${credentialsMode === "service_account" ? "bg-white/2 text-white font-bold" : ""}`}
                      >
                        <span>💼 Service Account (ADC)</span>
                        {credentialsMode === "service_account" && <span className="text-brand-primary text-[10px]">✓</span>}
                      </button>
                      {isCorporateUser(user?.email || auth.currentUser?.email || null) && (
                        <button
                          onClick={() => {
                            handleCredentialsModeChange("user_sso");
                          }}
                          className={`w-full px-4 py-2.5 text-left hover:bg-white/4 transition text-xs font-semibold text-slate-200 cursor-pointer border-none bg-transparent flex items-center justify-between ${credentialsMode === "user_sso" ? "bg-white/2 text-white font-bold" : ""}`}
                        >
                          <span>👤 SSO User Session</span>
                          {credentialsMode === "user_sso" && <span className="text-brand-primary text-[10px]">✓</span>}
                        </button>
                      )}

                      {credentialsMode === "user_sso" && (
                        <>
                          <div className="px-3 py-2 bg-white/3 border-t border-b border-white/6 text-[9px] font-bold uppercase tracking-wider text-slate-400 select-none text-left mt-1">
                            Target GCP Project
                          </div>
                          <div className="p-3 flex flex-col gap-2">
                            {gcpProjects.length === 0 ? (
                              <div className="text-[10px] text-slate-500 italic text-center py-2">
                                No projects loaded
                              </div>
                            ) : (
                              <div className="relative">
                                <select
                                  value={selectedProject}
                                  onChange={(e) => handleProjectChange(e.target.value)}
                                  className="w-full py-2 px-3 bg-slate-950 border border-white/8 rounded-lg text-xs text-slate-200 focus:border-brand-primary outline-none cursor-pointer appearance-none"
                                >
                                  {gcpProjects.map((p) => (
                                    <option key={p.projectId} value={p.projectId}>
                                      {p.name}
                                    </option>
                                  ))}
                                </select>
                                <ChevronDown className="absolute right-3 top-2.5 text-slate-400 pointer-events-none" size={12} />
                              </div>
                            )}
                          </div>
                        </>
                      )}

                      <div className="px-3 py-2 bg-white/3 border-t border-b border-white/6 text-[9px] font-bold uppercase tracking-wider text-slate-400 select-none text-left mt-1">
                        GCP Location (Region)
                      </div>
                      <div className="p-3 flex flex-col gap-2">
                        <div className="relative">
                          <select 
                            value={settingsLocation} 
                            onChange={(e) => {
                              const val = e.target.value;
                              setSettingsLocation(val);
                              handleLocationChange(val);
                            }}
                            className="w-full py-2 px-3 bg-slate-950 border border-white/8 rounded-lg text-xs text-slate-200 focus:border-brand-primary outline-none cursor-pointer appearance-none"
                          >
                            <option value="all">All Common Regions (Scan All)</option>
                            <option value="global">Global (Default)</option>
                            <option value="us-central1">us-central1 (Iowa)</option>
                            <option value="europe-west1">europe-west1 (Belgium)</option>
                            <option value="us">us (US Multi-region)</option>
                            <option value="eu">eu (EU Multi-region)</option>
                          </select>
                          <ChevronDown className="absolute right-3 top-2.5 text-slate-400 pointer-events-none" size={12} />
                        </div>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>

            <div className="w-px h-5 bg-white/10" />

            {/* User Profile Block */}
            {user.email && (
              <>
                <div className="text-right hidden sm:block">
                  <div className="text-xs font-semibold text-slate-300">{user.email}</div>
                  <div className="text-[8px] text-slate-500 font-bold uppercase tracking-wider">Authorized Session</div>
                </div>
                {/* Mobile User Avatar Circle */}
                <div 
                  className="flex sm:hidden w-8 h-8 rounded-full bg-brand-primary/15 border border-brand-primary/30 items-center justify-center text-xs font-bold text-brand-primary cursor-pointer select-none active:scale-95 transition"
                  title={`Logged in as: ${user.email}`}
                  onClick={() => alert(`Logged in as: ${user.email}`)}
                >
                  {user.email[0].toUpperCase()}
                </div>
              </>
            )}

            {/* Mobile-only New Chat Button (visible only in chat workspace on mobile) */}
            {currentPage === "chat" && (
              <button 
                id="mobile-new-chat-btn"
                onClick={() => {
                  setSelectedConvo("");
                  setMessages([]);
                  setIsSidebarOpen(false);
                }}
                className="py-1.5 px-3 bg-brand-primary/10 border border-brand-primary/20 hover:bg-brand-primary/20 rounded-lg text-brand-primary transition duration-150 cursor-pointer flex md:hidden items-center justify-center gap-1 font-semibold text-xs mr-1"
                title="Start New Chat"
              >
                <Plus size={13} />
                <span>New Chat</span>
              </button>
            )}

            {/* Settings Gear Button */}
            <button 
              id="settings-gear-btn"
              onClick={() => {
                trackClick("settings_gear");
                setCurrentPage("settings");
                const email = user?.email || auth.currentUser?.email || null;
                if (!isCorporateUser(email)) {
                  setSettingsActiveTab("branding");
                } else {
                  setSettingsActiveTab("general");
                }
                if (tourStep === 1) {
                  if (!isCorporateUser(email)) {
                    setTourStep(3);
                  } else {
                    setTourStep(2);
                  }
                }
              }}
              className={`p-2 bg-white/4 border border-white/6 hover:bg-brand-primary/10 hover:border-brand-primary/25 rounded-lg text-slate-300 hover:text-brand-primary transition duration-150 cursor-pointer flex items-center justify-center group ${(currentPage === "settings" && tourStep === 0) ? "bg-brand-primary/15 border-brand-primary/30 text-brand-primary" : ""} ${tourStep === 1 ? 'tour-highlight' : ''}`}
              title="Configure Portal Settings"
            >
              <Settings size={15} className="group-hover:rotate-45 transition-transform duration-300" />
            </button>

            {/* Sign Out Button (Desktop Only) */}
            <button 
              onClick={handleSignOut}
              className="p-2 bg-white/4 border border-white/6 hover:bg-rose-500/10 hover:border-rose-500/25 rounded-lg text-slate-400 hover:text-rose-400 transition duration-150 cursor-pointer hidden md:flex items-center justify-center"
              title="Sign Out"
            >
              <LogOut size={15} />
            </button>
          </div>
        </header>
      )}

      {/* Main Viewport Split Panel */}
      <div className="flex-1 flex min-h-0 overflow-hidden relative">
      
      {/* Backdrop overlay for mobile sidebar */}
      {currentPage === "chat" && isSidebarOpen && (
        <div 
          className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm z-40 md:hidden"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* -------------------- SIDEBAR -------------------- */}
      {currentPage === "chat" && (
        <aside className={`w-80 border-r border-white/6 bg-slate-900/45 backdrop-blur-md flex flex-col p-6 z-50 transition-transform duration-300 fixed md:static inset-y-0 left-0 h-full md:h-auto md:translate-x-0 ${isSidebarOpen ? "translate-x-0" : "-translate-x-full"}`}>
          {/* Back to Dashboard Button */}
          <button 
            onClick={() => {
              setIsSidebarOpen(false);
              setCurrentPage("home");
            }}
            className="flex items-center gap-2 text-xs font-bold text-slate-400 hover:text-brand-primary mb-6 transition cursor-pointer self-start border-none bg-transparent"
            title="Return to main dashboard"
          >
            <ArrowLeft size={14} />
            <span>Back to Dashboard</span>
          </button>

          <div className="flex justify-between items-center mb-8">
            <div className="font-heading text-2xl font-bold tracking-tight bg-gradient-to-r from-white to-white/70 bg-clip-text text-transparent">
              Data Workspace
            </div>
            <button
              onClick={() => setIsSidebarOpen(false)}
              className="p-1.5 bg-white/4 border border-white/6 hover:bg-white/10 rounded-lg text-slate-300 hover:text-white md:hidden cursor-pointer flex items-center justify-center shrink-0"
              title="Close Sidebar"
            >
              <X size={14} />
            </button>
          </div>
          
          <div className="mb-7 flex flex-col">
            <label className="text-[10px] uppercase font-bold tracking-wider text-slate-400 mb-2">Active Data Agent</label>
            <div className={`relative ${tourStep === 9 || tourStep === 14 ? 'tour-highlight rounded-xl' : ''}`} id="agent-select-container">
              <select 
                value={selectedAgent}
                onChange={handleAgentChange}
                className="w-full py-3 px-4 bg-slate-950/40 border border-white/6 rounded-xl text-sm text-slate-200 focus:border-brand-primary outline-none cursor-pointer appearance-none"
              >
                <option value="" disabled>Select a data agent</option>
                {agents.map((a, idx) => (
                  <option key={idx} value={a.name}>
                    {a.displayName || a.name.split("/").pop()}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-4 top-3.5 text-slate-400 pointer-events-none" size={16} />
            </div>
          </div>

          <div 
            id="conversations-panel-container"
            className={`flex flex-col flex-1 min-h-0 ${tourStep === 10 ? 'tour-highlight p-2 rounded-xl border border-white/6 bg-white/1' : ''}`}
          >
            <div className="flex justify-between items-center mb-3">
              <span className="text-[10px] uppercase font-bold tracking-wider text-slate-400">Conversations</span>
              <button 
                id="new-convo-btn"
                onClick={handleStartNewConvo}
                disabled={!selectedAgent || isCreatingConvo}
                className={`bg-white/5 border border-white/6 hover:bg-brand-primary hover:border-brand-primary text-white w-6 h-6 rounded-md cursor-pointer flex items-center justify-center text-md transition duration-200 disabled:opacity-50 disabled:cursor-not-allowed ${tourStep === 16 ? 'tour-highlight scale-110 shadow-lg border-brand-primary/50' : ''}`}
                title="Start new conversation"
              >
                {isCreatingConvo ? (
                  <Loader2 size={12} className="animate-spin text-white" />
                ) : (
                  <Plus size={14} />
                )}
              </button>
            </div>

            <div className="flex-1 overflow-y-auto flex flex-col gap-2 pr-1">
              {conversations.length === 0 ? (
                <div className="text-xs text-slate-400 text-center py-4 bg-white/2 border border-white/6 rounded-xl">
                  {selectedAgent ? "No conversations yet." : "Select an agent to load details."}
                </div>
              ) : (
                conversations.map((convo, idx) => {
                  const date = new Date(convo.createTime || convo.lastUsedTime || "");
                  const timeStr = date.toLocaleString([], { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
                  const isActive = selectedConvo === convo.name;
                  const isDeleting = deletingConvoName === convo.name;
                  return (
                    <div 
                      key={idx}
                      onClick={() => !isDeleting && handleConvoClick(convo.name)}
                      className={`p-3 bg-white/2 border border-white/6 rounded-xl text-xs cursor-pointer flex justify-between items-center group transition duration-200 hover:bg-white/7 hover:border-white/15 ${isActive ? "border-l-3 border-l-brand-primary bg-white/7" : ""} ${isDeleting ? "opacity-50 pointer-events-none" : ""}`}
                    >
                      <span className="truncate mr-2">Convo {timeStr}</span>
                      <button
                        onClick={(e) => handleDeleteConvo(e, convo.name)}
                        disabled={isDeleting}
                        className={`text-slate-400 hover:text-rose-500 transition-opacity duration-200 p-1 rounded hover:bg-white/5 cursor-pointer shrink-0 ${isDeleting ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}
                        title="Delete conversation"
                      >
                        {isDeleting ? (
                          <Loader2 size={12} className="animate-spin text-rose-400" />
                        ) : (
                          <Trash2 size={12} />
                        )}
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Mobile-only Sidebar Action Buttons */}
          <div className="mt-auto pt-4 border-t border-white/6 flex flex-col gap-2 md:hidden shrink-0">
            <button 
              id="sidebar-arch-diagram-btn"
              onClick={() => {
                setIsSidebarOpen(false);
                handleOpenArchitecture();
              }}
              className={`w-full flex items-center justify-center gap-2 text-xs font-semibold text-brand-primary bg-brand-primary/10 border border-brand-primary/20 py-2.5 rounded-xl hover:bg-brand-primary hover:text-white transition duration-200 cursor-pointer ${tourStep === 13 ? 'tour-highlight' : ''}`}
            >
              <Network size={13} />
              <span>Show Architecture</span>
            </button>
            
            <button 
              onClick={() => {
                setIsSidebarOpen(false);
                handleSignOut();
              }}
              className="w-full flex items-center justify-center gap-2 text-xs font-semibold text-rose-400 bg-rose-500/10 border border-rose-500/20 py-2.5 rounded-xl hover:bg-rose-500 hover:text-white transition duration-200 cursor-pointer"
            >
              <LogOut size={13} />
              <span>Sign Out</span>
            </button>
          </div>

        </aside>
      )}

      {/* -------------------- MAIN WORKSPACE -------------------- */}
      <main className="flex-1 flex flex-col h-full min-w-0">
        {currentPage === "home" && (
          <Dashboard 
            activeBrand={activeBrand} 
            renderLogoSvg={() => renderLogoSvg(appActiveBrandKey)} 
            onNavigate={(page) => {
              setCurrentPage(page);
              if (page === "chat") {
                setSelectedConvo("");
                setMessages([]);
                if (tourStep === 8) {
                  setTourStep(9);
                }
              }
            }} 
            conversations={conversations}
            onSelectConversation={(convoName) => {
              handleConvoClick(convoName);
              setCurrentPage("chat");
              if (tourStep === 7) {
                setTourStep(9); // Skip Step 8 (Launch Chat) and go directly to Step 9!
              }
            }}
            tourStep={tourStep}
          />
        )}


        {currentPage === "chat" && (
          <>
            {/* Active Chat Header */}
            {(() => {
              const activeAgentObj = agents.find(a => a.name === selectedAgent);
              return (
                <div className="border-b border-white/6 bg-slate-950/20 backdrop-blur-md px-6 md:px-10 py-3 flex items-center justify-between shrink-0 select-none animate-fadeIn">
                  <div className="flex items-center gap-2.5">
                    <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                    <span className="text-xs font-bold text-slate-200 tracking-tight uppercase">
                      {activeAgentObj?.displayName || selectedAgent.split("/").pop() || "Active Session"}
                    </span>
                  </div>
                  
                  {activeAgentObj?.graphData && (
                    <button
                      id="toggle-schema-btn"
                      onClick={() => setIsSchemaExpanded(!isSchemaExpanded)}
                      className={`flex items-center gap-1.5 px-3 py-1.5 bg-white/4 hover:bg-white/8 border border-white/6 rounded-lg text-[10px] font-bold uppercase tracking-wider text-slate-300 transition cursor-pointer border-none ${tourStep === 17 ? 'tour-highlight border-amber-500/50' : ''}`}
                    >
                      <Network size={12} className={isSchemaExpanded ? "text-amber-400 animate-pulse" : "text-slate-400"} />
                      <span>{isSchemaExpanded ? "Hide Schema" : "Show Schema"}</span>
                    </button>
                  )}
                </div>
              );
            })()}
            
            {/* Collapsible Schema Drawer */}
            {(() => {
              const activeAgentObj = agents.find(a => a.name === selectedAgent);
              if (isSchemaExpanded) {
                if (loadingAgentSchema) {
                  return (
                    <div id="schema-drawer-container" className="w-full flex-1 bg-slate-950/40 backdrop-blur-md py-12 px-6 overflow-hidden flex flex-col items-center justify-center min-h-[340px] border-b border-white/6 select-none">
                      <div className="relative w-28 h-28 flex items-center justify-center mb-6">
                        {/* Shimmer glowing background ring */}
                        <div className="absolute inset-0 rounded-full border border-brand-primary/25 bg-brand-primary/5 animate-ping opacity-75" style={{ animationDuration: '2.5s' }} />
                        <div className="absolute inset-4 rounded-full border border-white/10 bg-slate-950/80 backdrop-blur-md flex items-center justify-center shadow-xl shadow-brand-primary/5">
                          {/* Pulsing Central Network Icon */}
                          <Network className="text-brand-primary animate-pulse" size={32} />
                        </div>
                        {/* Small orbiting node dots */}
                        <div className="absolute w-2.5 h-2.5 rounded-full bg-amber-500 animate-bounce" style={{ top: '10%', right: '15%', animationDelay: '0.2s' }} />
                        <div className="absolute w-2.5 h-2.5 rounded-full bg-emerald-400 animate-bounce" style={{ bottom: '15%', left: '10%', animationDelay: '0.4s' }} />
                        <div className="absolute w-2.5 h-2.5 rounded-full bg-indigo-400 animate-bounce" style={{ bottom: '10%', right: '20%', animationDelay: '0.6s' }} />
                      </div>
                      <h3 className="text-sm font-bold text-slate-100 mb-2 tracking-widest uppercase flex items-center gap-2">
                        <Sparkles size={14} className="text-amber-400 animate-pulse" />
                        Constructing Graph Schema
                      </h3>
                      <p className="text-[11px] text-slate-400 text-center max-w-sm leading-relaxed">
                        Scanning BigQuery tables dynamically to resolve entities, properties, and relationships. Building your custom graph blueprint...
                      </p>
                    </div>
                  );
                }
                
                if (activeAgentObj?.graphData) {
                  return (
                    <div id="schema-drawer-container" className="w-full flex-1 bg-slate-950/40 backdrop-blur-md py-4 px-6 overflow-y-auto flex flex-col">
                      <GraphVisualizer
                        graphData={activeAgentObj.graphData}
                        onSelectSuggestion={(question) => {
                          setInputText(question);
                          handleSendMessage(question);
                        }}
                        brandPrimaryColor={brandPrimary}
                        brandLogoSvg={brandLogoSvg}
                        brandLogoText={brandLogoText}
                        agentName={selectedAgent}
                        fetchTablePreview={async (tableName, agentName) => {
                          const queryParams = new URLSearchParams({
                            table_name: tableName,
                            ...(agentName ? { agent_name: agentName } : {})
                          });
                          const res = await authenticatedFetch(`/api/preview?${queryParams.toString()}`);
                          if (!res.ok) throw new Error("Failed to load table data preview");
                          return await res.json();
                        }}
                        isGraphAgent={activeAgentObj.isGraphAgent}
                      />
                    </div>
                  );
                }
              }
              return null;
            })()}

            {/* Messages Panel & Input hidden when schema is expanded */}
            {!isSchemaExpanded && (
              <>
                <section className="flex-1 overflow-y-auto px-4 md:px-10 py-6 md:py-8 flex flex-col gap-6">
              {connectionStatus === "error" ? (
                <div className="flex-1 flex items-center justify-center py-10 animate-slideIn">
                  <div className="glass-panel p-4 sm:p-8 rounded-2xl max-w-xl flex flex-col gap-5 text-center items-center border-rose-500/20 shadow-2xl shadow-rose-500/5">
                    <div className="w-14 h-14 rounded-full bg-rose-500/10 border border-rose-500/25 flex items-center justify-center text-rose-500 shadow-[0_0_15px_rgba(239,68,68,0.1)]">
                      <AlertTriangle size={26} className="animate-pulse" />
                    </div>
                    
                    <div>
                      <h3 className="font-heading font-semibold text-lg text-white mb-2">
                        GCP Connection Offline
                      </h3>
                      <p className="text-slate-400 text-xs leading-relaxed max-w-md">
                        We encountered a permission or configuration error while attempting to connect to the Conversational Analytics API in project <span className="font-bold text-slate-300">{selectedProject || "Default"}</span>.
                      </p>
                    </div>

                    <div className="w-full bg-white/2 border border-white/5 rounded-xl p-4 text-left flex flex-col gap-3">
                      <div className="text-[10px] uppercase font-bold tracking-wider text-slate-400 select-none">
                        How to resolve this issue:
                      </div>
                      <ul className="text-xs text-slate-400 flex flex-col gap-2 list-none p-0 m-0">
                        <li className="flex gap-2 items-start">
                          <span className="text-rose-500 font-bold">•</span>
                          <span>
                            <strong>Verify IAM Roles</strong>: Ensure your active account has the <strong>Discovery Engine Viewer</strong> or <strong>Gemini Data Analytics User</strong> role enabled in the target project.
                          </span>
                        </li>
                        <li className="flex gap-2 items-start">
                          <span className="text-rose-500 font-bold">•</span>
                          <span>
                            <strong>API Activation</strong>: Verify that the <strong>Cloud Resource Manager API</strong> and <strong>Vertex AI Search</strong> APIs are enabled in the Google Cloud Console.
                          </span>
                        </li>
                        <li className="flex gap-2 items-start">
                          <span className="text-rose-500 font-bold">•</span>
                          <span>
                            <strong>Change Identity / Project</strong>: Try toggling between <em>Service Account</em> and <em>SSO Session</em>, or select another target project in the top-right Connection menu.
                          </span>
                        </li>
                      </ul>
                    </div>

                    <div className="flex gap-3 mt-2 w-full">
                      <button 
                        onClick={fetchAgents}
                        className="flex-1 py-3 bg-brand-primary hover:opacity-90 text-white font-semibold rounded-xl text-xs cursor-pointer transition duration-200 shadow-md border-none"
                      >
                        Retry Connection
                      </button>
                      <button 
                        onClick={() => setCurrentPage("settings")}
                        className="flex-1 py-3 bg-white/5 border border-white/6 hover:bg-white/10 text-white font-semibold rounded-xl text-xs cursor-pointer transition duration-200"
                      >
                        Open Portal Settings
                      </button>
                    </div>
                  </div>
                </div>
              ) : messages.length === 0 ? (
                // Clean empty state with beautiful query starters (hidden when schema is expanded to maximize canvas)
                isSchemaExpanded ? null : (() => {
                  const activeAgentObj = selectedAgent ? agents.find(a => a.name === selectedAgent) : undefined;

                  return (
                    <div className="flex-1 flex flex-col items-center justify-center p-4 md:p-8 mx-auto text-center my-auto animate-fadeIn select-none transition-all duration-300 max-w-2xl">
                      {/* Brand icon */}
                      <div className="w-14 h-14 rounded-2xl bg-brand-primary/10 border border-brand-primary/25 flex items-center justify-center mb-6 shadow-sm shadow-brand-primary/5">
                        <Sparkles size={26} className="text-brand-primary animate-pulse" />
                      </div>
                      
                      {selectedAgent ? (
                        <>
                          <h2 className="font-heading text-2xl md:text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-white via-slate-200 to-slate-400 mb-3 tracking-tight leading-none">
                            What would you like to analyze today?
                          </h2>
                          <p className="text-xs md:text-sm text-slate-400 mb-5 md:mb-8 max-w-md leading-relaxed">
                            {activeAgentObj?.welcomeSubtitle || activeAgentObj?.description || "Ask any analytical question about your connected data tables."}
                          </p>
                        </>
                      ) : (
                        <>
                          <h2 className="font-heading text-2xl md:text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-white via-slate-200 to-slate-400 mb-3 tracking-tight leading-none">
                            Conversational Analytics Hub
                          </h2>
                          <p className="text-xs md:text-sm text-slate-400 mb-5 md:mb-8 max-w-md leading-relaxed">
                            Unlock the power of your BigQuery data warehouses using natural language. Select an AI Data Specialist from the sidebar or dropdown to start asking questions, generating forecasts, and analyzing trends instantly.
                          </p>
                        </>
                      )}
                  
                  {/* Mobile-only Centered Agent Selector */}
                  {window.innerWidth < 768 && agents.length > 0 && (
                    <div className="w-full max-w-sm p-4 bg-white/3 border border-white/6 rounded-2xl mb-6 flex flex-col items-center gap-3 animate-slideIn">
                      <div className="flex items-center gap-2 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                        <svg className="w-3.5 h-3.5 text-brand-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                        </svg>
                        Select AI Specialist
                      </div>
                      
                      <div className="relative w-full">
                        <select
                          value={selectedAgent}
                          onChange={handleAgentChange}
                          className="w-full py-2.5 pl-4 pr-10 bg-slate-950/60 border border-white/10 rounded-xl text-xs font-semibold text-slate-200 focus:border-brand-primary outline-none cursor-pointer appearance-none text-center"
                        >
                          <option value="">Select a data agent</option>
                          {agents.map((agent, idx) => (
                            <option key={idx} value={agent.name}>
                              {agent.displayName || agent.name.split("/").pop()}
                            </option>
                          ))}
                        </select>
                        <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-slate-400">
                          <ChevronDown size={14} />
                        </div>
                      </div>
                      
                      <p className="text-[10px] text-slate-500 font-medium text-center">
                        Active agent handles your queries and provides custom data insights.
                      </p>
                    </div>
                  )}
                  
                  {selectedAgent ? (
                    (() => {
                      const activeAgentObj = agents.find(a => a.name === selectedAgent);
                      
                      // Render standard suggestions grid
                      return (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 w-full">
                          {( (() => {
                            if (activeAgentObj && Array.isArray(activeAgentObj.suggestions) && activeAgentObj.suggestions.length > 0) {
                              return activeAgentObj.suggestions;
                            }
                            const agentId = selectedAgent.split("/").pop() || "";
                            return getAgentSuggestions(activeAgentObj?.displayName || "", agentId, appActiveBrandKey);
                          })() as string[] ).map((suggestion, idx) => (
                            <button
                              key={idx}
                              onClick={() => {
                                setInputText(suggestion);
                                handleSendMessage(suggestion);
                              }}
                              className="p-4 bg-white/3 border border-white/6 hover:border-brand-primary/30 hover:bg-brand-primary/5 rounded-2xl text-left text-xs text-slate-300 font-medium transition cursor-pointer flex flex-col gap-1.5 shadow-sm group hover:-translate-y-0.5 duration-200"
                            >
                              <span className="group-hover:text-white transition duration-150 leading-relaxed">{suggestion}</span>
                              <span className="text-[10px] font-bold text-brand-primary shrink-0 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-0.5 mt-auto">
                                Ask agent <ChevronRight size={10} />
                              </span>
                            </button>
                          ))}
                        </div>
                      );
                    })()
                  ) : (
                    <div className="p-6 bg-white/3 border border-white/6 rounded-2xl max-w-sm w-full mx-auto flex flex-col gap-4 text-center backdrop-blur-md shadow-lg animate-fadeIn">
                      <div className="flex items-center justify-center w-11 h-11 rounded-xl bg-brand-primary/10 text-brand-primary mx-auto">
                        <Sparkles size={18} className="text-brand-primary animate-pulse" />
                      </div>
                      <div className="flex flex-col gap-1">
                        <h3 className="text-xs font-semibold text-white">To get started:</h3>
                        <p className="text-[10px] text-slate-500">Follow these simple steps to start analyzing your data</p>
                      </div>
                      <ol className="text-[10px] text-slate-400 text-left list-decimal list-inside flex flex-col gap-2.5 leading-relaxed">
                        <li>Select an <strong>AI Data Specialist</strong> from the sidebar dropdown.</li>
                        <li>Choose a pre-configured query starter card or type your own question.</li>
                        <li>Review the generated SQL, step-by-step thinking logs, and interactive charts.</li>
                      </ol>
                    </div>
                  )}
                    </div>
                  );
                })()
              ) : (
                messages.map((msg, idx) => {
                  const isUser = !!msg.userMessage;
                  
                  return (
                    <div 
                      key={idx}
                      className={`flex gap-4 max-w-[85%] ${isUser ? "self-end flex-row-reverse" : "self-start"} animate-slideIn`}
                    >
                      <div className={`w-9 h-9 rounded-full flex items-center justify-center font-heading font-semibold text-xs shrink-0 select-none ${isUser ? "bg-brand-primary text-white" : "bg-white/5 border border-white/6 text-slate-200"}`}>
                        {isUser ? "ME" : renderLogoSvg(appActiveBrandKey)}
                      </div>
                      
                      <div className={`px-5 py-4 rounded-2xl shadow-sm text-[0.95rem] leading-relaxed ${isUser ? "bg-brand-primary/10 border border-brand-primary/25 rounded-tr-sm" : "bg-white/3 border border-white/6 rounded-tl-sm"}`}>
                        {isUser ? (
                          <p>{cleanUserMessage(msg.userMessage?.text)}</p>
                        ) : (
                          <div className="markdown-body">
                            {(() => {
                              const parsed = {
                                statuses: msg.systemMessage?.statuses || [],
                                thoughts: msg.systemMessage?.thoughts || [],
                                answer: msg.systemMessage?.answer || "",
                                insights: msg.systemMessage?.insights || "",
                                suggestions: msg.systemMessage?.suggestions || []
                              };
                              return (
                                <>
                                  <MessageThinkingBlock statuses={parsed.statuses} thoughts={parsed.thoughts} tourStep={tourStep} setTourStep={setTourStep} />
                                  {parsed.answer && (
                                    <div dangerouslySetInnerHTML={{ __html: marked.parse(formatMarkdown(parsed.answer)) }} />
                                  )}
                                  {msg.systemMessage?.schema && (
                                    <SchemaWidget schema={msg.systemMessage.schema} />
                                  )}
                                  {msg.systemMessage?.data?.generatedSql && (
                                    <SqlWidget data={msg.systemMessage.data} />
                                  )}
                                  {msg.systemMessage?.chart ? (
                                    <VisualizerWidget 
                                      chart={msg.systemMessage.chart} 
                                      data={msg.systemMessage.data} 
                                      primaryColorHsl={branding?.brands[appActiveBrandKey]?.primaryColor || "217 89% 61%"} 
                                    />
                                  ) : (
                                    msg.systemMessage?.data?.result?.data && (
                                      <DataTableOnlyWidget data={msg.systemMessage.data} />
                                    )
                                  )}
                                  {parsed.insights && (
                                    <div dangerouslySetInnerHTML={{ __html: marked.parse(formatMarkdown(parsed.insights)) }} />
                                  )}
                                </>
                              );
                            })()}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })
              )}

              {/* Follow-up suggestions */}
              {(() => {
                if (isQuerying || streamingMessages.length > 0 || messages.length === 0) return null;
                const lastMsg = messages[messages.length - 1];
                if (lastMsg.userMessage) return null;

                const lastParsed = {
                  statuses: lastMsg.systemMessage?.statuses || [],
                  thoughts: lastMsg.systemMessage?.thoughts || [],
                  answer: lastMsg.systemMessage?.answer || "",
                  insights: lastMsg.systemMessage?.insights || "",
                  suggestions: lastMsg.systemMessage?.suggestions || []
                };
                const suggestionsToRender = lastParsed.suggestions.length > 0 
                  ? lastParsed.suggestions 
                  : (() => {
                      const activeAgentObj = agents.find(a => a.name === selectedAgent);
                      if (activeAgentObj && Array.isArray(activeAgentObj.suggestions) && activeAgentObj.suggestions.length > 0) {
                        return activeAgentObj.suggestions;
                      }
                      const agentId = selectedAgent.split("/").pop() || "";
                      return getAgentSuggestions(activeAgentObj?.displayName || "", agentId, appActiveBrandKey);
                    })() as string[];

                if (suggestionsToRender.length === 0) return null;

                return (
                  <div 
                    id="chat-suggestions-container"
                    className={`flex flex-col gap-2 mt-2 ml-13 animate-fadeIn ${tourStep === 20 ? 'tour-highlight p-2 rounded-2xl bg-white/2 border border-white/6' : ''}`}
                  >
                    <div className="flex flex-wrap gap-2">
                      {suggestionsToRender.map((suggestion: string, sIdx: number) => (
                        <button
                          key={sIdx}
                          onClick={() => handleSendMessage(suggestion)}
                          className="px-4.5 py-2.5 text-xs font-medium text-slate-300 hover:text-white bg-slate-900/40 hover:bg-brand-primary/15 border border-white/8 hover:border-brand-primary/45 rounded-xl transition-all duration-200 cursor-pointer select-none shadow-sm hover:shadow-md hover:scale-[1.01] active:scale-[0.99]"
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })()}

              {/* Streaming Output Renderer */}
              {streamingMessages.length > 0 && (
                <div className="flex gap-4 max-w-[85%] self-start animate-slideIn">
                  <div className="w-9 h-9 rounded-full bg-white/5 border border-white/6 flex items-center justify-center font-heading font-semibold text-xs shrink-0 select-none">
                    {renderLogoSvg(appActiveBrandKey)}
                  </div>
                  
                  <div className="px-5 py-4 rounded-2xl bg-white/3 border border-white/6 rounded-tl-sm shadow-sm text-[0.95rem] leading-relaxed">
                    <div className="markdown-body">
                      {(() => {
                        const parsedStreamingList = groupConversationalMessages(
                          streamingMessages.map(m => ({ systemMessage: m }))
                        );
                        const parsedStreaming = parsedStreamingList[0]?.systemMessage || {
                          statuses: [],
                          thoughts: [],
                          answer: "",
                          insights: "",
                          suggestions: [],
                          schema: null,
                          data: null,
                          chart: null
                        };

                        return (
                          <>
                            <MessageThinkingBlock statuses={parsedStreaming.statuses} thoughts={parsedStreaming.thoughts} isStreaming={true} tourStep={tourStep} setTourStep={setTourStep} />
                            {parsedStreaming.answer && (
                              <div dangerouslySetInnerHTML={{ __html: marked.parse(formatMarkdown(parsedStreaming.answer)) }} />
                            )}
                            {parsedStreaming.schema && <SchemaWidget schema={parsedStreaming.schema} />}
                            {parsedStreaming.data?.generatedSql && <SqlWidget data={parsedStreaming.data} />}
                            {parsedStreaming.chart ? (
                              <VisualizerWidget 
                                chart={parsedStreaming.chart} 
                                data={parsedStreaming.data} 
                                primaryColorHsl={branding?.brands[appActiveBrandKey]?.primaryColor || "217 89% 61%"} 
                              />
                            ) : (
                              parsedStreaming.data?.result?.data && <DataTableOnlyWidget data={parsedStreaming.data} />
                            )}
                            {parsedStreaming.insights && (
                              <div dangerouslySetInnerHTML={{ __html: marked.parse(formatMarkdown(parsedStreaming.insights)) }} />
                            )}
                          </>
                        );
                      })()}
                    </div>
                  </div>
                </div>
              )}

              {/* Loader Typing Bubble */}
              {isQuerying && streamingMessages.length === 0 && (
                <div id="agent-thinking-bubble" className="flex gap-4 max-w-[85%] self-start animate-slideIn">
                  <div className="w-9 h-9 rounded-full bg-white/5 border border-white/6 flex items-center justify-center font-heading font-semibold text-xs shrink-0 select-none">
                    {renderLogoSvg(appActiveBrandKey)}
                  </div>
                  <div className="flex items-center gap-3 py-3.5 px-5 bg-white/2 border border-white/6 rounded-2xl rounded-tl-sm select-none shadow-md">
                    <div className="relative w-5 h-5 flex items-center justify-center">
                      <svg viewBox="0 0 24 24" className="w-full h-full text-sky-400 fill-current animate-spin" style={{ animationDuration: '3s' }}>
                        <path d="M12,3 C12,7.97 16.03,12 21,12 C16.03,12 12,16.03 12,21 C12,16.03 7.97,12 3,12 C7.97,12 12,7.97 12,3 Z" />
                      </svg>
                      <div className="absolute inset-0 bg-sky-400/20 rounded-full blur-md animate-pulse" />
                    </div>
                    <span className="text-xs font-semibold text-slate-300 animate-pulse">Agent is thinking...</span>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </section>

            {/* Chat Input Container */}
            <div className="px-4 md:px-10 pb-4 md:pb-8 pt-2 mt-auto">
              <div 
                id="chat-input-container"
                className={`glass-panel flex flex-col gap-2 px-4 md:px-6 py-3 md:py-4 rounded-2xl shadow-xl ${(tourStep === 18) ? 'tour-highlight' : ''}`}
              >
                <textarea 
                  ref={textareaRef}
                  value={inputText}
                  onChange={(e) => {
                    setInputText(e.target.value);
                    handleInputResize();
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask a question about your database..." 
                  rows={1}
                  className="w-full bg-transparent border-none text-slate-100 placeholder-slate-400 text-md resize-none outline-none max-h-32"
                />
                
                {/* Bottom Row Controls */}
                <div className="flex justify-between items-center border-t border-white/4 pt-2.5 mt-1 select-none">
                  {/* Left Side: Chat Mode Dropdown */}
                  <div className="relative" ref={chatModeDropdownRef}>
                    <button 
                      id="chat-mode-btn"
                      onClick={() => {
                        console.log("Chat mode button clicked! Old state:", showChatModeDropdown);
                        setShowChatModeDropdown(!showChatModeDropdown);
                      }}
                      className={`flex items-center gap-1.5 px-3 py-1.5 bg-white/3 hover:bg-white/6 border border-white/6 rounded-lg text-xs font-semibold text-slate-300 transition cursor-pointer select-none border-none ${(tourStep === 11 || tourStep === 15) ? 'tour-highlight' : ''}`}
                    >
                      <Sparkles size={12} className={chatMode === "thinking" ? "text-sky-400 fill-sky-400/20 animate-pulse" : "text-slate-400"} />
                      <span>{chatMode === "thinking" ? "Thinking Mode" : "Fast Mode"}</span>
                      <ChevronDown size={12} className="text-slate-400" />
                    </button>
                    
                    {showChatModeDropdown && (
                      <div className={`absolute bottom-full left-0 mb-2 w-64 bg-slate-950/95 border border-white/8 rounded-xl shadow-xl overflow-hidden backdrop-blur-md animate-slideUp ${tourStep > 0 ? 'z-[2000]' : 'z-50'}`}>
                        <button
                          onClick={() => {
                            setChatMode("fast");
                            setShowChatModeDropdown(false);
                            if (tourStep === 15) setTourStep(conversations.length === 0 ? 17 : 16);
                          }}
                          className={`w-full px-4 py-3 text-left hover:bg-white/4 transition flex flex-col gap-0.5 cursor-pointer border-none bg-transparent ${chatMode === "fast" ? "bg-white/2" : ""}`}
                        >
                          <span className="text-xs font-bold text-slate-100 flex items-center gap-1.5">
                            Fast <span className="text-[9px] font-semibold text-emerald-400 bg-emerald-400/10 px-1.5 py-0.5 rounded-full">GA</span>
                          </span>
                          <span className="text-[10px] text-slate-400 leading-normal">Best for most standard analytical questions. Fast answers.</span>
                        </button>
                        <div className="h-[1px] bg-white/4" />
                        <button
                          onClick={() => {
                            setChatMode("thinking");
                            setShowChatModeDropdown(false);
                            if (tourStep === 15) setTourStep(conversations.length === 0 ? 17 : 16);
                          }}
                          className={`w-full px-4 py-3 text-left hover:bg-white/4 transition flex flex-col gap-0.5 cursor-pointer border-none bg-transparent ${chatMode === "thinking" ? "bg-white/2" : ""}`}
                        >
                          <span className="text-xs font-bold text-slate-100 flex items-center gap-1.5">
                            Thinking <span className="text-[9px] font-semibold text-sky-400 bg-sky-400/10 px-1.5 py-0.5 rounded-full">Preview</span>
                          </span>
                          <span className="text-[10px] text-slate-400 leading-normal">Deep reasoning. Best for complex logic, forecasting, or multiple steps.</span>
                        </button>
                      </div>
                    )}
                  </div>
                  
                  {/* Right Side: Send Button */}
                  <button 
                    onClick={handleSendMessage}
                    disabled={!inputText.trim() || isQuerying || !selectedAgent}
                    className="bg-brand-primary text-white border-none w-9 h-9 rounded-xl cursor-pointer flex items-center justify-center transition hover:scale-105 active:scale-100 disabled:opacity-50 disabled:hover:scale-100 disabled:cursor-not-allowed shadow-md"
                  >
                    <Send size={15} />
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </>
    )}

        {currentPage === "settings" && (
          <div className="max-w-4xl mx-auto w-full px-5 my-10 overflow-y-auto">
            <header className="glass-panel flex items-center gap-6 px-8 py-5 rounded-2xl mb-6">
              <button 
                onClick={() => {
                  setCurrentPage("home");
                  if (tourStep > 0) {
                    setTourStep(0);
                    sessionStorage.setItem("ca_visited_tour", "true");
                  }
                }}
                className="flex items-center gap-2 text-sm text-slate-400 hover:text-white cursor-pointer transition font-medium"
              >
                <ArrowLeft size={16} />
                Back to Dashboard
              </button>
              <h1 className="font-heading text-xl font-bold text-white">Portal Settings</h1>
            </header>

            <div className="flex flex-col md:flex-row gap-6">
               {/* Settings Nav */}
              <nav id="settings-sidebar-nav" className={`glass-panel w-full md:w-64 p-4 rounded-2xl flex flex-col gap-2 h-fit ${tourStep === 2 ? 'tour-highlight' : ''}`}>
                {isCorporateUser(user?.email || auth.currentUser?.email || null) && (
                  <button 
                    onClick={() => setSettingsActiveTab("general")}
                    className={`px-4 py-3 text-left text-sm font-semibold rounded-lg cursor-pointer transition duration-150 ${settingsActiveTab === "general" ? "bg-white/8 text-white border-l-3 border-l-brand-primary" : "text-slate-400 hover:text-white hover:bg-white/2"}`}
                  >
                    General Configuration
                  </button>
                )}
                <button 
                  onClick={() => setSettingsActiveTab("branding")}
                  className={`px-4 py-3 text-left text-sm font-semibold rounded-lg cursor-pointer transition duration-150 ${settingsActiveTab === "branding" ? "bg-white/8 text-white border-l-3 border-l-brand-primary" : "text-slate-400 hover:text-white hover:bg-white/2"}`}
                >
                  Branding Profile
                </button>
              </nav>

              {/* Panel Content */}
              <div className="flex-1">
                {settingsActiveTab === "general" ? (
                  <div id="settings-auth-config" className="glass-panel p-8 rounded-2xl flex flex-col gap-6">
                    <h2 className="font-heading text-lg font-bold text-white mb-2">Connection Details</h2>
                    
                    <div className="flex flex-col gap-2">
                      <label className="text-xs font-semibold text-slate-400">Authentication Mode</label>
                      <div className="relative">
                        <select 
                          value={credentialsMode} 
                          onChange={(e) => handleCredentialsModeChange(e.target.value as "service_account" | "user_sso")}
                          className="w-full py-3 px-4 bg-slate-950/40 border border-white/6 rounded-xl text-sm text-slate-200 outline-none focus:border-brand-primary/50 cursor-pointer appearance-none"
                        >
                          <option value="service_account">Service Account (ADC)</option>
                          {isCorporateUser(user?.email || auth.currentUser?.email || null) && (
                            <option value="user_sso">SSO User Session (Google Login)</option>
                          )}
                        </select>
                        <ChevronDown className="absolute right-4 top-4 text-slate-400 pointer-events-none" size={14} />
                      </div>
                      <small className="text-[10px] text-slate-400">
                        Choose between service-wide Google credentials or authenticating queries with your current user identity.
                      </small>
                    </div>

                    {credentialsMode === "user_sso" && (
                      <div className="flex flex-col gap-2">
                        <label className="text-xs font-semibold text-slate-400">Google Cloud Project ID</label>
                        {gcpProjects.length === 0 ? (
                          <input 
                            type="text" 
                            value={settingsProjectId} 
                            onChange={(e) => setSettingsProjectId(e.target.value)}
                            placeholder="Enter your target GCP Project ID (e.g. your-gcp-project-id)"
                            className="py-3 px-4 bg-slate-950/40 border border-white/6 rounded-xl text-sm text-slate-200 outline-none focus:border-brand-primary/50"
                          />
                        ) : (
                          <div className="relative">
                            <select 
                              value={settingsProjectId} 
                              onChange={(e) => setSettingsProjectId(e.target.value)}
                              className="w-full py-3 px-4 bg-slate-950/40 border border-white/6 rounded-xl text-sm text-slate-200 outline-none focus:border-brand-primary/50 cursor-pointer appearance-none"
                            >
                              {gcpProjects.map((p) => (
                                <option key={p.projectId} value={p.projectId}>
                                  {p.name} ({p.projectId})
                                </option>
                              ))}
                            </select>
                            <ChevronDown className="absolute right-4 top-4 text-slate-400 pointer-events-none" size={14} />
                          </div>
                        )}
                        <small className="text-[10px] text-slate-400">
                          Select the default Google Cloud Project ID for the portal. Takes effect dynamically in real time.
                        </small>
                      </div>
                    )}

                    <div className="flex flex-col gap-2">
                      <label className="text-xs font-semibold text-slate-400">GCP Location (Region)</label>
                      <div className="relative">
                        <select 
                          value={settingsLocation} 
                          onChange={(e) => {
                            const val = e.target.value;
                            setSettingsLocation(val);
                            handleLocationChange(val);
                          }}
                          className="w-full py-3 px-4 bg-slate-950/40 border border-white/6 rounded-xl text-sm text-slate-200 outline-none focus:border-brand-primary/50 cursor-pointer appearance-none"
                        >
                          <option value="all">All Common Regions (Scan All)</option>
                          <option value="global">Global (Default)</option>
                          <option value="us-central1">us-central1 (Iowa)</option>
                          <option value="europe-west1">europe-west1 (Belgium)</option>
                          <option value="us">us (US Multi-region)</option>
                          <option value="eu">eu (EU Multi-region)</option>
                        </select>
                        <ChevronDown className="absolute right-4 top-4 text-slate-400 pointer-events-none" size={14} />
                      </div>
                      <small className="text-[10px] text-slate-400">
                        Choose the Google Cloud region where your Dialogflow CX or Vertex AI Data Agents are deployed.
                      </small>
                    </div>

                    <div className="flex flex-col sm:flex-row sm:items-center gap-3 mt-2 w-full">
                      <button 
                        onClick={handleSaveGeneralConfig}
                        className="w-full sm:w-auto py-3 px-6 text-xs font-semibold bg-brand-primary hover:opacity-90 rounded-xl text-white transition cursor-pointer shadow-md border-none animate-slideIn"
                      >
                        Save Connection Config
                      </button>
                      <button 
                        onClick={handleTestConnection}
                        className="w-full sm:w-auto py-3 px-5 text-xs font-medium bg-white/5 border border-white/6 hover:bg-white/10 rounded-xl text-white transition cursor-pointer"
                      >
                        Test API Connection
                      </button>
                      {settingsSaveResult && (
                        <span className="text-xs text-emerald-400 font-semibold animate-pulse">{settingsSaveResult}</span>
                      )}
                      <span className={`text-xs font-medium ${
                        settingsTestSuccess === true ? "text-emerald-400" : 
                        settingsTestSuccess === false ? "text-rose-400" : "text-slate-400"
                      }`}>{settingsTestResult}</span>
                    </div>
                  </div>
                ) : (
                  // Branding Panel
                  <div id="settings-branding-panel" className="flex flex-col gap-8 items-stretch w-full">
                    {/* Controls Column */}
                    <div id="settings-branding-controls" className={`w-full glass-panel p-8 rounded-2xl flex flex-col gap-6 ${tourStep === 3 ? 'tour-highlight' : ''}`}>
                      <h2 className="font-heading text-lg font-bold text-white mb-2">Active Branding Profile</h2>



                    <div className="flex flex-col gap-2">
                      <label className="text-xs font-semibold text-slate-400">Select Active Profile</label>
                      <div className="flex gap-3">
                        <div className="relative flex-1">
                          <select 
                            value={activeBrandKey}
                            onChange={(e) => {
                              const val = e.target.value;
                              setActiveBrandKey(val);
                              localStorage.setItem("ca_active_brand", val);
                              if (branding) {
                                const b = branding.brands[val];
                                setBrandName(b.name);
                                setBrandPrimary(b.primaryColor);
                                setBrandSecondary(b.secondaryColor);
                                setBrandBgStart(b.backgroundColorStart);
                                setBrandBgEnd(b.backgroundColorEnd);
                                setBrandLogoText(b.logoText);
                                setBrandWelcome(b.welcomeMessage);
                                setBrandLogoSvg(b.logoSvg || "");
                                setSettingsProjectId(b.gcpProjectId || "");
                                setSettingsLocation(b.gcpLocation || "all");
                              }
                            }}
                            className="w-full py-3 px-4 bg-slate-950/40 border border-white/6 rounded-xl text-sm text-slate-200 focus:border-brand-primary outline-none cursor-pointer appearance-none"
                          >
                            {branding && Object.keys(branding.brands).map((key, idx) => (
                              <option key={idx} value={key}>{branding.brands[key].name}</option>
                            ))}
                          </select>
                          <ChevronDown className="absolute right-4 top-3.5 text-slate-400 pointer-events-none" size={16} />
                        </div>
                        {activeBrandKey !== "default" && (
                          <button
                            onClick={handleDeleteBrand}
                            className="p-3 bg-rose-500/10 hover:bg-rose-500 text-rose-500 hover:text-white border border-rose-500/20 rounded-xl transition duration-200 cursor-pointer flex items-center justify-center shrink-0 w-11 h-11"
                            title="Delete this brand theme"
                          >
                            <Trash2 size={18} />
                          </button>
                        )}
                      </div>
                    </div>

                    <div className="flex flex-col gap-4 border-t border-white/6 pt-5 mt-2">
                      <h3 className="font-heading text-sm font-semibold text-slate-400">Search Brand Logo</h3>
                      <p className="text-[11px] text-slate-500 -mt-3 leading-relaxed">
                        Query by corporate name (e.g. <code className="text-[10px] bg-white/4 px-1 rounded">Coca Cola</code>), web domain name (e.g. <code className="text-[10px] bg-white/4 px-1 rounded">fleetpride.com</code>), or <code className="text-[10px] bg-white/4 px-1 rounded">upload your own</code> logo.
                      </p>
                      <div className="flex gap-2">
                        <input 
                          type="text" 
                          placeholder="e.g. Coca Cola, Target, Fleet Pride..." 
                          value={logoSearchQuery}
                          onChange={(e) => setLogoSearchQuery(e.target.value)}
                          onKeyDown={(e) => { if (e.key === 'Enter') handleSearchLogo(); }}
                          className="flex-1 min-w-0 py-3 px-4 bg-slate-950/40 border border-white/6 rounded-xl text-sm text-slate-200 outline-none focus:border-brand-primary"
                        />
                        <button
                          type="button"
                          onClick={handleSearchLogo}
                          disabled={isSearchingLogo || !logoSearchQuery.trim()}
                          className="py-3 px-5 bg-brand-primary hover:opacity-90 disabled:opacity-50 text-white text-xs font-semibold rounded-xl transition cursor-pointer border-none"
                        >
                          {isSearchingLogo ? "Searching..." : "Search"}
                        </button>
                        
                        <input 
                          type="file" 
                          ref={logoFileInputRef}
                          onChange={handleLogoUpload}
                          accept="image/png, image/jpeg, image/svg+xml"
                          className="hidden"
                        />
                        <button
                          type="button"
                          onClick={() => logoFileInputRef.current?.click()}
                          disabled={isGeneratingFromLogo}
                          className="p-3 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 text-slate-300 hover:text-white rounded-xl transition cursor-pointer flex items-center justify-center shrink-0 w-11 h-11"
                          title="Upload custom logo file (PNG, JPG, SVG)"
                        >
                          {isGeneratingFromLogo ? (
                            <Loader2 className="animate-spin animate-duration-1000" size={18} />
                          ) : (
                            <Upload size={18} />
                          )}
                        </button>
                      </div>

                      {logoSearchError && (
                        <span className="text-xs text-rose-400 font-semibold">{logoSearchError}</span>
                      )}

                      {/* Search Results / Analysis Status */}
                      {isSearchingLogo ? (
                        <div className="flex flex-col gap-2">
                          <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider animate-pulse select-none">Searching Brand Logos...</label>
                          <div className="grid grid-cols-4 gap-3 bg-slate-950/20 rounded-xl p-3 border border-white/4">
                            {[1, 2, 3, 4].map((i) => (
                              <div 
                                key={i}
                                className="p-2 bg-white/5 border border-white/4 rounded-xl flex flex-col items-center justify-center aspect-square gap-2 animate-pulse select-none"
                              >
                                <div className="w-10 h-10 rounded-lg bg-white/5" />
                                <div className="h-2 w-12 rounded bg-white/5" />
                                <div className="h-1.5 w-8 rounded bg-white/5 mt-0.5" />
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : isGeneratingFromLogo ? (
                        <div className="flex flex-col items-center justify-center py-6 gap-3 text-slate-400 text-xs font-semibold bg-slate-950/20 rounded-xl p-4 border border-white/4">
                          <Loader2 className="animate-spin text-brand-primary" size={24} />
                          <span>Analyzing logo colors and applying custom theme...</span>
                        </div>
                      ) : logoSearchResults.length > 0 ? (
                        <div className="flex flex-col gap-4">
                          {/* High-Resolution Logos */}
                          {logoSearchResults.some(r => r.source === "Web Search") && (
                            <div className="flex flex-col gap-2">
                              <label className="text-[9px] font-bold text-brand-primary uppercase tracking-wider flex items-center gap-1.5 select-none">
                                <span className="w-1 h-1 rounded-full bg-brand-primary" />
                                High-Resolution Logos (Web Search)
                              </label>
                              <div className="grid grid-cols-4 gap-3 bg-slate-950/20 rounded-xl p-3 border border-white/4 max-h-48 overflow-y-auto">
                                {logoSearchResults.filter(r => r.source === "Web Search").map((logo) => (
                                  <div 
                                    key={logo.url}
                                    onClick={() => handleSelectSearchLogo(logo.url, logo.title)}
                                    className="p-2 bg-white/5 border border-white/6 hover:border-brand-primary/50 hover:bg-brand-primary/5 rounded-xl cursor-pointer flex flex-col items-center justify-center aspect-square gap-1 transition group"
                                  >
                                    <div className="w-10 h-10 flex items-center justify-center overflow-hidden">
                                      <img 
                                        src={logo.url} 
                                        alt={logo.title} 
                                        className="max-w-full max-h-full object-contain group-hover:scale-105 transition"
                                        onError={() => {
                                          setLogoSearchResults(prev => prev.filter(r => r.url !== logo.url));
                                        }}
                                      />
                                    </div>
                                    <span className="text-[8px] text-slate-500 font-bold uppercase tracking-wider scale-90 mt-1">High Res</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Fallback Favicons */}
                          {logoSearchResults.some(r => r.source !== "Web Search") && (
                            <div className="flex flex-col gap-2">
                              <label className="text-[9px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5 select-none">
                                <span className="w-1 h-1 rounded-full bg-slate-500" />
                                Website Favicons (Low Res Fallback)
                              </label>
                              <div className="grid grid-cols-4 gap-3 bg-slate-950/20 rounded-xl p-3 border border-white/4 max-h-48 overflow-y-auto">
                                {logoSearchResults.filter(r => r.source !== "Web Search").map((logo) => (
                                  <div 
                                    key={logo.url}
                                    onClick={() => handleSelectSearchLogo(logo.url, logo.title)}
                                    className="p-2 bg-white/5 border border-white/6 hover:border-brand-primary/50 hover:bg-brand-primary/5 rounded-xl cursor-pointer flex flex-col items-center justify-center aspect-square gap-1 transition group"
                                  >
                                    <div className="w-10 h-10 flex items-center justify-center overflow-hidden">
                                      <img 
                                        src={logo.url} 
                                        alt={logo.title} 
                                        className="max-w-full max-h-full object-contain group-hover:scale-105 transition"
                                        onError={() => {
                                          setLogoSearchResults(prev => prev.filter(r => r.url !== logo.url));
                                        }}
                                      />
                                    </div>
                                    <span className="text-[8px] text-slate-500 font-bold uppercase tracking-wider scale-90 mt-1">Favicon</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      ) : null}

                      {/* Selected Logo Preview Widget */}
                      {brandLogoSvg && (
                        <div className="flex flex-col gap-4 border-t border-white/6 pt-4">
                          <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Active Logo & Theme Preview</label>
                          <div className="flex items-center gap-4 bg-slate-950/40 border border-white/6 rounded-xl p-4">
                            <div className={`w-16 h-16 rounded-xl border border-white/6 p-2 flex items-center justify-center shrink-0 ${brandLogoSvg.includes("<img") ? 'bg-white' : 'bg-white/5'}`}>
                              {brandLogoSvg.includes("<svg") ? (
                                <div className="w-full h-full text-brand-primary" dangerouslySetInnerHTML={{ __html: brandLogoSvg }} />
                              ) : (
                                <div className="w-full h-full text-brand-primary" dangerouslySetInnerHTML={{ __html: brandLogoSvg }} />
                              )}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="text-sm font-semibold text-white truncate">{brandName}</div>
                              <div className="text-[10px] text-slate-500 font-medium mt-0.5">Primary Hue: {brandPrimary}</div>
                              <div className="text-[10px] text-slate-500 font-medium">Secondary Hue: {brandSecondary}</div>
                            </div>
                          </div>

                          {/* Editable branding texts */}
                          <div className="flex flex-col gap-3 bg-slate-950/20 border border-white/4 rounded-xl p-4">
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                              <div className="flex flex-col gap-1.5">
                                <label className="text-[9px] font-bold text-slate-400 uppercase tracking-wider select-none text-left">Header Portal Title</label>
                                <input
                                  type="text"
                                  value={brandLogoText}
                                  onChange={(e) => setBrandLogoText(e.target.value)}
                                  placeholder="e.g. COCA COLA"
                                  className="w-full py-2 px-3 bg-slate-950 border border-white/8 rounded-lg text-xs text-slate-200 focus:border-brand-primary outline-none"
                                />
                              </div>
                              <div className="flex flex-col gap-1.5">
                                <label className="text-[9px] font-bold text-slate-400 uppercase tracking-wider select-none text-left">Theme Profile Name</label>
                                <input
                                  type="text"
                                  value={brandName}
                                  onChange={(e) => setBrandName(e.target.value)}
                                  placeholder="e.g. Coca-Cola"
                                  className="w-full py-2 px-3 bg-slate-950 border border-white/8 rounded-lg text-xs text-slate-200 focus:border-brand-primary outline-none"
                                />
                              </div>
                            </div>
                            <div className="flex flex-col gap-1.5 mt-1">
                              <label className="text-[9px] font-bold text-slate-400 uppercase tracking-wider select-none text-left">Welcome Message</label>
                              <textarea
                                value={brandWelcome}
                                onChange={(e) => setBrandWelcome(e.target.value)}
                                placeholder="Welcome to Coca-Cola Analytics..."
                                rows={2}
                                className="w-full py-2 px-3 bg-slate-950 border border-white/8 rounded-lg text-xs text-slate-200 focus:border-brand-primary outline-none resize-none"
                              />
                            </div>
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="flex flex-col sm:flex-row sm:items-center gap-3 mt-2 border-t border-white/6 pt-5 w-full">
                      <button 
                        id="settings-save-branding-btn"
                        onClick={handleSaveBranding}
                        className={`w-full sm:w-auto py-3 px-6 text-sm font-medium bg-brand-primary hover:opacity-90 rounded-xl text-white transition cursor-pointer shadow-md border-none ${tourStep === 5 ? 'tour-highlight' : ''}`}
                      >
                        Save Branding Config
                      </button>
                      <button
                        type="button"
                        onClick={() => setShowPreviewModal(true)}
                        id="settings-trigger-preview-btn"
                        className={`w-full sm:w-auto py-3 px-5 text-sm font-semibold bg-white/5 border border-white/6 hover:bg-white/10 text-white rounded-xl transition cursor-pointer ${tourStep === 4 ? 'tour-highlight' : ''}`}
                      >
                        Show Live Preview
                      </button>
                      <span className="text-xs text-emerald-400 font-semibold">{settingsSaveResult}</span>
                    </div>
                  </div> {/* Closes Controls Column */}


                  </div> // Closes settings-branding-panel flex container
                )}
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Reference Architecture Modal overlay */}
      <ArchitectureModal 
        key={isArchModalOpen ? "open" : "closed"}
        isOpen={isArchModalOpen} 
        onClose={() => setIsArchModalOpen(false)} 
        isGraphAgent={agents.find(a => a.name === selectedAgent)?.isGraphAgent || false}
      />

      {/* Global Glassmorphic Loading Overlay */}
      {(isCreatingConvo || deletingConvoName) && (
        <div 
          className="fixed inset-0 bg-slate-950/60 backdrop-blur-md flex flex-col items-center justify-center animate-fadeIn"
          style={{ zIndex: 9999 }}
        >
          <div className="glass-panel p-8 rounded-2xl flex flex-col items-center gap-4 max-w-sm text-center border border-white/10 shadow-2xl scale-100 transition duration-300">
            <div className="w-16 h-16 rounded-full bg-brand-primary/10 border border-brand-primary/20 flex items-center justify-center text-brand-primary animate-pulse">
              <Loader2 size={32} className="animate-spin text-brand-primary" style={{ animationDuration: "1.5s" }} />
            </div>
            <div>
              <h3 className="font-heading font-semibold text-white text-md">
                {isCreatingConvo ? "Creating Workspace" : "Deleting Workspace"}
              </h3>
              <p className="text-slate-400 text-xs mt-1.5 leading-relaxed">
                {isCreatingConvo 
                  ? "Configuring your new conversational analytics session. Please wait a moment..." 
                  : "Removing conversation history and clearing session data from Google Cloud..."
                }
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Onboarding Tour Welcome Opt-In Modal */}
      {tourStep === -1 && (
        <div className="fixed inset-0 bg-slate-950/70 backdrop-blur-sm flex items-center justify-center z-[9999] animate-fadeIn">
          <div className="glass-panel p-8 rounded-2xl flex flex-col items-center gap-5 max-w-sm text-center border border-white/10 shadow-2xl animate-scaleIn">
            <div className="w-16 h-16 rounded-full bg-brand-primary/10 border border-brand-primary/20 flex items-center justify-center text-brand-primary">
              <Sparkles size={32} className="text-amber-400 animate-pulse" />
            </div>
            {window.innerWidth < 768 ? (
              <>
                <div className="flex flex-col gap-2">
                  <h3 className="font-heading font-bold text-white text-lg">
                    Guided Tour Available
                  </h3>
                  <p className="text-slate-300 text-xs leading-relaxed font-medium">
                    Welcome to the portal! The full interactive guided tour and walkthrough are best experienced on a desktop browser. Please open this portal on a larger screen to explore the full capabilities of our AI agents and customization options!
                  </p>
                </div>
                <button
                  onClick={() => {
                    setTourStep(0);
                    sessionStorage.setItem("ca_visited_tour", "true");
                  }}
                  className="w-full py-2.5 px-4 bg-brand-primary hover:opacity-90 text-white rounded-xl text-xs font-semibold cursor-pointer transition shadow-md border-none mt-2"
                >
                  Got it
                </button>
              </>
            ) : (
              <>
                <div className="flex flex-col gap-2">
                  <h3 className="font-heading font-bold text-white text-lg">
                    New here?
                  </h3>
                  <p className="text-slate-300 text-xs leading-relaxed font-medium">
                    {!isCorporateUser(user?.email || auth.currentUser?.email || null)
                      ? "See how to navigate this site, customize branding, and use AI agents."
                      : "See how to navigate this site, configure credentials, customize branding, and use AI agents."
                    }
                  </p>
                </div>
                <div className="flex gap-3 w-full mt-2">
                  <button
                    onClick={() => {
                      setTourStep(0);
                      sessionStorage.setItem("ca_visited_tour", "true");
                    }}
                    className="flex-1 py-2.5 px-4 bg-white/5 border border-white/6 hover:bg-white/10 text-white rounded-xl text-xs font-semibold cursor-pointer transition border-none"
                  >
                    No, thanks
                  </button>
                  <button
                    onClick={() => {
                      setTourStep(1);
                      setCurrentPage("home");
                    }}
                    className="flex-1 py-2.5 px-4 bg-brand-primary hover:opacity-90 text-white rounded-xl text-xs font-semibold cursor-pointer transition shadow-md border-none"
                  >
                    Yes, start tour
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Onboarding Tour Tooltip Overlay */}
      {tourStep > 0 && (
        <div 
          className="absolute bg-slate-900/98 border border-amber-500/55 p-5 rounded-2xl shadow-[0_0_30px_rgba(245,158,11,0.18)] z-[9999] w-[340px] flex flex-col gap-3.5 select-none"
          style={tooltipStyle}
        >
          {/* Arrow indicator */}
          {window.innerWidth >= 768 && (() => {
            const isThinkingBubble = tourStep === 19 && !document.getElementById("show-thinking-btn");
            return (
              <>
                {(tourStep === 1 || tourStep === 6 || tourStep === 13 || tourStep === 17 || isThinkingBubble) && (
                  <div className={`absolute -top-2 ${tourStep === 1 || tourStep === 13 || tourStep === 17 ? 'right-6' : 'left-6'} w-4 h-4 bg-slate-900 border-t border-l border-amber-500/55 rotate-45`} />
                )}
                {(tourStep === 2 || tourStep === 9 || tourStep === 10 || tourStep === 14 || tourStep === 16) && (
                  <div className="absolute -left-2 top-6 w-4 h-4 bg-slate-900 border-b border-l border-amber-500/55 rotate-45" />
                )}
                {(tourStep === 11 || tourStep === 15) && (
                  <div className="absolute -left-2 bottom-6 w-4 h-4 bg-slate-900 border-b border-l border-amber-500/55 rotate-45" />
                )}
                {(tourStep === 3 || tourStep === 12) && (
                  <div className="absolute -right-2 top-6 w-4 h-4 bg-slate-900 border-t border-r border-amber-500/55 rotate-45" />
                )}
                {(tourStep === 4 || tourStep === 5 || tourStep === 7 || tourStep === 8 || tourStep === 18 || (tourStep === 19 && !isThinkingBubble) || tourStep === 20) && (
                  <div className={`absolute -bottom-2 ${tourStep === 4 || tourStep === 5 ? 'right-6' : 'left-6'} w-4 h-4 bg-slate-900 border-b border-r border-amber-500/55 rotate-45`} />
                )}
              </>
            );
          })()}

          {/* Content */}
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-amber-400 animate-pulse" />
            <h4 className="text-xs font-bold uppercase tracking-wider text-amber-400">
              {getDisplayStepInfo(tourStep).text}
            </h4>
          </div>

          <p className="text-xs text-slate-300 leading-relaxed font-medium">
            {tourStep === 1 && (window.innerWidth < 768 
              ? "Welcome to the portal! The full interactive guided tour and walkthrough are best experienced on a desktop browser. Please open this portal on a larger screen to explore the full capabilities of our AI agents and customization options!"
              : (!isCorporateUser(user?.email || auth.currentUser?.email || null) 
                ? "Click the settings gear icon in the top right to update your portal branding profile." 
                : "Click the settings gear icon in the top right to manage your portal branding profile or modify how the website communicates with the Conversational Analytics API."))
            }
            {tourStep === 2 && "Select 'SSO User Session' in case you want to access and query custom data agents defined inside your own Google Cloud projects."}
            {tourStep === 3 && "Set your logo banner titles, search the web, or upload your own custom brand logo to personalize your analytics portal."}
            {tourStep === 4 && "Once you have finished customizing the branding settings, click here to see a live preview of how the conversational analytics workspace looks."}
            {tourStep === 5 && "Save your branding settings to apply them across your workspace, updating your layout theme and greeting cards instantly."}
            {tourStep === 6 && "Great job configuring! Click the brand logo or application title in the top-left header to navigate back to the main dashboard."}
            {tourStep === 7 && "View a list of your most recent chat sessions. Click on any chat history card to instantly jump back into that conversation!"}
            {tourStep === 8 && "Select this action to enter the interactive chat workspace, where you can ask questions and query your data directly using natural conversation."}
            {tourStep === 9 && (window.innerWidth < 768
              ? "We have automatically opened the top-left menu (☰) for you. Choose the retail analytics agent from the dropdown."
              : "Choose the agent you want to interact to using Conversational Analytics API.")
            }
            {tourStep === 10 && (window.innerWidth < 768
              ? "Open the top-left menu (☰) to view recent conversations or start a new chat session."
              : "View or manage your recent conversational analytics sessions with any of the data agents. You can start a new session or delete old ones to keep your workspace organized.")
            }
            {tourStep === 11 && "Toggle between 'Fast Answer' for quick responses, or 'In-Depth Analysis' to activate advanced reasoning models for complex queries and multi-step data visualizations."}
            {tourStep === 12 && "Change how the workspace interacts with the Conversational Analytics API directly from this quick dropdown menu, without going to the settings page."}
            {tourStep === 13 && "Access the reference architecture diagram explaining the pipeline flow from ingestion to display. Note that the architecture and visualizer schemas change dynamically depending on whether you choose a standard relational flat-table agent or a graph-connected property agent!"}
            {tourStep === 14 && (window.innerWidth < 768
              ? "We have automatically opened the top-left menu (☰) for you. Select a specialized AI agent to load its analytical capabilities."
              : "To begin the demo, select a specialized AI agent from this dropdown menu to load its analytical capabilities.")
            }
            {tourStep === 15 && "Select a thinking mode: Toggle 'Fast Answer' for quick responses, or 'In-Depth Analysis' to activate advanced reasoning models for complex queries."}
            {tourStep === 16 && "You already have active conversations for this agent. Click the '+' button to start a new, clean conversation and get a clean slate for the tutorial!"}
            {tourStep === 17 && "Need to reference your database? Click the 'Show Schema' button in the chat header at any time to expand or collapse the interactive schema diagram, allowing you to browse table structures and preview live BigQuery records!"}
            {tourStep === 18 && "Ask a question about your database! Type in the chat input or simply click one of the suggested query starter cards below (e.g., 'Show me the monthly trend of cost and revenue')."}
            {tourStep === 19 && "Once the agent begins responding, click 'Show thinking' to inspect the step-by-step reasoning, plan logic, and generated BigQuery SQL queries."}
            {tourStep === 20 && "Great query! You can follow-up on your conversation by typing in the input box, or simply click any of the dynamic follow-up suggestions generated by Gemini at the bottom."}
          </p>

          {/* Buttons */}
          <div className="flex flex-col gap-2.5 mt-1 pt-3 border-t border-white/6 w-full">
            {tourStep === 13 && (
              <button 
                onClick={startDemoWalkthrough}
                className="w-full py-2.5 px-3.5 bg-brand-primary hover:opacity-90 text-white rounded-lg text-xs font-bold cursor-pointer transition shadow-md border-none flex items-center justify-center gap-1.5"
              >
                <Sparkles size={13} className="fill-current animate-pulse" />
                Start Demo Walkthrough
              </button>
            )}

            <div className="flex items-center justify-between w-full">
              {window.innerWidth >= 768 ? (
                <button 
                  onClick={handleSkipTour}
                  className="text-[11px] font-bold text-slate-400 hover:text-amber-400 hover:underline transition cursor-pointer border-none bg-transparent whitespace-nowrap"
                >
                  Skip Tour
                </button>
              ) : (
                <div />
              )}

              <div className="flex gap-2 items-center">
                {window.innerWidth >= 768 && (
                  <span className="text-[10px] text-slate-500 font-bold mr-1 whitespace-nowrap">
                    {getDisplayStepInfo(tourStep).num} of {getDisplayStepInfo(tourStep).total}
                  </span>
                )}
                
                {window.innerWidth < 768 ? (
                  <button 
                    onClick={handleSkipTour}
                    className="py-1.5 px-3.5 bg-brand-primary hover:opacity-90 text-white rounded-lg text-xs font-semibold cursor-pointer transition shadow-md border-none"
                  >
                    Got it
                  </button>
                ) : (
                  <>
                    {tourStep > 1 && (
                      <button 
                        onClick={handleBackTour}
                        className="py-1.5 px-3 bg-white/5 border border-white/6 hover:bg-white/10 text-white rounded-lg text-xs font-semibold cursor-pointer transition border-none"
                      >
                        Back
                      </button>
                    )}
                    {tourStep !== 1 && tourStep !== 8 && tourStep !== 14 && tourStep !== 15 && tourStep !== 18 ? (
                      <button 
                        onClick={handleNextTour}
                        className="py-1.5 px-3.5 bg-brand-primary hover:opacity-90 text-white rounded-lg text-xs font-semibold cursor-pointer transition shadow-md border-none"
                      >
                        {tourStep === 20 ? "Finish Walkthrough" : (getDisplayStepInfo(tourStep).num === getDisplayStepInfo(tourStep).total ? "Finish" : "Next")}
                      </button>
                    ) : (
                      <span className="text-[10px] text-amber-400 font-bold animate-pulse mr-1 whitespace-nowrap">
                        {tourStep === 1 ? "Click gear icon" : 
                         tourStep === 8 ? "Click card to proceed" : 
                         tourStep === 14 ? "Select an agent" : 
                         tourStep === 15 ? "Choose thinking mode" : 
                         tourStep === 18 ? "Submit query or pill" : 
                         "Click 'Show thinking'"}
                      </span>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
      {showPreviewModal && (
        <div 
          onClick={() => setShowPreviewModal(false)}
          className="fixed inset-0 bg-slate-950/70 backdrop-blur-sm flex items-center justify-center z-50 animate-fadeIn select-none"
        >
          <div 
            onClick={(e) => e.stopPropagation()}
            className="glass-panel p-6 rounded-2xl w-full max-w-4xl border border-white/10 shadow-2xl flex flex-col gap-4"
          >
            <div className="flex justify-between items-center pb-2 border-b border-white/6">
              <h3 className="font-heading font-bold text-sm text-white">Live Portal Preview</h3>
              <button 
                onClick={() => setShowPreviewModal(false)}
                className="text-slate-400 hover:text-white transition cursor-pointer bg-transparent border-none p-0 text-xs font-semibold"
              >
                Close Preview
              </button>
            </div>
            
            <p className="text-slate-400 text-xs leading-normal">
              This is a real-time preview of how your theme colors, logo, and greetings will look in the Conversational Analytics workspace.
            </p>
            
            {/* Mini Browser Frame */}
            <div 
              className="w-full aspect-video rounded-xl border border-white/10 overflow-hidden flex flex-col shadow-inner transition duration-300 relative"
              style={{
                background: `linear-gradient(to bottom, ${brandBgStart || '#020617'}, ${brandBgEnd || '#0f172a'})`
              }}
            >
              {/* Mock Header */}
              <div className="h-10 border-b border-white/5 px-4 flex items-center justify-between bg-black/20 text-xs">
                <div className="flex items-center gap-2 font-heading font-bold" style={{ color: `hsl(${brandPrimary || '217 89% 61%'})` }}>
                  {/* Render Logo */}
                  {brandLogoSvg ? (
                    <div className={`w-5 h-5 flex items-center justify-center mini-logo-preview ${brandLogoSvg.includes("<img") ? 'bg-white/95 p-0.5 rounded' : ''}`} dangerouslySetInnerHTML={{ __html: brandLogoSvg }} />
                  ) : (
                    <div className="w-5 h-5 rounded bg-white/10 flex items-center justify-center font-bold text-[10px]">
                      {brandLogoText ? brandLogoText.substring(0, 2) : "AI"}
                    </div>
                  )}
                  <span className="text-[11px] font-semibold text-slate-200 truncate max-w-[250px]">
                    {brandLogoText || "AI Assistant"}
                  </span>
                </div>
                <div className="w-2 h-2 rounded-full shadow-[0_0_8px_currentColor]" style={{ color: `hsl(${brandPrimary || '217 89% 61%'})`, backgroundColor: `currentColor` }} />
              </div>

              {/* Mock Chat View */}
              <div className="flex-1 p-4 flex flex-col gap-3 overflow-y-auto justify-end">
                {/* Agent Greeting bubble */}
                <div className="flex gap-2.5 items-start max-w-[85%]">
                  <div className="w-6 h-6 rounded-full bg-white/5 border border-white/10 flex items-center justify-center shrink-0 overflow-hidden select-none">
                    {brandLogoSvg ? (
                      <div className={`w-full h-full p-0.5 flex items-center justify-center mini-logo-preview ${brandLogoSvg.includes("<img") ? 'bg-white' : ''}`} dangerouslySetInnerHTML={{ __html: brandLogoSvg }} />
                    ) : (
                      <span className="text-[9px] font-bold text-slate-300">
                        {brandLogoText ? brandLogoText.substring(0, 2) : "AI"}
                      </span>
                    )}
                  </div>
                  <div className="p-3 bg-white/4 border border-white/6 rounded-xl rounded-tl-sm text-[10px] text-slate-200 leading-relaxed font-medium max-h-[120px] overflow-y-auto whitespace-pre-wrap text-left">
                    {brandWelcome || "Hello! Ask me any questions."}
                  </div>
                </div>

                {/* User bubble */}
                <div className="p-3 bg-white/6 border border-white/10 rounded-xl rounded-tr-sm text-[10px] text-slate-200 leading-relaxed max-w-[85%] self-end text-left">
                  How are sales performing?
                </div>
              </div>

              {/* Mock Input */}
              <div className="p-3 border-t border-white/5 bg-black/10 flex gap-2 items-center">
                <div className="flex-1 h-8 bg-slate-950/60 border border-white/6 rounded-lg px-3 text-[10px] text-slate-500 flex items-center">
                  Type a question...
                </div>
                <div className="w-8 h-8 rounded-lg bg-white/5 border border-white/6 flex items-center justify-center text-[10px] text-slate-400">
                  ⚙️
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  </div>
  );
};

export default App;
