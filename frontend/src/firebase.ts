import { initializeApp } from "firebase/app";
import { getAuth, GoogleAuthProvider, signInWithPopup } from "firebase/auth";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
  measurementId: import.meta.env.VITE_FIREBASE_MEASUREMENT_ID,
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Initialize Auth
export const auth = getAuth(app);

// Sign in with Google SSO (basic authentication scopes only)
export const signInWithGoogle = async () => {
  const provider = new GoogleAuthProvider();
  provider.addScope("https://www.googleapis.com/auth/cloud-platform");
  
  // Force Google account selection
  provider.setCustomParameters({
    prompt: "select_account",
  });
  
  try {
    const result = await signInWithPopup(auth, provider);
    const credential = GoogleAuthProvider.credentialFromResult(result);
    const accessToken = credential?.accessToken;
    if (accessToken) {
      sessionStorage.setItem("gcp_user_access_token", accessToken);
      logger_log("Google OAuth Access Token saved during initial sign-in.");
    }
    return result.user;
  } catch (error) {
    console.error("Error signing in with Google SSO:", error);
    throw error;
  }
};

// Request incremental authorization for Google Cloud Platform scope
export const requestGCPToken = async () => {
  const provider = new GoogleAuthProvider();
  provider.addScope("https://www.googleapis.com/auth/cloud-platform");
  
  try {
    const result = await signInWithPopup(auth, provider);
    const credential = GoogleAuthProvider.credentialFromResult(result);
    const accessToken = credential?.accessToken;
    if (accessToken) {
      sessionStorage.setItem("gcp_user_access_token", accessToken);
      logger_log("Google OAuth Access Token successfully saved to sessionStorage.");
      return accessToken;
    }
    return null;
  } catch (error) {
    console.error("Error requesting GCP authorization scope:", error);
    throw error;
  }
};

// Simple log helper to avoid console clutter
const logger_log = (msg: string) => {
  console.log(`[Firebase Auth] ${msg}`);
};

export { GoogleAuthProvider, signInWithPopup };
