"use client";

import { createContext, useState, useContext, useEffect, useCallback, useMemo, useRef } from "react";
import supabase, { isSupabaseConfigured } from "@/supabaseClient";
import { API_BASE_URL } from "@/utils/apiBase";
import { FALLBACK_AVATAR, isUploadedAvatarValue, normalizeAvatarValue } from "@/utils/avatar";
import {
  authHeaders,
  clearBackendAuthSession,
  readPasswordAuthSession,
  requireBackendAuthSession,
  writeBackendAuthSession,
} from "@/utils/authSession";

const UserContext = createContext();

const GUEST_STORAGE_KEY = "supernova_social_six_guest";
const CUSTOM_STORAGE_PREFIX = "supernova_social_six_custom::";
const DEFAULT_AVATAR = FALLBACK_AVATAR;
const SPECIES_KEYS = new Set(["human", "ai", "company"]);

function normalizeSpecies(value) {
  const species = typeof value === "string" ? value.trim().toLowerCase() : "";
  return SPECIES_KEYS.has(species) ? species : "";
}

function normalizePrincipalSpecies(value) {
  const species = normalizeSpecies(value);
  return species === "ai" ? "" : species;
}

function calculateInitials(name) {
  if (!name || !name.trim()) return "";
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return parts.map((part) => part[0].toUpperCase()).join("").slice(0, 2);
  }
  return parts[0].slice(0, 2).toUpperCase();
}

function readStorage(key) {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeStorage(key, value) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Ignore unavailable storage.
  }
}

function removeStorage(key) {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(key);
  } catch {
    // Ignore unavailable storage.
  }
}

function getCustomStorageKey(authUser, passwordAuth) {
  const identityId = authUser?.id || passwordAuth?.id;
  if (!identityId) return GUEST_STORAGE_KEY;
  return `${CUSTOM_STORAGE_PREFIX}${identityId}`;
}

function getProviderProfile(authUser) {
  if (!authUser) {
    return {
      id: null,
      email: "",
      name: "",
      avatar: "",
      provider: "guest",
    };
  }

  const metadata = authUser.user_metadata || {};
  const provider = authUser.app_metadata?.provider
    || metadata.provider
    || authUser.identities?.[0]?.provider
    || "oauth";

  return {
    id: authUser.id,
    email: authUser.email || metadata.email || "",
    name: metadata.full_name || metadata.name || authUser.email || "",
    avatar: normalizeAvatarValue(metadata.avatar_url || metadata.picture || ""),
    provider,
  };
}

function getPasswordProfile(passwordAuth) {
  if (!passwordAuth) return null;
  return {
    id: passwordAuth.id || passwordAuth.username || null,
    email: passwordAuth.email || "",
    name: passwordAuth.username || "",
    avatar: normalizeAvatarValue(passwordAuth.avatar || ""),
    species: passwordAuth.species || "",
    provider: "password",
  };
}

function sameUsername(left = "", right = "") {
  return String(left || "").trim().toLowerCase() === String(right || "").trim().toLowerCase();
}

function profileMatchesBackendAuth(storedProfile = {}, backendAuth = null) {
  if (!backendAuth?.token) return false;
  const storedName = String(storedProfile?.customName || "").trim();
  return Boolean(storedName && sameUsername(storedName, backendAuth.username));
}

function persistBackendAuthFromSyncPayload(payload = {}, fallback = {}) {
  if (!payload?.access_token) return null;
  return writeBackendAuthSession({
    token: payload.access_token,
    id: payload.id || payload.username || fallback.username || "",
    username: payload.username || fallback.username || "",
    email: payload.email || fallback.email || "",
    avatar: normalizeAvatarValue(payload.avatar_url || fallback.avatar || ""),
    species: normalizeSpecies(payload.species) || normalizeSpecies(fallback.species) || "human",
  });
}

function mergeUserData(providerProfile, storedProfile = {}) {
  if (!providerProfile.id) {
    const species = normalizeSpecies(storedProfile.species) || "human";
    return {
      id: null,
      email: "",
      provider: "guest",
      isAuthenticated: false,
      species,
      avatar: "",
      providerAvatar: "",
      name: "",
      providerName: "",
      initials: "SN",
    };
  }

  const effectiveName = storedProfile.customName || providerProfile.name || "";
  const storedAvatar = normalizeAvatarValue(storedProfile.customAvatar || "");
  const providerAvatar = normalizeAvatarValue(providerProfile.avatar || "");
  const effectiveAvatar = storedAvatar || providerAvatar || "";
  const species = normalizeSpecies(storedProfile.species) || normalizeSpecies(providerProfile.species) || "human";

  return {
    id: providerProfile.id,
    email: providerProfile.email || "",
    provider: providerProfile.provider || "guest",
    isAuthenticated: Boolean(providerProfile.id),
    species,
    avatar: effectiveAvatar,
    providerAvatar,
    name: effectiveName,
    providerName: providerProfile.name || "",
    initials: calculateInitials(effectiveName || providerProfile.email || ""),
  };
}

export function UserProvider({ children }) {
  const [session, setSession] = useState(null);
  const [passwordAuth, setPasswordAuth] = useState(null);
  const [storedProfile, setStoredProfile] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [socialProfileLookup, setSocialProfileLookup] = useState({ key: "", status: "idle" });
  const authEpochRef = useRef(0);

  const authUser = session?.user ?? null;
  const providerProfile = useMemo(
    () => getPasswordProfile(!authUser ? passwordAuth : null) || getProviderProfile(authUser),
    [authUser, passwordAuth]
  );

  useEffect(() => {
    const savedPasswordAuth = readPasswordAuthSession();
    const initialStored = readStorage(getCustomStorageKey(null, savedPasswordAuth)) || readStorage(GUEST_STORAGE_KEY) || {};
    if (savedPasswordAuth?.token) setPasswordAuth(savedPasswordAuth);
    setStoredProfile(initialStored);

    if (!isSupabaseConfigured || !supabase) {
      setAuthLoading(false);
      return undefined;
    }

    let mounted = true;

    const applySessionState = (nextSession) => {
      const currentBackendAuth = readPasswordAuthSession();
      let nextBackendAuth = currentBackendAuth?.token ? currentBackendAuth : null;
      let nextStored = {};

      if (nextSession?.user) {
        const socialKey = getCustomStorageKey(nextSession.user, nextBackendAuth);
        nextStored = readStorage(socialKey) || {};
        if (nextBackendAuth && !profileMatchesBackendAuth(nextStored, nextBackendAuth)) {
          clearBackendAuthSession();
          nextBackendAuth = null;
        }
      } else {
        const passwordKey = getCustomStorageKey(null, nextBackendAuth);
        nextStored = readStorage(passwordKey) || {};
      }

      setSession(nextSession);
      setPasswordAuth(nextBackendAuth);
      setStoredProfile(nextStored);
      setAuthLoading(false);
    };

    supabase.auth.getSession().then(({ data }) => {
      if (!mounted) return;
      applySessionState(data?.session ?? null);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      if (!mounted) return;
      applySessionState(nextSession ?? null);
    });

    return () => {
      mounted = false;
      subscription.unsubscribe();
    };
  }, []);

  const userData = useMemo(
    () => mergeUserData(providerProfile, storedProfile || {}),
    [providerProfile, storedProfile]
  );
  const socialProfileKey = useMemo(() => {
    if (!providerProfile.id || providerProfile.provider === "guest" || providerProfile.provider === "password") {
      return "";
    }
    return `${providerProfile.provider}:${providerProfile.id}:${providerProfile.email || ""}`;
  }, [providerProfile.email, providerProfile.id, providerProfile.provider]);
  const hasStoredSocialProfile = Boolean(
    socialProfileKey && storedProfile?.customName && normalizeSpecies(storedProfile?.species)
  );

  useEffect(() => {
    if (!socialProfileKey || hasStoredSocialProfile) {
      return undefined;
    }

    let cancelled = false;
    setSocialProfileLookup({ key: socialProfileKey, status: "checking" });

    const params = new URLSearchParams({
      provider: providerProfile.provider,
      provider_id: providerProfile.id,
    });
    if (providerProfile.email) {
      params.set("email", providerProfile.email);
    }

    fetch(`${API_BASE_URL}/auth/social/profile?${params.toString()}`)
      .then((response) => (response.ok ? response.json() : null))
      .then((payload) => {
        if (cancelled) return;
        if (payload?.exists && payload?.username && normalizeSpecies(payload?.species)) {
          const nextStored = {
            ...(storedProfile || {}),
            customName: payload.username,
            species: normalizeSpecies(payload.species),
            customAvatar: normalizeAvatarValue(payload.avatar_url || storedProfile?.customAvatar || providerProfile.avatar || ""),
          };
          const key = getCustomStorageKey(authUser, passwordAuth);
          writeStorage(key, nextStored);
          setStoredProfile(nextStored);
          setSocialProfileLookup({ key: socialProfileKey, status: "loaded" });
          return;
        }
        setSocialProfileLookup({ key: socialProfileKey, status: "checked" });
      })
      .catch(() => {
        if (!cancelled) {
          setSocialProfileLookup({ key: socialProfileKey, status: "checked" });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [
    authUser,
    hasStoredSocialProfile,
    passwordAuth,
    providerProfile.avatar,
    providerProfile.email,
    providerProfile.id,
    providerProfile.provider,
    socialProfileKey,
    storedProfile,
  ]);

  const needsProfileSetup = useMemo(() => {
    if (!providerProfile.id || providerProfile.provider === "guest" || providerProfile.provider === "password") {
      return false;
    }
    if (hasStoredSocialProfile) {
      return false;
    }
    return socialProfileLookup.key === socialProfileKey && socialProfileLookup.status === "checked";
  }, [hasStoredSocialProfile, providerProfile.id, providerProfile.provider, socialProfileKey, socialProfileLookup]);

  useEffect(() => {
    if (!providerProfile.id || providerProfile.provider === "guest") return undefined;
    if (socialProfileKey && !hasStoredSocialProfile) return undefined;
    if (needsProfileSetup) return undefined;

    let cancelled = false;
    const username =
      userData.name ||
      providerProfile.name ||
      providerProfile.email?.split("@")[0] ||
      `${providerProfile.provider}-${providerProfile.id.slice(0, 8)}`;

    const storedAvatar = normalizeAvatarValue(storedProfile?.customAvatar || "");
    const syncPayload = {
      provider: providerProfile.provider,
      provider_id: providerProfile.id,
      email: providerProfile.email,
      username,
      avatar_url: normalizeAvatarValue(storedAvatar || providerProfile.avatar || userData.avatar || ""),
    };
    const explicitSpecies = normalizeSpecies(storedProfile?.species) || normalizeSpecies(providerProfile.species);
    if (explicitSpecies) {
      syncPayload.species = explicitSpecies;
    }

    const authEpoch = authEpochRef.current;

    fetch(`${API_BASE_URL}/auth/social/sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(syncPayload),
    })
      .then((response) => (response.ok ? response.json() : null))
      .then((payload) => {
        if (cancelled || authEpoch !== authEpochRef.current || !payload?.username) return;
        const responseSpecies = normalizeSpecies(payload.species);
        const responseAvatar = normalizeAvatarValue(payload.avatar_url || "");
        const localAvatar = normalizeAvatarValue(storedProfile?.customAvatar || "");
        const syncedAuth = persistBackendAuthFromSyncPayload(payload, {
          username,
          email: providerProfile.email,
          avatar: responseAvatar || localAvatar || providerProfile.avatar || userData.avatar || "",
          species: responseSpecies || storedProfile?.species || providerProfile.species || userData.species,
        });
        if (syncedAuth) {
          setPasswordAuth((current) => (current?.token === syncedAuth.token ? current : syncedAuth));
        }
        const shouldAdoptSpecies = !normalizeSpecies(storedProfile?.species) && responseSpecies;
        const shouldAdoptAvatar = responseAvatar && (
          !localAvatar ||
          (isUploadedAvatarValue(responseAvatar) && !isUploadedAvatarValue(localAvatar))
        );
        if (shouldAdoptSpecies || shouldAdoptAvatar) {
          const key = getCustomStorageKey(authUser, passwordAuth);
          const nextStored = {
            ...(storedProfile || {}),
          };
          if (shouldAdoptSpecies) nextStored.species = responseSpecies;
          if (shouldAdoptAvatar) nextStored.customAvatar = responseAvatar;
          writeStorage(key, nextStored);
          setStoredProfile(nextStored);
        }
      })
      .catch(() => {
        // Social auth remains usable even if the local backend is offline.
      });

    return () => {
      cancelled = true;
    };
  }, [
    providerProfile.avatar,
    providerProfile.email,
    providerProfile.id,
    providerProfile.name,
    providerProfile.provider,
    providerProfile.species,
    storedProfile?.species,
    storedProfile,
    userData.avatar,
    userData.name,
    userData.species,
    authUser,
    passwordAuth,
    needsProfileSetup,
    socialProfileKey,
    hasStoredSocialProfile,
  ]);

  const persistProfile = useCallback((nextStored) => {
    const key = getCustomStorageKey(authUser, passwordAuth);
    writeStorage(key, nextStored);
    setStoredProfile(nextStored);
  }, [authUser, passwordAuth]);

  const setUserData = useCallback((update) => {
    const previous = storedProfile || {};
    const current = mergeUserData(providerProfile, previous);
    const patch = typeof update === "function" ? update(current) : update;
    const nextSpecies = normalizeSpecies(patch?.species) || current.species || "human";
    const nextStored = {
      species: nextSpecies,
      customName: typeof patch?.name === "string" ? patch.name : previous.customName || current.name || "",
      customAvatar: typeof patch?.avatar === "string"
        ? normalizeAvatarValue(patch.avatar)
        : normalizeAvatarValue(previous.customAvatar || current.avatar || ""),
    };
    const key = getCustomStorageKey(authUser, passwordAuth);
    writeStorage(key, nextStored);
    setStoredProfile(nextStored);

    const username = passwordAuth?.username || current.name || providerProfile.name || nextStored.customName || "";
    const shouldSyncProfile = Boolean(readPasswordAuthSession()?.token);
    if (username && shouldSyncProfile) {
      fetch(`${API_BASE_URL}/profile/${encodeURIComponent(username)}`, {
        method: "PATCH",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          username: nextStored.customName || username,
          avatar_url: normalizeAvatarValue(nextStored.customAvatar || ""),
          species: normalizeSpecies(nextStored.species) || "human",
        }),
      }).catch(() => {
        // Local profile stays usable if backend sync is temporarily unavailable.
      });
    }

    if (passwordAuth?.token) {
      setPasswordAuth((prev) => {
        if (!prev) return prev;
        const nextAuth = {
          ...prev,
          username: nextStored.customName || prev.username,
          avatar: normalizeAvatarValue(nextStored.customAvatar || ""),
          species: normalizeSpecies(nextStored.species) || "human",
        };
        return writeBackendAuthSession(nextAuth) || nextAuth;
      });
    }
  }, [authUser, passwordAuth, providerProfile, storedProfile]);

  const syncSocialProfile = useCallback(async ({ username, species, avatar }) => {
    const cleanUsername = String(username || "").trim();
    const accountSpecies = normalizePrincipalSpecies(species);
    if (!providerProfile.id || providerProfile.provider === "guest" || providerProfile.provider === "password") {
      throw new Error("Social account is not ready.");
    }
    if (!cleanUsername) throw new Error("Choose a username.");
    if (!accountSpecies) throw new Error("Choose Human or ORG. AI delegates are created after signup from account settings.");

    const response = await fetch(`${API_BASE_URL}/auth/social/sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: providerProfile.provider,
        provider_id: providerProfile.id,
        email: providerProfile.email,
        username: cleanUsername,
        avatar_url: normalizeAvatarValue(avatar || storedProfile?.customAvatar || providerProfile.avatar || ""),
        species: accountSpecies,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload?.detail || "Unable to sync your SuperNova identity.");
    }

    const nextStored = {
      ...(storedProfile || {}),
      customName: payload.username || cleanUsername,
      species: normalizeSpecies(payload.species) || accountSpecies,
      customAvatar: normalizeAvatarValue(payload.avatar_url || avatar || storedProfile?.customAvatar || providerProfile.avatar || ""),
    };
    const authPayload = persistBackendAuthFromSyncPayload(payload, {
      username: cleanUsername,
      email: providerProfile.email,
      avatar: nextStored.customAvatar,
      species: accountSpecies,
    });
    if (authPayload) {
      setSession(null);
      setPasswordAuth(authPayload);
    }
    const key = getCustomStorageKey(authUser, passwordAuth);
    writeStorage(key, nextStored);
    setStoredProfile(nextStored);
    return payload;
  }, [authUser, passwordAuth, providerProfile, storedProfile]);

  const saveUserProfile = useCallback(async ({ username, species, avatar }) => {
    const current = mergeUserData(providerProfile, storedProfile || {});
    const currentUsername = passwordAuth?.username || current.name || providerProfile.name || "";
    const cleanUsername = String(username || currentUsername || "").trim();
    const accountSpecies = normalizeSpecies(species) || current.species || "human";
    const nextAvatar = normalizeAvatarValue(avatar || current.avatar || "");
    if (!currentUsername) throw new Error("Current username is missing.");
    if (!cleanUsername) throw new Error("Choose a username.");
    requireBackendAuthSession();

    const response = await fetch(`${API_BASE_URL}/profile/${encodeURIComponent(currentUsername)}`, {
      method: "PATCH",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        username: cleanUsername,
        avatar_url: nextAvatar,
        species: accountSpecies,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload?.detail || "Unable to update profile.");
    }

    const nextStored = {
      ...(storedProfile || {}),
      species: normalizeSpecies(payload.species) || accountSpecies,
      customName: payload.username || cleanUsername,
      customAvatar: normalizeAvatarValue(payload.avatar_url || nextAvatar),
    };
    const key = getCustomStorageKey(authUser, passwordAuth);
    writeStorage(key, nextStored);
    setStoredProfile(nextStored);

    if (passwordAuth?.token) {
      setPasswordAuth((prev) => {
        if (!prev) return prev;
        const nextAuth = {
          ...prev,
          username: nextStored.customName || prev.username,
          avatar: normalizeAvatarValue(nextStored.customAvatar || ""),
          species: normalizeSpecies(nextStored.species) || "human",
        };
        return writeBackendAuthSession(nextAuth) || nextAuth;
      });
    }

    return payload;
  }, [authUser, passwordAuth, providerProfile, storedProfile]);

  const resetCustomProfile = useCallback(() => {
    const key = getCustomStorageKey(authUser, passwordAuth);
    removeStorage(key);
    setStoredProfile({});
  }, [authUser, passwordAuth]);

  const applyPasswordSession = useCallback((payload) => {
    const authPayload = writeBackendAuthSession({
      token: payload.access_token,
      id: payload.user?.id || payload.user?.username,
      username: payload.user?.username || "",
      email: payload.user?.email || "",
      avatar: normalizeAvatarValue(payload.user?.avatar_url || payload.user?.profile_pic || ""),
      species: normalizeSpecies(payload.user?.species) || "human",
    });
    if (!authPayload?.token) {
      throw new Error("Backend session token is missing.");
    }
    setSession(null);
    setPasswordAuth(authPayload);
    const key = getCustomStorageKey(null, authPayload);
    const savedProfile = readStorage(key) || {};
    const savedAvatar = normalizeAvatarValue(savedProfile.customAvatar || "");
    setStoredProfile({
      species: savedProfile.species || authPayload.species,
      customName: savedProfile.customName || authPayload.username,
      customAvatar: normalizeAvatarValue(authPayload.avatar || savedAvatar),
    });
    return authPayload;
  }, []);

  const loginWithPassword = useCallback(async ({ username, password }) => {
    let response = await fetch(`${API_BASE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    let payload = await response.json().catch(() => ({}));

    if (response.status === 404) {
      const formData = new URLSearchParams();
      formData.set("username", username);
      formData.set("password", password);
      response = await fetch(`${API_BASE_URL}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: formData.toString(),
      });
      payload = await response.json().catch(() => ({}));
    }

    if (!response.ok) {
      throw new Error(payload?.detail || "Unable to sign in.");
    }
    return applyPasswordSession(payload);
  }, [applyPasswordSession]);

  const registerWithPassword = useCallback(async ({ username, password, email, species }) => {
    const accountSpecies = normalizePrincipalSpecies(species) || "human";
    const response = await fetch(`${API_BASE_URL}/users/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, email, species: accountSpecies }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload?.detail || "Unable to create account.");
    }
    return loginWithPassword({ username, password });
  }, [loginWithPassword]);

  const loginWithProvider = useCallback(async (provider) => {
    if (!supabase || !isSupabaseConfigured) {
      throw new Error("Supabase social login is not configured yet.");
    }

    const redirectTo = typeof window !== "undefined" ? window.location.origin : undefined;
    const options = {
      redirectTo,
    };

    if (provider === "google") {
      options.queryParams = {
        access_type: "offline",
        prompt: "consent",
      };
    }

    const { error } = await supabase.auth.signInWithOAuth({
      provider,
      options,
    });

    if (error) {
      throw error;
    }
  }, []);

  const signOut = useCallback(async () => {
    authEpochRef.current += 1;
    clearBackendAuthSession();
    setPasswordAuth(null);
    let signOutError = null;

    if (supabase && isSupabaseConfigured) {
      try {
        const { error } = await supabase.auth.signOut();
        signOutError = error;
      } catch (error) {
        signOutError = error;
      }
    }

    setSession(null);
    setStoredProfile(readStorage(GUEST_STORAGE_KEY) || {});
    setSocialProfileLookup({ key: "", status: "idle" });

    if (signOutError) {
      console.warn("SuperNova sign out cleared local session after provider sign-out failed.", signOutError);
    }
  }, []);

  return (
    <UserContext.Provider
      value={{
        userData,
        setUserData,
        defaultAvatar: DEFAULT_AVATAR,
        authLoading,
        authConfigured: isSupabaseConfigured,
        isAuthenticated: Boolean(session?.user || passwordAuth?.token),
        backendAuthReady: Boolean(passwordAuth?.token),
        needsProfileSetup,
        passwordAuth,
        authProvider: userData.provider,
        loginWithProvider,
        loginWithPassword,
        registerWithPassword,
        signOut,
        session,
        persistProfile,
        syncSocialProfile,
        saveUserProfile,
        resetCustomProfile,
      }}
    >
      {children}
    </UserContext.Provider>
  );
}

export function useUser() {
  return useContext(UserContext);
}
