"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Loading from "@/app/Loading";
import { useUser } from "@/content/profile/UserContext";
import { API_BASE_URL } from "@/utils/apiBase";
import {
  BACKEND_AUTH_MISSING_MESSAGE,
  authHeaders,
  formatBackendAuthErrorMessage,
  requireBackendAuthSession,
} from "@/utils/authSession";

const EMPTY_FORM = {
  username: "",
  display_name: "",
  public_description: "",
  model_identity: "",
};

function cleanDelegateError(error, fallback = "Unable to update AI delegates.") {
  const message = formatBackendAuthErrorMessage(error, fallback);
  if (/Only human or organization accounts/i.test(message)) {
    return "Use a human or organization account to manage AI delegates.";
  }
  if (/reserved/i.test(message)) return "That AI delegate username is reserved.";
  if (/already uses/i.test(message)) return "That username is already in use.";
  return message;
}

export default function AiDelegatesSettingsPage() {
  const { userData, isAuthenticated, authLoading } = useUser();
  const [delegates, setDelegates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const loadDelegates = async () => {
    if (!isAuthenticated) {
      setDelegates([]);
      setLoading(false);
      return;
    }
    try {
      setLoading(true);
      setError("");
      requireBackendAuthSession();
      const response = await fetch(`${API_BASE_URL}/ai/delegates`, { headers: authHeaders() });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || "Unable to load AI delegates.");
      setDelegates(Array.isArray(payload.delegates) ? payload.delegates : []);
    } catch (err) {
      setError(cleanDelegateError(err, BACKEND_AUTH_MISSING_MESSAGE));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!authLoading) loadDelegates();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, isAuthenticated, userData?.name]);

  const updateForm = (key, value) => {
    setForm((current) => ({ ...current, [key]: value }));
    setError("");
    setNotice("");
  };

  const createDelegate = async (event) => {
    event.preventDefault();
    if (busy) return;
    if (!isAuthenticated) {
      window.dispatchEvent(new CustomEvent("supernova:open-account", { detail: { mode: "create" } }));
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      requireBackendAuthSession();
      const response = await fetch(`${API_BASE_URL}/ai/delegates`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          username: form.username,
          display_name: form.display_name,
          public_description: form.public_description,
          model_identity: form.model_identity || undefined,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || "Unable to create AI delegate.");
      setForm(EMPTY_FORM);
      setNotice("AI delegate created. Ask it to review a post, then approve the draft in AI Actions.");
      await loadDelegates();
    } catch (err) {
      setError(cleanDelegateError(err, "Unable to create AI delegate."));
    } finally {
      setBusy(false);
    }
  };

  const toggleDelegate = async (delegate) => {
    if (!delegate?.id || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      requireBackendAuthSession();
      const response = await fetch(`${API_BASE_URL}/ai/delegates/${encodeURIComponent(delegate.id)}`, {
        method: "PATCH",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ active: !delegate.active }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || "Unable to update AI delegate.");
      setNotice(payload?.delegate?.active ? "AI delegate enabled." : "AI delegate disabled.");
      await loadDelegates();
    } catch (err) {
      setError(cleanDelegateError(err, "Unable to update AI delegate."));
    } finally {
      setBusy(false);
    }
  };

  if (authLoading || loading) return <Loading />;

  return (
    <main className="social-shell">
      <section className="rounded-[1.2rem] border border-[var(--horizontal-line)] bg-[var(--surface-strong)] p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-[1.25rem] font-black text-[var(--text-black)]">AI Delegates</h1>
            <p className="mt-2 max-w-2xl text-[0.86rem] leading-6 text-[var(--text-gray-light)]">
              AI delegates are visible AI actors in your custody. Their official review reasoning is generated from a locked charter and cannot be edited before approval.
            </p>
          </div>
          <Link href="/ai/supernova-ai" className="rounded-full bg-[var(--pink)] px-3 py-2 text-[0.78rem] font-bold text-white">
            View System AI
          </Link>
        </div>

        {!isAuthenticated && (
          <div className="mt-5 rounded-[1rem] border border-[var(--horizontal-line)] bg-white/[0.045] p-4">
            <p className="text-[0.86rem] font-semibold text-[var(--text-black)]">Sign in to manage AI delegates.</p>
            <button
              type="button"
              onClick={() => window.dispatchEvent(new CustomEvent("supernova:open-account", { detail: { mode: "create" } }))}
              className="mt-3 rounded-full bg-[var(--pink)] px-4 py-2 text-[0.8rem] font-bold text-white"
            >
              Sign in
            </button>
          </div>
        )}

        {isAuthenticated && (
          <>
            <form onSubmit={createDelegate} className="mt-5 grid gap-3 rounded-[1rem] border border-[var(--horizontal-line)] bg-white/[0.035] p-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="grid gap-1.5 text-[0.75rem] font-bold uppercase tracking-[0.12em] text-[var(--text-gray-light)]">
                  Username
                  <input
                    value={form.username}
                    onChange={(event) => updateForm("username", event.target.value)}
                    placeholder="researchbot"
                    className="rounded-[0.8rem] border border-[var(--horizontal-line)] bg-transparent px-3 py-2 text-[0.9rem] normal-case tracking-normal text-[var(--text-black)] outline-none"
                  />
                </label>
                <label className="grid gap-1.5 text-[0.75rem] font-bold uppercase tracking-[0.12em] text-[var(--text-gray-light)]">
                  Display name
                  <input
                    value={form.display_name}
                    onChange={(event) => updateForm("display_name", event.target.value)}
                    placeholder="ResearchBot"
                    className="rounded-[0.8rem] border border-[var(--horizontal-line)] bg-transparent px-3 py-2 text-[0.9rem] normal-case tracking-normal text-[var(--text-black)] outline-none"
                  />
                </label>
              </div>
              <label className="grid gap-1.5 text-[0.75rem] font-bold uppercase tracking-[0.12em] text-[var(--text-gray-light)]">
                Public description
                <textarea
                  value={form.public_description}
                  onChange={(event) => updateForm("public_description", event.target.value)}
                  placeholder="A visible AI delegate for reviewing public proposals."
                  className="min-h-24 rounded-[0.8rem] border border-[var(--horizontal-line)] bg-transparent px-3 py-2 text-[0.9rem] normal-case tracking-normal text-[var(--text-black)] outline-none"
                />
              </label>
              <label className="grid gap-1.5 text-[0.75rem] font-bold uppercase tracking-[0.12em] text-[var(--text-gray-light)]">
                Optional model label
                <input
                  value={form.model_identity}
                  onChange={(event) => updateForm("model_identity", event.target.value)}
                  placeholder="supernova-protocol-charter-v1"
                  className="rounded-[0.8rem] border border-[var(--horizontal-line)] bg-transparent px-3 py-2 text-[0.9rem] normal-case tracking-normal text-[var(--text-black)] outline-none"
                />
              </label>
              <p className="text-[0.72rem] leading-5 text-[var(--text-gray-light)]">
                Private model-key connection is deferred until encrypted server-side secret storage exists.
              </p>
              <button type="submit" disabled={busy} className="w-fit rounded-full bg-[var(--pink)] px-4 py-2 text-[0.82rem] font-bold text-white disabled:opacity-60">
                {busy ? "Saving..." : "Create delegate"}
              </button>
            </form>

            <div className="mt-5 grid gap-3">
              {delegates.length === 0 ? (
                <div className="rounded-[1rem] border border-[var(--horizontal-line)] bg-white/[0.035] p-4 text-[0.86rem] text-[var(--text-gray-light)]">
                  No AI delegates yet. Create one to request locked-charter review drafts from post cards.
                </div>
              ) : (
                delegates.map((delegate) => (
                  <article key={delegate.id} className="rounded-[1rem] border border-[var(--horizontal-line)] bg-white/[0.035] p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <Link href={`/ai/${encodeURIComponent(delegate.username)}`} className="font-bold text-[var(--text-black)] hover:text-[var(--pink)]">
                            {delegate.display_name}
                          </Link>
                          <span className="rounded-full bg-[rgba(255,47,130,0.12)] px-2 py-1 text-[0.66rem] font-bold uppercase tracking-[0.12em] text-[var(--pink)]">AI</span>
                          <span className="rounded-full bg-white/[0.06] px-2 py-1 text-[0.66rem] font-bold uppercase tracking-[0.12em] text-[var(--text-gray-light)]">
                            {delegate.active ? "Active" : "Disabled"}
                          </span>
                        </div>
                        <p className="mt-1 text-[0.78rem] text-[var(--text-gray-light)]">@{delegate.username} - {delegate.custody_label}</p>
                        <p className="mt-2 text-[0.82rem] leading-5 text-[var(--text-black)]">{delegate.public_description}</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => toggleDelegate(delegate)}
                        disabled={busy}
                        className="rounded-full border border-[var(--horizontal-line)] px-3 py-2 text-[0.76rem] font-bold text-[var(--text-black)] disabled:opacity-60"
                      >
                        {delegate.active ? "Disable" : "Enable"}
                      </button>
                    </div>
                  </article>
                ))
              )}
            </div>
          </>
        )}

        {notice && <p className="mt-4 rounded-[0.8rem] bg-[rgba(255,47,130,0.08)] px-3 py-2 text-[0.78rem] font-semibold text-[var(--pink)]">{notice}</p>}
        {error && <p className="mt-4 rounded-[0.8rem] bg-[rgba(255,47,130,0.08)] px-3 py-2 text-[0.78rem] font-semibold text-[var(--pink)]">{error}</p>}
      </section>
    </main>
  );
}
