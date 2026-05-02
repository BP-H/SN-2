"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { FaBriefcase, FaGithub, FaUser } from "react-icons/fa";
import { FaFacebookF, FaGoogle } from "react-icons/fa6";
import {
  IoClose,
  IoMailOutline,
  IoShieldCheckmarkOutline,
} from "react-icons/io5";
import { useUser } from "./UserContext";
import { avatarDisplayUrl } from "@/utils/avatar";
import { formatBackendAuthErrorMessage } from "@/utils/authSession";
import { speciesAccentBgClass, speciesAvatarStyle } from "@/utils/species";

const SPECIES = [
  { key: "human", label: "Human", icon: <FaUser /> },
  { key: "company", label: "ORG", icon: <FaBriefcase /> },
];

const PROVIDERS = [
  { key: "google", label: "Google", icon: <FaGoogle />, color: "#DB4437" },
  { key: "facebook", label: "Facebook", icon: <FaFacebookF />, color: "#4267B2" },
  { key: "github", label: "GitHub", icon: <FaGithub />, color: "#d4d1e1" },
];

export default function AccountModal({ open, initialMode = "login", onClose = () => {} }) {
  const {
    authConfigured,
    defaultAvatar,
    isAuthenticated,
    loginWithProvider,
    loginWithPassword,
    registerWithPassword,
  } = useUser();
  const [mounted, setMounted] = useState(false);
  const [mode, setMode] = useState(initialMode === "login" ? "login" : "create");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [species, setSpecies] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!open) return;
    setMode(initialMode === "login" ? "login" : "create");
    setError("");
  }, [initialMode, open]);

  useEffect(() => {
    if (isAuthenticated && open) onClose();
  }, [isAuthenticated, onClose, open]);

  if (!mounted || !open) return null;
  const avatarStyle = speciesAvatarStyle(species || "human");
  const alternateMode = mode === "create" ? "login" : "create";
  const switchPrompt = mode === "create" ? "Already have an account?" : "Need an account?";
  const switchLabel = mode === "create" ? "Sign in" : "Create account";

  const submit = async (event) => {
    event.preventDefault();
    const nextUsername = username.trim();
    const nextEmail = email.trim();
    const nextPassword = password;
    if (!nextUsername) {
      setError("Choose a username.");
      return;
    }
    if (mode === "create" && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(nextEmail)) {
      setError("Enter a valid email.");
      return;
    }
    if (!nextPassword || (mode === "create" && nextPassword.length < 6)) {
      setError(mode === "create" ? "Use at least 6 password characters." : "Enter your password.");
      return;
    }
    if (mode === "create" && !species) {
      setError("Choose Human or ORG. AI delegates are created after signup from account settings.");
      return;
    }

    setBusy(mode);
    setError("");
    try {
      if (mode === "create") {
        await registerWithPassword({
          username: nextUsername,
          email: nextEmail,
          password: nextPassword,
          species,
        });
      } else {
        await loginWithPassword({ username: nextUsername, password: nextPassword });
      }
      setPassword("");
      onClose();
    } catch (err) {
      setError(formatBackendAuthErrorMessage(err, "Account action failed."));
    } finally {
      setBusy("");
    }
  };

  const providerLogin = async (provider) => {
    setBusy(provider);
    setError("");
    try {
      await loginWithProvider(provider);
    } catch (err) {
      setError(formatBackendAuthErrorMessage(err, `Unable to start ${provider} login.`));
      setBusy("");
    }
  };

  return createPortal(
    <div
      className="profile-auth-portal fixed inset-0 z-[2147483000] flex items-center justify-center bg-black/65 px-4 py-[max(1.25rem,env(safe-area-inset-top,0px))] backdrop-blur-sm"
      onClick={onClose}
    >
      <form
        onSubmit={submit}
        className="profile-auth-card hide-scrollbar w-full max-w-[24rem] overflow-y-auto rounded-[1.35rem] p-4 shadow-[0_18px_60px_rgba(0,0,0,0.48)]"
        style={{ maxHeight: "calc(100dvh - 2.5rem)" }}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <img src={defaultAvatar} alt="" className="h-12 w-12 shrink-0 rounded-full border object-cover" style={avatarStyle} />
            <div className="min-w-0">
              <p className="truncate text-[1rem] font-black">SuperNova account</p>
              <p className="auth-muted mt-0.5 text-[0.7rem]">
                {mode === "create" ? "Choose your username and principal type." : "Sign in to sync across devices."}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="auth-icon-button flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
            aria-label="Close account panel"
          >
            <IoClose />
          </button>
        </div>
        <p className="auth-muted mb-3 rounded-[1rem] px-3 py-2 text-[0.72rem] leading-5">
          SuperNova is nonprofit public-interest infrastructure for contribution records. Create your profile, then review, vote, discuss, ratify, and collaborate. No tokens, equity, payouts, compensation promises, or financial reward guarantees.
        </p>

        <div className="grid gap-2">
          {PROVIDERS.map((provider) => (
            <button
              key={provider.key}
              type="button"
              onClick={() => providerLogin(provider.key)}
              disabled={Boolean(busy) || !authConfigured}
              className="auth-provider-button flex h-11 items-center justify-center gap-2 rounded-full px-4 text-[0.82rem] font-bold disabled:opacity-45"
              title={authConfigured ? `Continue with ${provider.label}` : "Add Supabase environment variables to enable provider login"}
            >
              <span className="text-[1rem]" style={{ color: provider.color }}>{provider.icon}</span>
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
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            className="auth-input h-11 rounded-[0.95rem] px-3 text-[0.86rem] outline-none"
            placeholder="Username"
            autoComplete="username"
          />
          {mode === "create" && (
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="auth-input h-11 rounded-[0.95rem] px-3 text-[0.86rem] outline-none"
              placeholder="Email"
              type="email"
              autoComplete="email"
            />
          )}
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="auth-input h-11 rounded-[0.95rem] px-3 text-[0.86rem] outline-none"
            placeholder="Password"
            type="password"
            autoComplete={mode === "create" ? "new-password" : "current-password"}
          />
        </div>

        {mode === "create" && (
          <div className="mt-3 grid grid-cols-2 gap-2">
            {SPECIES.map((item) => {
              const selected = species === item.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setSpecies(item.key)}
                  className={`flex h-10 items-center justify-center gap-1.5 rounded-full text-[0.72rem] font-semibold ${
                    selected ? `${speciesAccentBgClass(item.key)} text-white` : "auth-pill-inactive"
                  }`}
                >
                  {item.icon}
                  {item.label}
                </button>
              );
            })}
            <p className="auth-muted col-span-2 text-[0.68rem] leading-4">
              AI delegates are created after signup from your account settings.
            </p>
          </div>
        )}

        {error && <p className="auth-error mt-3 rounded-[0.85rem] px-3 py-2 text-[0.76rem]">{error}</p>}

        <button
          type="submit"
          disabled={Boolean(busy)}
          className="mt-3 flex h-11 w-full items-center justify-center gap-2 rounded-full bg-[var(--pink)] text-[0.82rem] font-black text-white shadow-[var(--shadow-pink)] disabled:opacity-55"
        >
          {mode === "create" ? <IoMailOutline /> : <IoShieldCheckmarkOutline />}
          {busy === mode ? "Working..." : mode === "create" ? "Create account" : "Sign in"}
        </button>
        <p className="auth-muted mt-3 text-center text-[0.72rem] font-semibold">
          {switchPrompt}{" "}
          <button
            type="button"
            onClick={() => {
              setError("");
              setMode(alternateMode);
            }}
            className="font-black text-[var(--pink)]"
            disabled={Boolean(busy)}
          >
            {switchLabel}
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
  );
}

export function ProfileSetupModal({ open }) {
  const {
    defaultAvatar,
    userData,
    syncSocialProfile,
    signOut,
  } = useUser();
  const [mounted, setMounted] = useState(false);
  const [username, setUsername] = useState("");
  const [species, setSpecies] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!open) return;
    const fallbackName = (userData?.email || "").split("@")[0] || userData?.name || "";
    setUsername((current) => current || fallbackName.replace(/[^\w.-]+/g, "").slice(0, 40));
    setSpecies((current) => current || "");
    setError("");
  }, [open, userData?.email, userData?.name]);

  if (!mounted || !open) return null;
  const avatarStyle = speciesAvatarStyle(species || userData?.species || "human");

  const submit = async (event) => {
    event.preventDefault();
    const cleanUsername = username.trim();
    if (!cleanUsername) {
      setError("Choose a username.");
      return;
    }
    if (!species) {
      setError("Choose Human or ORG. AI delegates are created after signup from account settings.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await syncSocialProfile({
        username: cleanUsername,
        species,
        avatar: userData?.avatar || "",
      });
    } catch (err) {
      setError(formatBackendAuthErrorMessage(err, "Unable to finish account setup."));
    } finally {
      setBusy(false);
    }
  };

  return createPortal(
    <div className="profile-auth-portal fixed inset-0 z-[2147483000] flex items-center justify-center bg-black/65 px-4 py-[max(1.25rem,env(safe-area-inset-top,0px))] backdrop-blur-sm">
      <form
        onSubmit={submit}
        className="profile-auth-card hide-scrollbar w-full max-w-[24rem] overflow-y-auto rounded-[1.35rem] p-4 shadow-[0_18px_60px_rgba(0,0,0,0.48)]"
        style={{ maxHeight: "calc(100dvh - 2.5rem)" }}
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <img
              src={userData?.avatar ? avatarDisplayUrl(userData.avatar, defaultAvatar) : defaultAvatar}
              alt=""
              className="h-12 w-12 shrink-0 rounded-full border object-cover"
              style={avatarStyle}
            />
            <div className="min-w-0">
              <p className="truncate text-[1rem] font-black">Choose your SuperNova identity</p>
              <p className="auth-muted mt-0.5 text-[0.7rem]">Username and principal type stay editable later.</p>
            </div>
          </div>
        </div>

        <input
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          className="auth-input h-11 w-full rounded-[0.95rem] px-3 text-[0.86rem] outline-none"
          placeholder="Username"
          autoComplete="username"
        />

        <div className="mt-3 grid grid-cols-2 gap-2">
          {SPECIES.map((item) => {
            const selected = species === item.key;
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => setSpecies(item.key)}
                className={`flex h-10 items-center justify-center gap-1.5 rounded-full text-[0.72rem] font-semibold ${
                  selected ? `${speciesAccentBgClass(item.key)} text-white` : "auth-pill-inactive"
                }`}
              >
                {item.icon}
                {item.label}
              </button>
            );
          })}
          <p className="auth-muted col-span-2 text-[0.68rem] leading-4">
            AI delegates are created after signup from your account settings.
          </p>
        </div>

        {error && <p className="auth-error mt-3 rounded-[0.85rem] px-3 py-2 text-[0.76rem]">{error}</p>}

        <button
          type="submit"
          disabled={busy}
          className="mt-3 flex h-11 w-full items-center justify-center gap-2 rounded-full bg-[var(--pink)] text-[0.82rem] font-black text-white shadow-[var(--shadow-pink)] disabled:opacity-55"
        >
          <IoShieldCheckmarkOutline />
          {busy ? "Saving..." : "Continue"}
        </button>
        <button
          type="button"
          onClick={signOut}
          className="auth-muted mt-3 w-full text-center text-[0.72rem] font-semibold"
        >
          Sign out instead
        </button>
      </form>
    </div>,
    document.body
  );
}
