import { auth, requestGCPToken } from "../firebase";

export const authenticatedFetch = async (url: string, options: RequestInit = {}): Promise<Response> => {
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
