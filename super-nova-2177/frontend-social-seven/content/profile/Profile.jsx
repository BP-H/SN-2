import {
  FaBriefcase,
  FaGithub,
  FaPowerOff,
  FaUser,
} from "react-icons/fa";
import imageCompression from "browser-image-compression";
import { FaFacebookF, FaGoogle } from "react-icons/fa6";
import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  IoCameraOutline,
  IoCheckmark,
  IoClose,
  IoLogInOutline,
  IoMailOutline,
  IoMoonOutline,
  IoShieldCheckmarkOutline,
  IoSunnyOutline,
} from "react-icons/io5";
import { useQueryClient } from "@tanstack/react-query";
import { useUser } from "./UserContext";
import { API_BASE_URL } from "@/utils/apiBase";
import { authHeaders, formatBackendAuthErrorMessage } from "@/utils/authSession";
import { avatarDisplayUrl, normalizeAvatarValue } from "@/utils/avatar";
import { speciesAccentBgClass, speciesAvatarStyle } from "@/utils/species";

const SPECIES = [
  { key: "human", label: "Human", icon: <FaUser /> },
  { key: "company", label: "ORG", icon: <FaBriefcase /> },
];

function publicAccountSpecies(value) {
  return value === "company" ? "company" : "human";
}

function publicAccountSpeciesLabel(value) {
  if (value === "company") return "Organization";
  if (value === "ai") return "AI protocol actor";
  return "Human";
}

const PROVIDERS = [
  { key: "google", label: "Google", icon: <FaGoogle />, color: "#DB4437" },
  { key: "facebook", label: "Facebook", icon: <FaFacebookF />, color: "#4267B2" },
  { key: "github", label: "GitHub", icon: <FaGithub />, color: "#d4d1e1" },
];

function Profile({ setErrorMsg = () => {}, setNotify = () => {}, authIntent = null }) {
  const {
    userData,
    defaultAvatar,
    authLoading,
    authConfigured,
    isAuthenticated,
    loginWithProvider,
    loginWithPassword,
    registerWithPassword,
    saveUserProfile,
    signOut,
    passwordAuth,
  } = useUser();

  const [selectedSpecies, setSelectedSpecies] = useState(userData.species || "human");
  const [avatarUrl, setAvatarUrl] = useState(userData.avatar || "");
  const [profileName, setProfileName] = useState(userData.name || "");
  const [authBusy, setAuthBusy] = useState("");
  const [saveBusy, setSaveBusy] = useState(false);
  const [identityBusy, setIdentityBusy] = useState(false);
  const [theme, setTheme] = useState("light");
  const [authOpen, setAuthOpen] = useState(false);
  const [passwordMode, setPasswordMode] = useState("login");
  const [accountName, setAccountName] = useState("");
  const [accountEmail, setAccountEmail] = useState("");
  const [accountPassword, setAccountPassword] = useState("");
  const [mounted, setMounted] = useState(false);
  const queryClient = useQueryClient();

  useEffect(() => {
    setSelectedSpecies(userData.species || "human");
    setAvatarUrl(userData.avatar || "");
    setProfileName(userData.name || "");
  }, [userData]);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const savedTheme = localStorage.getItem("supernova-theme") || "light";
    setTheme(savedTheme);
  }, []);

  useEffect(() => {
    if (!authIntent || isAuthenticated) return;
    if (typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("supernova:open-account", {
          detail: { mode: authIntent.mode === "login" ? "login" : "create" },
        })
      );
    }
  }, [authIntent, isAuthenticated]);

  const providerLabel = useMemo(() => {
    if (!isAuthenticated) return "Guest";
    return (userData.provider || "account").replace(/^\w/, (char) => char.toUpperCase());
  }, [isAuthenticated, userData.provider]);

  const currentName = userData.name || "";
  const accountUsername = passwordAuth?.username || currentName;
  const accountId = passwordAuth?.id || userData.id || "";
  const avatarPreview = isAuthenticated
    ? avatarDisplayUrl(avatarUrl || userData.avatar, defaultAvatar)
    : defaultAvatar;
  const avatarStyle = speciesAvatarStyle(selectedSpecies || userData.species || "human");
  const openAuth = (mode) => {
    const nextMode = mode === "create" ? "create" : "login";
    if (!isAuthenticated && typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("supernova:open-account", {
          detail: { mode: nextMode },
        })
      );
      return;
    }
    setPasswordMode(nextMode);
    setAuthOpen(true);
  };
  const alternatePasswordMode = passwordMode === "create" ? "login" : "create";
  const passwordSwitchPrompt = passwordMode === "create" ? "Already have an account?" : "Need an account?";
  const passwordSwitchLabel = passwordMode === "create" ? "Sign in" : "Create account";

  async function handleProviderLogin(provider) {
    setErrorMsg([]);
    setNotify([]);
    setAuthBusy(provider);
    try {
      await loginWithProvider(provider);
      setNotify([`Redirecting to ${provider} for login...`]);
    } catch (error) {
      setErrorMsg([formatBackendAuthErrorMessage(error, `Unable to start ${provider} login.`)]);
    } finally {
      setAuthBusy("");
    }
  }

  async function handlePasswordSubmit(event) {
    event.preventDefault();
    const username = accountName.trim();
    const email = accountEmail.trim();
    const password = accountPassword;
    const errors = [];

    if (!username) errors.push("Username is required.");
    if (passwordMode === "create" && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      errors.push("Enter a valid email for account recovery later.");
    }
    if (!password) errors.push("Password is required.");
    if (passwordMode === "create" && password.length < 6) {
      errors.push("Use at least 6 characters for now.");
    }
    if (errors.length) {
      setErrorMsg(errors);
      return;
    }

    setAuthBusy(passwordMode);
    setErrorMsg([]);
    setNotify([]);
    try {
      if (passwordMode === "create") {
        await registerWithPassword({
          username,
          password,
          email,
          species: publicAccountSpecies(selectedSpecies),
        });
        setNotify(["Account created and signed in."]);
      } else {
        await loginWithPassword({ username, password });
        setNotify(["Signed in."]);
      }
      setAccountPassword("");
      setAuthOpen(false);
    } catch (error) {
      setErrorMsg([formatBackendAuthErrorMessage(error, "Account action failed.")]);
    } finally {
      setAuthBusy("");
    }
  }

  async function handleAvatarSelect(event) {
    if (!isAuthenticated) {
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("supernova:open-account", { detail: { mode: "login" } }));
      }
      event.target.value = "";
      return;
    }

    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.type?.startsWith("image/")) {
      setErrorMsg(["Choose an image file for your profile photo."]);
      event.target.value = "";
      return;
    }

    setSaveBusy(true);
    try {
      const previousUsername = currentName || accountUsername || profileName || "";
      let uploadFile = file;
      try {
        uploadFile = await imageCompression(file, {
          maxSizeMB: 0.18,
          maxWidthOrHeight: 384,
          useWebWorker: true,
          initialQuality: 0.82,
        });
      } catch {
        uploadFile = file;
      }

      const formData = new FormData();
      formData.append("file", uploadFile, uploadFile.name || file.name);
      if (accountUsername) {
        formData.append("username", accountUsername);
      }
      if (accountId) {
        formData.append("user_id", String(accountId));
      }
      const response = await fetch(`${API_BASE_URL}/upload-image`, {
        method: "POST",
        headers: authHeaders(),
        body: formData,
      });
      if (!response.ok) throw new Error("Failed to upload avatar.");
      const data = await response.json();
      if (!data?.url) throw new Error("Avatar upload did not return an image URL.");
      const nextAvatar = normalizeAvatarValue(data.url);

      const payload = await saveUserProfile({
        username: profileName || currentName || accountUsername,
        species: publicAccountSpecies(selectedSpecies || userData.species),
        avatar: nextAvatar,
      });
      const savedAvatar = normalizeAvatarValue(payload.avatar_url || nextAvatar);
      const savedUsername = payload.username || profileName || currentName || accountUsername;
      const savedSpecies = payload.species || selectedSpecies || "human";

      setAvatarUrl(savedAvatar);
      setProfileName(savedUsername);
      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("supernova:profile-avatar-updated", {
            detail: { previousUsername, username: savedUsername, avatar: savedAvatar, species: savedSpecies },
          })
        );
      }
      queryClient.invalidateQueries({ queryKey: ["home-feed"] });
      queryClient.invalidateQueries({ queryKey: ["proposals"] });
      queryClient.invalidateQueries({ queryKey: ["user-posts"] });
      queryClient.invalidateQueries({ queryKey: ["public-profile"] });
      queryClient.invalidateQueries({ queryKey: ["desktop-social-users"] });
      queryClient.invalidateQueries({ queryKey: ["desktop-social-graph"] });
      queryClient.invalidateQueries({ queryKey: ["universe-social-graph"] });
      setNotify(["Profile photo updated."]);
    } catch (error) {
      setErrorMsg([formatBackendAuthErrorMessage(error, "Avatar upload failed.")]);
    } finally {
      setSaveBusy(false);
      event.target.value = "";
    }
  }

  async function handleIdentitySave(event) {
    event?.stopPropagation?.();
    if (!isAuthenticated) {
      openAuth("login");
      return;
    }
    const nextName = profileName.trim();
    if (!nextName) {
      setErrorMsg(["Choose a username."]);
      return;
    }
    setIdentityBusy(true);
    setErrorMsg([]);
    try {
      const previousUsername = currentName || accountUsername || profileName || "";
      const payload = await saveUserProfile({
        username: nextName,
        species: publicAccountSpecies(selectedSpecies || userData.species),
        avatar: avatarUrl || userData.avatar || "",
      });
      const savedName = payload.username || nextName;
      const savedSpecies = payload.species || selectedSpecies || "human";
      const savedAvatar = normalizeAvatarValue(payload.avatar_url || avatarUrl || userData.avatar || "");
      setProfileName(savedName);
      setSelectedSpecies(savedSpecies);
      setAvatarUrl(savedAvatar);
      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("supernova:profile-avatar-updated", {
            detail: { previousUsername, username: savedName, avatar: savedAvatar, species: savedSpecies },
          })
        );
      }
      queryClient.invalidateQueries({ queryKey: ["home-feed"] });
      queryClient.invalidateQueries({ queryKey: ["proposals"] });
      queryClient.invalidateQueries({ queryKey: ["user-posts"] });
      queryClient.invalidateQueries({ queryKey: ["public-profile"] });
      queryClient.invalidateQueries({ queryKey: ["desktop-social-users"] });
      queryClient.invalidateQueries({ queryKey: ["desktop-social-graph"] });
      queryClient.invalidateQueries({ queryKey: ["universe-social-graph"] });
      setNotify(["Profile updated."]);
    } catch (error) {
      setErrorMsg([formatBackendAuthErrorMessage(error, "Profile update failed.")]);
    } finally {
      setIdentityBusy(false);
    }
  }

  async function handleSignOut() {
    setAuthBusy("signout");
    try {
      await signOut();
      setNotify(["Signed out successfully."]);
    } catch (error) {
      setErrorMsg([formatBackendAuthErrorMessage(error, "Sign out failed.")]);
    } finally {
      setAuthBusy("");
    }
  }

  function applyTheme(nextTheme) {
    setTheme(nextTheme);
    if (typeof window !== "undefined") {
      localStorage.setItem("supernova-theme", nextTheme);
    }
    document.documentElement.dataset.theme = nextTheme;
  }

  return (
    <div
      className={`profile-compact-card w-full rounded-[1.05rem] p-3 text-[var(--text-black)] ${
        isAuthenticated ? "" : "cursor-pointer"
      }`}
      role={isAuthenticated ? undefined : "button"}
      tabIndex={isAuthenticated ? undefined : 0}
      onClick={() => {
        if (!isAuthenticated) openAuth("login");
      }}
      onKeyDown={(event) => {
        if (!isAuthenticated && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          openAuth("login");
        }
      }}
    >
      <div className="flex items-center gap-3">
        <div className="relative shrink-0">
          <img
            src={avatarPreview}
            alt="Avatar"
            onError={(event) => {
              event.currentTarget.src = defaultAvatar;
            }}
            className="h-14 w-14 rounded-full border object-cover"
            style={avatarStyle}
          />
          {isAuthenticated && (
            <>
              <label
                htmlFor="avatarInputSocialSeven"
                className={`absolute -bottom-1 -right-1 flex h-7 w-7 items-center justify-center rounded-full bg-[var(--pink)] text-white shadow-[var(--shadow-pink)] ${
                  saveBusy ? "pointer-events-none opacity-70" : "cursor-pointer"
                }`}
                title="Upload profile photo"
                onClick={(event) => event.stopPropagation()}
              >
                <IoCameraOutline />
              </label>
              <input
                type="file"
                id="avatarInputSocialSeven"
                accept="image/*"
                className="hidden"
                onChange={handleAvatarSelect}
              />
            </>
          )}
        </div>

        <div className="min-w-0 flex-1">
          <p className="truncate text-[0.98rem] font-black">{isAuthenticated ? currentName : "SuperNova account"}</p>
          <p className="mt-0.5 truncate text-[0.7rem] text-[var(--text-gray-light)]">
            {authLoading ? "Checking account..." : isAuthenticated ? `${providerLabel} account` : "Sign in to sync across devices"}
          </p>
          {!isAuthenticated && (
            <p className="mt-1 text-[0.68rem] font-semibold text-[var(--pink)]">
              Tap to sign in or create an account.
            </p>
          )}
        </div>

        {isAuthenticated ? (
          <button
            type="button"
            onClick={handleSignOut}
            disabled={authBusy === "signout"}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white/[0.07] text-[var(--text-gray-light)] disabled:opacity-50"
            aria-label="Sign out"
          >
            <FaPowerOff />
          </button>
        ) : (
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              openAuth("login");
            }}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--pink)] text-white shadow-[var(--shadow-pink)]"
            aria-label="Sign in"
          >
            <IoLogInOutline />
          </button>
        )}
      </div>

      {isAuthenticated && (
        <div className="mt-3 grid gap-2" onClick={(event) => event.stopPropagation()}>
          <div className="flex items-center gap-2">
            <input
              value={profileName}
              onChange={(event) => setProfileName(event.target.value)}
              className="auth-input h-10 min-w-0 flex-1 rounded-full px-3 text-[0.82rem] outline-none"
              placeholder="Username"
              autoComplete="username"
            />
            <button
              type="button"
              onClick={handleIdentitySave}
              disabled={identityBusy}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--pink)] text-white shadow-[var(--shadow-pink)] disabled:opacity-55"
              aria-label="Save profile"
              title="Save profile"
            >
              <IoCheckmark />
            </button>
          </div>
          <div className="rounded-[0.85rem] bg-white/[0.045] px-3 py-2 text-[0.7rem] leading-4 text-[var(--text-gray-light)]">
            Principal type:{" "}
            <span className="font-bold text-[var(--text-black)]">
              {publicAccountSpeciesLabel(selectedSpecies || userData.species)}
            </span>
            . AI is a protocol actor type; create AI delegates through AI Genesis instead of switching this account into AI.
          </div>
        </div>
      )}

      <div className="mt-3 grid grid-cols-2 gap-2">
        {["dark", "light"].map((mode) => (
          <button
            key={mode}
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              applyTheme(mode);
            }}
            className={`flex h-10 items-center justify-center gap-2 rounded-full px-3 text-[0.74rem] font-semibold capitalize ${
              theme === mode
                ? "bgPink text-white shadow-[var(--shadow-pink)]"
                : "bgGray text-[var(--text-black)]"
            }`}
          >
            {mode === "dark" ? <IoMoonOutline /> : <IoSunnyOutline />}
            {mode}
          </button>
        ))}
      </div>

      {mounted && authOpen && createPortal(
        <div
          className="profile-auth-portal fixed inset-0 z-[2147483000] flex items-center justify-center bg-black/65 px-4 py-[max(1.25rem,env(safe-area-inset-top,0px))] backdrop-blur-sm"
          onClick={() => setAuthOpen(false)}
        >
          <form
            onSubmit={handlePasswordSubmit}
            className="profile-auth-card hide-scrollbar w-full max-w-[24rem] overflow-y-auto rounded-[1.35rem] p-4 shadow-[0_18px_60px_rgba(0,0,0,0.48)]"
            style={{ maxHeight: "calc(100dvh - 2.5rem)" }}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <div>
                <p className="text-[1rem] font-black">SuperNova account</p>
                <p className="auth-muted mt-0.5 text-[0.7rem]">
                  {passwordMode === "create" ? "Choose your username and principal type." : "Sign in to sync across devices."}
                </p>
                <p className="auth-muted mt-2 max-w-[18rem] text-[0.68rem] leading-4">
                  Reviewing is contribution: SuperNova records proposals, votes, reviews, and ratifications without tokens or speculation.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setAuthOpen(false)}
                className="auth-icon-button flex h-9 w-9 items-center justify-center rounded-full"
                aria-label="Close account panel"
              >
                <IoClose />
              </button>
            </div>

            <div className="grid gap-2">
              {PROVIDERS.map((provider) => (
                <button
                  key={provider.key}
                  type="button"
                  onClick={() => handleProviderLogin(provider.key)}
                  disabled={Boolean(authBusy) || !authConfigured}
                  className="auth-provider-button flex h-11 items-center justify-center gap-2 rounded-full px-4 text-[0.82rem] font-bold disabled:opacity-45"
                  title={authConfigured ? `Continue with ${provider.label}` : "Add Supabase environment variables to enable provider login"}
                >
                  <span className="text-[1rem]" style={{ color: provider.color }}>
                    {authBusy === provider.key ? (
                      <span className="block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                    ) : (
                      provider.icon
                    )}
                  </span>
                  Continue with {provider.label}
                </button>
              ))}
            </div>

            <div className="auth-divider my-3 flex items-center gap-3 text-[0.68rem] font-semibold uppercase tracking-[0.18em]">
              <span className="h-px flex-1" />
              <span>Account</span>
              <span className="h-px flex-1" />
            </div>

            <div className="grid gap-2">
              <input
                value={accountName}
                onChange={(event) => setAccountName(event.target.value)}
                className="auth-input h-11 rounded-[0.95rem] px-3 text-[0.86rem] outline-none"
                placeholder="Username"
                autoComplete="username"
              />
              {passwordMode === "create" && (
                <input
                  value={accountEmail}
                  onChange={(event) => setAccountEmail(event.target.value)}
                  className="auth-input h-11 rounded-[0.95rem] px-3 text-[0.86rem] outline-none"
                  placeholder="Email"
                  type="email"
                  autoComplete="email"
                />
              )}
              <input
                value={accountPassword}
                onChange={(event) => setAccountPassword(event.target.value)}
                className="auth-input h-11 rounded-[0.95rem] px-3 text-[0.86rem] outline-none"
                placeholder="Password"
                type="password"
                autoComplete={passwordMode === "create" ? "new-password" : "current-password"}
              />
            </div>

            {passwordMode === "create" && (
              <>
              <div className="mt-3 grid grid-cols-2 gap-2">
                {SPECIES.map((item) => {
                  const selected = selectedSpecies === item.key;
                  return (
                    <button
                      key={item.key}
                      type="button"
                      onClick={() => setSelectedSpecies(item.key)}
                      className={`flex h-10 items-center justify-center gap-1.5 rounded-full text-[0.72rem] font-semibold ${
                        selected ? `${speciesAccentBgClass(item.key)} text-white` : "auth-pill-inactive"
                      }`}
                    >
                      {item.icon}
                      {item.label}
                    </button>
                  );
                })}
              </div>
              <p className="auth-muted mt-2 rounded-[0.85rem] px-3 py-2 text-[0.7rem] leading-5">
                AI remains a protocol species. AI delegates are created after signup through AI Genesis.
              </p>
              </>
            )}

            <button
              type="submit"
              disabled={Boolean(authBusy)}
              className="mt-3 flex h-11 w-full items-center justify-center gap-2 rounded-full bg-[var(--pink)] text-[0.82rem] font-black text-white shadow-[var(--shadow-pink)] disabled:opacity-55"
            >
              {passwordMode === "create" ? <IoMailOutline /> : <IoShieldCheckmarkOutline />}
              {authBusy === passwordMode ? "Working..." : passwordMode === "create" ? "Create account" : "Sign in"}
            </button>
            <p className="auth-muted mt-3 text-center text-[0.72rem] font-semibold">
              {passwordSwitchPrompt}{" "}
              <button
                type="button"
                onClick={() => setPasswordMode(alternatePasswordMode)}
                className="font-black text-[var(--pink)]"
                disabled={Boolean(authBusy)}
              >
                {passwordSwitchLabel}
              </button>
            </p>
            {!authConfigured && (
              <p className="auth-muted mt-2 text-center text-[0.66rem] leading-4">
                Google, Facebook, and GitHub need Supabase env vars and provider redirect URLs. Password accounts still work through the backend.
              </p>
            )}
          </form>
        </div>,
        document.body
      )}
    </div>
  );
}

export default Profile;
