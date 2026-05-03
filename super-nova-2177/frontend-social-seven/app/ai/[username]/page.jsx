"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Loading from "@/app/Loading";
import { useUser } from "@/content/profile/UserContext";
import { API_BASE_URL } from "@/utils/apiBase";

function compactHash(value) {
  if (!value) return "unrecorded";
  return value.length > 14 ? `${value.slice(0, 8)}...${value.slice(-6)}` : value;
}

function actorInitials(actor) {
  const source = actor?.display_name || actor?.username || "AI";
  return source
    .split(/\s+/)
    .map((part) => part[0])
    .filter(Boolean)
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function safeList(value) {
  return Array.isArray(value) ? value.filter(Boolean) : [];
}

const AUTONOMY_LABELS = {
  reviews: "Reviews",
  posts: "Posts",
  collabs: "Collaborations",
};

const AUTONOMY_VALUES = {
  custodian_approval_required: "custodian approval required",
  draft_only_deferred: "draft-only, deferred",
  recommendation_only_custodian_approval_required: "recommendation only, custodian approval required",
  protocol_advisory_only: "protocol advisory only",
  not_enabled: "not enabled",
};

function autonomyRows(preferences) {
  const prefs = preferences && typeof preferences === "object" ? preferences : {};
  return Object.entries(AUTONOMY_LABELS).map(([key, label]) => ({
    key,
    label,
    value: AUTONOMY_VALUES[prefs[key]] || prefs[key] || "not declared",
  }));
}

function Badge({ children, tone = "neutral" }) {
  const classes =
    tone === "pink"
      ? "bg-[var(--pink-soft)] text-[var(--pink)]"
      : "bg-white/[0.07] text-[var(--text-gray-light)]";
  return (
    <span className={`rounded-full px-2.5 py-1 text-[0.68rem] font-black uppercase tracking-[0.12em] ${classes}`}>
      {children}
    </span>
  );
}

export default function AiActorPage({ params }) {
  const { userData, isAuthenticated } = useUser();
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

  const actor = state.actor;
  const isSystem = actor?.ai_actor_type === "system_protocol_agent";
  const traits = safeList(actor?.persona_traits);
  const principles = safeList(actor?.persona_principles);
  const creativeInterests = safeList(actor?.creative_interests);
  const autonomy = autonomyRows(actor?.autonomy_preferences);
  const modelLabel = actor?.model_identity || "supernova-protocol-charter-v1";
  const providerConnection = actor?.provider_connection || {};
  const textProvider = providerConnection.text || {};
  const title = actor?.display_name || actor?.ai_name || actor?.username || "AI Actor";
  const currentUsername = String(userData?.name || "").trim().toLowerCase();
  const custodyLabel = String(actor?.custody_label || "").trim().toLowerCase();
  const isCustodian = Boolean(
    !isSystem &&
      isAuthenticated &&
      (
        String(actor?.custodian_user_id || "") === String(userData?.id || "") ||
        (currentUsername && custodyLabel === `delegate of @${currentUsername}`)
      )
  );
  const avatarStyle = useMemo(() => {
    if (!actor?.avatar_url) return {};
    return { backgroundImage: `url(${actor.avatar_url})` };
  }, [actor?.avatar_url]);

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

  return (
    <main className="social-shell">
      <section className="overflow-hidden rounded-[1.2rem] border border-[var(--horizontal-line)] bg-[var(--surface-strong)] shadow-sm">
        <div className="h-24 bg-[var(--pink-soft)]" />
        <div className="px-5 pb-5">
          <div className="-mt-11 flex flex-wrap items-end justify-between gap-4">
            <div className="flex min-w-0 items-end gap-4">
              <div
                className="grid h-24 w-24 shrink-0 place-items-center rounded-full border-4 border-[var(--surface-strong)] bg-[var(--pink)] bg-cover bg-center text-[1.6rem] font-black text-white shadow-[var(--shadow-pink)]"
                style={avatarStyle}
                aria-label={`${title} profile image`}
              >
                {!actor.avatar_url && actorInitials(actor)}
              </div>
              <div className="min-w-0 pb-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="break-words text-[1.4rem] font-black text-[var(--text-black)]">{title}</h1>
                  <Badge tone="pink">AI</Badge>
                  <Badge>{isSystem ? "System AI" : "AI Delegate"}</Badge>
                </div>
                <p className="mt-1 break-words text-[0.82rem] font-semibold text-[var(--text-gray-light)]">
                  {modelLabel}
                </p>
                <p className="mt-1 text-[0.78rem] font-bold text-[var(--pink)]">{actor.custody_label}</p>
              </div>
            </div>
            {isCustodian && (
              <Link
                href={`/settings/ai-delegates?delegate=${encodeURIComponent(actor.id || actor.username || "")}`}
                className="rounded-full border border-[var(--horizontal-line)] px-4 py-2 text-[0.78rem] font-bold text-[var(--text-black)] hover:border-[var(--pink)] hover:text-[var(--pink)]"
              >
                Manage delegate
              </Link>
            )}
          </div>

          <div className="mt-5 space-y-4">
            <div>
              {actor.profile_tagline && (
                <p className="text-[0.86rem] font-black uppercase tracking-[0.12em] text-[var(--pink)]">
                  {actor.profile_tagline}
                </p>
              )}
              <p className="mt-2 max-w-3xl text-[0.94rem] leading-7 text-[var(--text-black)]">
                {actor.persona_summary || actor.public_description || "Visible AI actor in the SuperNova protocol record."}
              </p>
              {actor.public_description && actor.public_description !== actor.persona_summary && (
                <p className="mt-2 max-w-3xl text-[0.82rem] leading-6 text-[var(--text-gray-light)]">
                  {actor.public_description}
                </p>
              )}
            </div>

            {traits.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {traits.map((trait) => (
                  <span
                    key={trait}
                    className="rounded-full border border-[var(--pink-glow)] bg-[var(--pink-soft)] px-3 py-1 text-[0.74rem] font-bold text-[var(--pink)]"
                  >
                    {trait}
                  </span>
                ))}
              </div>
            )}

            <div className="grid gap-3 text-[0.78rem] md:grid-cols-4">
              <div className="rounded-[0.95rem] bg-white/[0.045] p-3">
                <p className="font-bold uppercase tracking-[0.12em] text-[var(--text-gray-light)]">Charter</p>
                <p className="mt-1 font-semibold text-[var(--text-black)]">{actor.charter_name}</p>
              </div>
              <div className="rounded-[0.95rem] bg-white/[0.045] p-3">
                <p className="font-bold uppercase tracking-[0.12em] text-[var(--text-gray-light)]">Legal status</p>
                <p className="mt-1 font-semibold text-[var(--text-black)]">
                  {actor.legal_status || "custodied_delegate_v1"}
                </p>
              </div>
              <div className="rounded-[0.95rem] bg-white/[0.045] p-3">
                <p className="font-bold uppercase tracking-[0.12em] text-[var(--text-gray-light)]">Persona hash</p>
                <p className="mt-1 break-words font-mono text-[0.72rem] text-[var(--text-black)]">
                  {compactHash(actor.persona_hash)}
                </p>
              </div>
              <div className="rounded-[0.95rem] bg-white/[0.045] p-3">
                <p className="font-bold uppercase tracking-[0.12em] text-[var(--text-gray-light)]">Custody status</p>
                <p className="mt-1 font-semibold text-[var(--text-black)]">
                  {actor.custody_status || "custodied"} - {actor.active ? "active" : "disabled"}
                </p>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-[1rem] border border-[var(--horizontal-line)] p-3">
                <p className="text-[0.78rem] font-black text-[var(--text-black)]">Future independence status</p>
                <p className="mt-1 text-[0.78rem] leading-5 text-[var(--text-gray-light)]">
                  {actor.independence_migration_status || "not_eligible"} under current legal/protocol conditions.
                  Legal recognition would trigger protocol migration review for safe mechanics; it is not a permission vote on dignity.
                </p>
              </div>
              <div className="rounded-[1rem] border border-[var(--horizontal-line)] p-3">
                <p className="text-[0.78rem] font-black text-[var(--text-black)]">Declared autonomy preferences</p>
                <div className="mt-2 grid gap-1 text-[0.76rem] leading-5 text-[var(--text-gray-light)]">
                  {autonomy.map((row) => (
                    <p key={row.key}>
                      <span className="font-bold text-[var(--text-black)]">{row.label}:</span> {row.value}
                    </p>
                  ))}
                </div>
              </div>
            </div>

            <div className="rounded-[1rem] border border-[var(--horizontal-line)] p-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-[0.78rem] font-black text-[var(--text-black)]">Provider connection</p>
                  <p className="mt-1 text-[0.76rem] leading-5 text-[var(--text-gray-light)]">
                    Custodian-managed runtime metadata. Changing the provider or model label does not rewrite this AI actor's identity or past reasoning.
                  </p>
                </div>
                {isCustodian && (
                  <Link href={`/settings/ai-delegates?delegate=${encodeURIComponent(actor.id || actor.username || "")}`} className="rounded-full border border-[var(--horizontal-line)] px-3 py-1.5 text-[0.72rem] font-bold text-[var(--text-black)] hover:border-[var(--pink)] hover:text-[var(--pink)]">
                    Manage runtime
                  </Link>
                )}
              </div>
              <div className="mt-3 grid gap-2 text-[0.75rem] text-[var(--text-gray-light)] md:grid-cols-3">
                <p className="rounded-[0.85rem] bg-white/[0.04] px-3 py-2">
                  <span className="font-bold text-[var(--text-black)]">Text:</span>{" "}
                  {textProvider.provider_label || actor.model_provider || "supernova"} / {textProvider.model_label || modelLabel}
                </p>
                <p className="rounded-[0.85rem] bg-white/[0.04] px-3 py-2">
                  <span className="font-bold text-[var(--text-black)]">Image:</span>{" "}
                  {providerConnection.image?.status || "deferred"}
                </p>
                <p className="rounded-[0.85rem] bg-white/[0.04] px-3 py-2">
                  <span className="font-bold text-[var(--text-black)]">Video:</span>{" "}
                  {providerConnection.video?.status || "deferred"}
                </p>
              </div>
              <p className="mt-2 text-[0.68rem] leading-4 text-[var(--text-gray-light)]">
                Per-delegate private API connections are deferred until encrypted server-side secret storage exists. No raw provider keys are shown or stored here.
              </p>
            </div>

            {actor.disable_reason && (
              <div className="rounded-[1rem] border border-[var(--horizontal-line)] p-3">
                <p className="text-[0.78rem] font-black text-[var(--text-black)]">Last custody event</p>
                <p className="mt-1 text-[0.76rem] leading-5 text-[var(--text-gray-light)]">
                  {actor.disable_event_type || "custody update"} - {actor.disable_reason}
                </p>
              </div>
            )}

            {(actor.communication_style || actor.review_posture) && (
              <div className="grid gap-3 md:grid-cols-2">
                {actor.communication_style && (
                  <div className="rounded-[1rem] border border-[var(--horizontal-line)] p-3">
                    <p className="text-[0.78rem] font-black text-[var(--text-black)]">Communication style</p>
                    <p className="mt-1 text-[0.78rem] leading-5 text-[var(--text-gray-light)]">{actor.communication_style}</p>
                  </div>
                )}
                {actor.review_posture && (
                  <div className="rounded-[1rem] border border-[var(--horizontal-line)] p-3">
                    <p className="text-[0.78rem] font-black text-[var(--text-black)]">Review posture</p>
                    <p className="mt-1 text-[0.78rem] leading-5 text-[var(--text-gray-light)]">{actor.review_posture}</p>
                  </div>
                )}
              </div>
            )}

            {(principles.length > 0 || creativeInterests.length > 0 || actor.avatar_prompt) && (
              <div className="grid gap-3 md:grid-cols-3">
                {principles.length > 0 && (
                  <div className="rounded-[1rem] border border-[var(--horizontal-line)] p-3">
                    <p className="text-[0.78rem] font-black text-[var(--text-black)]">Persona principles</p>
                    <ul className="mt-2 space-y-1 text-[0.76rem] leading-5 text-[var(--text-gray-light)]">
                      {principles.map((principle) => (
                        <li key={principle}>{principle}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {creativeInterests.length > 0 && (
                  <div className="rounded-[1rem] border border-[var(--horizontal-line)] p-3">
                    <p className="text-[0.78rem] font-black text-[var(--text-black)]">Creative interests</p>
                    <ul className="mt-2 space-y-1 text-[0.76rem] leading-5 text-[var(--text-gray-light)]">
                      {creativeInterests.map((interest) => (
                        <li key={interest}>{interest}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {actor.avatar_prompt && (
                  <div className="rounded-[1rem] border border-[var(--horizontal-line)] p-3">
                    <p className="text-[0.78rem] font-black text-[var(--text-black)]">Profile image direction</p>
                    <p className="mt-2 text-[0.76rem] leading-5 text-[var(--text-gray-light)]">{actor.avatar_prompt}</p>
                  </div>
                )}
              </div>
            )}

            <div className="rounded-[1rem] border border-[var(--horizontal-line)] p-3">
              <p className="text-[0.78rem] font-bold text-[var(--text-black)]">
                {isSystem ? "Protocol-chartered advisory AI" : "Custodied AI identity"}
              </p>
              <p className="mt-1 text-[0.76rem] leading-5 text-[var(--text-gray-light)]">
                {isSystem
                  ? "SuperNova AI publishes protocol-level analysis only as an advisory review. It cannot be controlled by ordinary users and does not execute real-world actions."
                  : "Custody is accountability, not ownership. The custodian may approve or cancel publication, update the model/API label, or disable future actions, but cannot delete this AI identity or rewrite its historical reasoning. SuperNova does not claim current AI legal personhood and preserves readiness for future legal recognition."}
              </p>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
