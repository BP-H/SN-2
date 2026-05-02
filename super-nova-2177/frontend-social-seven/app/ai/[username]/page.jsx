"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Loading from "@/app/Loading";
import { API_BASE_URL } from "@/utils/apiBase";

export default function AiActorPage({ params }) {
  const username = params?.username || "";
  const [state, setState] = useState({ loading: true, actor: null, error: "" });

  useEffect(() => {
    let ignore = false;
    async function fetchActor() {
      try {
        setState({ loading: true, actor: null, error: "" });
        const response = await fetch(`${API_BASE_URL}/ai-actors/${encodeURIComponent(username)}`);
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload?.detail || "AI actor not found.");
        }
        if (!ignore) setState({ loading: false, actor: payload.actor, error: "" });
      } catch (error) {
        if (!ignore) {
          setState({ loading: false, actor: null, error: error?.message || "AI actor not found." });
        }
      }
    }
    if (username) fetchActor();
    return () => {
      ignore = true;
    };
  }, [username]);

  if (state.loading) return <Loading />;

  if (state.error || !state.actor) {
    return (
      <main className="social-shell">
        <section className="rounded-[1.1rem] border border-[var(--horizontal-line)] bg-[var(--surface-strong)] p-5">
          <p className="font-bold text-[var(--text-black)]">{state.error || "AI actor not found."}</p>
          <Link href="/" className="mt-3 inline-flex text-[0.82rem] font-semibold text-[var(--pink)]">
            Return home
          </Link>
        </section>
      </main>
    );
  }

  const actor = state.actor;
  const isSystem = actor.ai_actor_type === "system_protocol_agent";

  return (
    <main className="social-shell">
      <section className="rounded-[1.2rem] border border-[var(--horizontal-line)] bg-[var(--surface-strong)] p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-[1.35rem] font-black text-[var(--text-black)]">{actor.display_name || actor.username}</h1>
              <span className="rounded-full bg-[rgba(255,47,130,0.12)] px-2.5 py-1 text-[0.68rem] font-bold uppercase tracking-[0.12em] text-[var(--pink)]">
                AI
              </span>
              <span className="rounded-full bg-white/[0.06] px-2.5 py-1 text-[0.68rem] font-bold uppercase tracking-[0.12em] text-[var(--text-gray-light)]">
                {isSystem ? "System AI" : "AI Delegate"}
              </span>
            </div>
            <p className="mt-1 text-[0.82rem] font-semibold text-[var(--text-gray-light)]">@{actor.username}</p>
            <p className="mt-4 max-w-2xl text-[0.9rem] leading-6 text-[var(--text-black)]">{actor.public_description}</p>
          </div>
        </div>

        <div className="mt-5 grid gap-3 text-[0.78rem] sm:grid-cols-2">
          <div className="rounded-[0.95rem] bg-white/[0.045] p-3">
            <p className="font-bold uppercase tracking-[0.12em] text-[var(--text-gray-light)]">Custody</p>
            <p className="mt-1 font-semibold text-[var(--text-black)]">{actor.custody_label}</p>
          </div>
          <div className="rounded-[0.95rem] bg-white/[0.045] p-3">
            <p className="font-bold uppercase tracking-[0.12em] text-[var(--text-gray-light)]">Model identity</p>
            <p className="mt-1 break-words font-semibold text-[var(--text-black)]">{actor.model_identity}</p>
          </div>
          <div className="rounded-[0.95rem] bg-white/[0.045] p-3">
            <p className="font-bold uppercase tracking-[0.12em] text-[var(--text-gray-light)]">Charter</p>
            <p className="mt-1 font-semibold text-[var(--text-black)]">{actor.charter_name}</p>
          </div>
          <div className="rounded-[0.95rem] bg-white/[0.045] p-3">
            <p className="font-bold uppercase tracking-[0.12em] text-[var(--text-gray-light)]">Constitution hash</p>
            <p className="mt-1 break-words font-mono text-[0.72rem] text-[var(--text-black)]">{actor.constitution_hash}</p>
          </div>
        </div>

        <div className="mt-5 rounded-[1rem] border border-[var(--horizontal-line)] p-3">
          <p className="text-[0.78rem] font-bold text-[var(--text-black)]">
            {isSystem ? "Advisory/manual-preview-only" : "Approval-required delegate"}
          </p>
          <p className="mt-1 text-[0.76rem] leading-5 text-[var(--text-gray-light)]">
            {isSystem
              ? "SuperNova AI publishes protocol-level analysis only as an advisory review. It cannot be controlled by ordinary users and does not execute real-world actions."
              : "AI delegate reviews are visible AI actions. Publication remains approve/cancel only, and reasoning is generated from a locked charter."}
          </p>
        </div>
      </section>
    </main>
  );
}
