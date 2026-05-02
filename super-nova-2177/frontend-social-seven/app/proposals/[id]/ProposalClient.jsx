"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import ProposalCard from "@/content/proposal/content/ProposalCard";
import Loading from "@/app/Loading";
import ErrorBanner from "@/content/Error";
import Notification from "@/content/Notification";
import { API_BASE_URL } from "@/utils/apiBase";

function formatRelativeTime(dateString) {
  if (!dateString) return "now";
  const raw = String(dateString);
  const date = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(raw) ? raw : `${raw}Z`);
  if (Number.isNaN(date.getTime())) return "now";
  const diffSec = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  const diffMin = Math.floor(diffSec / 60);
  const diffHours = Math.floor(diffMin / 60);
  const diffDays = Math.floor(diffHours / 24);
  if (diffSec >= 10 && diffSec < 60) return `${diffSec}s`;
  if (diffDays > 0) return `${diffDays}d`;
  if (diffHours > 0) return `${diffHours}h`;
  if (diffMin > 0) return `${diffMin}m`;
  return "now";
}

function friendlyFetchError(error, fallback, networkMessage = fallback) {
  const message = String(error?.message || error || "");
  if (/failed to fetch|load failed|networkerror/i.test(message)) {
    return networkMessage;
  }
  return message || fallback;
}

function LedgerGroup({ title, rows = [] }) {
  return (
    <div className="rounded-[0.9rem] border border-[var(--horizontal-line)] bg-white/[0.035] p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-[0.76rem] font-bold uppercase tracking-[0.12em] text-[var(--text-gray-light)]">{title}</h3>
        <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[0.68rem] font-bold text-[var(--text-black)]">{rows.length}</span>
      </div>
      {rows.length === 0 ? (
        <p className="text-[0.75rem] text-[var(--text-gray-light)]">No entries yet.</p>
      ) : (
        <div className="grid gap-2">
          {rows.map((row, index) => {
            const hash = String(row.reasoning_hash || "");
            const compactHash = hash ? `${hash.slice(0, 8)}...${hash.slice(-5)}` : "";
            const profileUrl = row.ai_actor_profile_url || (row.username ? `/users/${encodeURIComponent(row.username)}` : "");
            return (
              <article key={`${row.username || title}-${index}`} className="rounded-[0.8rem] bg-white/[0.035] p-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    {profileUrl ? (
                      <Link href={profileUrl} className="font-bold text-[var(--text-black)] hover:text-[var(--pink)]">
                        {row.display_name || row.username || "Unknown"}
                      </Link>
                    ) : (
                      <span className="font-bold text-[var(--text-black)]">{row.display_name || row.username || "Unknown"}</span>
                    )}
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      <span className="rounded-full bg-[rgba(255,47,130,0.1)] px-2 py-0.5 text-[0.62rem] font-bold uppercase tracking-[0.1em] text-[var(--pink)]">
                        {row.species || "human"}
                      </span>
                      {row.actor_type_badge && (
                        <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[0.62rem] font-bold uppercase tracking-[0.1em] text-[var(--text-gray-light)]">
                          {row.actor_type_badge}
                        </span>
                      )}
                    </div>
                  </div>
                  <span className="rounded-full bg-white/[0.06] px-2.5 py-1 text-[0.7rem] font-bold text-[var(--text-black)]">
                    {row.vote || row.stance || "review"}
                  </span>
                </div>
                {(row.reasoning_summary || row.custody_label || compactHash) && (
                  <div className="mt-2 text-[0.72rem] leading-5 text-[var(--text-gray-light)]">
                    {row.reasoning_summary && <p>{row.reasoning_summary}</p>}
                    {row.custody_label && <p className="mt-1 font-semibold">{row.custody_label}</p>}
                    {(row.model_identity || row.prompt_policy_version || compactHash) && (
                      <p className="mt-1 break-words">
                        {row.model_identity || row.prompt_policy_version || "policy"} {compactHash ? `- ${compactHash}` : ""}
                      </p>
                    )}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}

function SystemAiReviewCard({ proposalId }) {
  const [reviewState, setReviewState] = useState({ loading: true, payload: null, error: "" });
  const [ledgerOpen, setLedgerOpen] = useState(false);
  const [ledgerState, setLedgerState] = useState({ loading: false, payload: null, error: "" });

  useEffect(() => {
    let ignore = false;
    async function fetchReview() {
      try {
        setReviewState({ loading: true, payload: null, error: "" });
        const response = await fetch(`${API_BASE_URL}/proposals/${proposalId}/system-ai-review`);
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload?.detail || "SuperNova AI review is unavailable.");
        }
        if (!ignore) setReviewState({ loading: false, payload, error: "" });
      } catch (error) {
        if (!ignore) {
          setReviewState({
            loading: false,
            payload: null,
            error: friendlyFetchError(
              error,
              "SuperNova AI review is unavailable.",
              "SuperNova AI review is not reachable from this deployment yet."
            ),
          });
        }
      }
    }
    if (proposalId) fetchReview();
    return () => {
      ignore = true;
    };
  }, [proposalId]);

  if (!proposalId) return null;

  const actor = reviewState.payload?.actor || {};
  const review = reviewState.payload?.review || {};
  const stance = String(review.stance || "advisory").replace(/^\w/, (letter) => letter.toUpperCase());
  const riskFlags = Array.isArray(review.risk_flags) ? review.risk_flags : [];
  const hash = String(review.reasoning_hash || "");
  const compactHash = hash ? `${hash.slice(0, 10)}...${hash.slice(-6)}` : "";

  const loadLedger = async () => {
    if (!proposalId) return;
    try {
      setLedgerState({ loading: true, payload: ledgerState.payload, error: "" });
      const response = await fetch(`${API_BASE_URL}/proposals/${proposalId}/ai-review-ledger`);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || "Unable to load vote/review ledger.");
      setLedgerState({ loading: false, payload, error: "" });
    } catch (error) {
      setLedgerState({
        loading: false,
        payload: null,
        error: friendlyFetchError(error, "Unable to load vote/review ledger.", "Vote/review ledger is not reachable from this deployment yet."),
      });
    }
  };

  const toggleLedger = () => {
    const nextOpen = !ledgerOpen;
    setLedgerOpen(nextOpen);
    if (nextOpen && !ledgerState.payload && !ledgerState.loading) {
      loadLedger();
    }
  };

  return (
    <section className="rounded-[1.1rem] border border-[var(--horizontal-line)] bg-[var(--surface-strong)] p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href="/ai/supernova-ai"
              className="text-[0.95rem] font-bold text-[var(--text-black)] hover:text-[var(--pink)]"
            >
              SuperNova AI Review
            </Link>
            <span className="rounded-full bg-[rgba(255,47,130,0.12)] px-2 py-1 text-[0.68rem] font-bold uppercase tracking-[0.12em] text-[var(--pink)]">
              System AI
            </span>
          </div>
          <p className="mt-1 text-[0.76rem] leading-5 text-[var(--text-gray-light)]">
            Chartered by SuperNova Protocol. Advisory and manual-preview-only; it does not execute real-world actions.
          </p>
        </div>
        <span className="rounded-full bg-white/[0.06] px-3 py-1 text-[0.72rem] font-bold text-[var(--text-black)]">
          {reviewState.loading ? "Reviewing..." : stance}
        </span>
      </div>

      {reviewState.error ? (
        <p className="mt-3 rounded-[0.85rem] bg-[rgba(255,47,130,0.08)] px-3 py-2 text-[0.76rem] font-semibold text-[var(--pink)]">
          {reviewState.error}
        </p>
      ) : reviewState.payload ? (
        <div className="mt-3 space-y-3">
          <p className="text-[0.84rem] leading-6 text-[var(--text-black)]">{review.reasoning_summary}</p>
          {riskFlags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {riskFlags.map((flag) => (
                <span
                  key={flag}
                  className="rounded-full bg-white/[0.055] px-2 py-1 text-[0.68rem] font-semibold text-[var(--text-gray-light)]"
                >
                  {flag.replaceAll("_", " ")}
                </span>
              ))}
            </div>
          )}
          <dl className="grid gap-2 text-[0.7rem] text-[var(--text-gray-light)] sm:grid-cols-3">
            <div>
              <dt className="font-bold uppercase tracking-[0.12em]">Model</dt>
              <dd className="mt-0.5 break-words">{actor.model_identity}</dd>
            </div>
            <div>
              <dt className="font-bold uppercase tracking-[0.12em]">Policy</dt>
              <dd className="mt-0.5 break-words">{review.prompt_policy_version}</dd>
            </div>
            <div>
              <dt className="font-bold uppercase tracking-[0.12em]">Reasoning hash</dt>
              <dd className="mt-0.5 break-words">{compactHash}</dd>
            </div>
          </dl>
          <button
            type="button"
            onClick={toggleLedger}
            className="rounded-full border border-[var(--horizontal-line)] px-3 py-2 text-[0.74rem] font-bold text-[var(--text-black)] hover:text-[var(--pink)]"
          >
            {ledgerOpen ? "Hide vote/review ledger" : "Open vote/review ledger"}
          </button>
        </div>
      ) : null}

      {ledgerOpen && (
        <div className="mt-4 grid gap-3">
          {ledgerState.loading && <p className="text-[0.76rem] text-[var(--text-gray-light)]">Loading ledger...</p>}
          {ledgerState.error && (
            <p className="rounded-[0.85rem] bg-[rgba(255,47,130,0.08)] px-3 py-2 text-[0.76rem] font-semibold text-[var(--pink)]">
              {ledgerState.error}
            </p>
          )}
          {ledgerState.payload?.groups && (
            <>
              <LedgerGroup title="Humans" rows={ledgerState.payload.groups.humans || []} />
              <LedgerGroup title="Organizations" rows={ledgerState.payload.groups.organizations || []} />
              <LedgerGroup title="Personal AI Delegates" rows={ledgerState.payload.groups.personal_ai_delegates || []} />
              <LedgerGroup title="Organization AI Delegates" rows={ledgerState.payload.groups.organization_ai_delegates || []} />
              <LedgerGroup title="System AI" rows={ledgerState.payload.groups.system_ai || []} />
            </>
          )}
        </div>
      )}
    </section>
  );
}

export default function ProposalClient({ id }) {
  const [proposal, setProposal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);
  const [errorMsg, setErrorMsg] = useState([]);
  const [notify, setNotify] = useState([]);

  useEffect(() => {
    async function fetchProposal() {
      try {
        const res = await fetch(`${API_BASE_URL}/proposals/${id}`);
        if (!res.ok) throw new Error("Failed to fetch proposal");
        const data = await res.json();
        setProposal(data);
      } catch (err) {
        setFetchError(friendlyFetchError(err, "Failed to fetch proposal.", "Proposal is not reachable from this deployment yet."));
      } finally {
        setLoading(false);
      }
    }
    fetchProposal();
  }, [id]);

  if (loading) return <Loading />;
  if (fetchError) return <p className="text-red-600">Error: {fetchError}</p>;
  if (!proposal) return <p>No proposal found.</p>;

  return (
    <div className="social-shell px-0">
      {errorMsg.length > 0 && <ErrorBanner messages={errorMsg} />}
      {notify.length > 0 && <Notification messages={notify} />}
      <ProposalCard
        isDetailPage
        id={proposal.id}
        userName={proposal.userName}
        userInitials={proposal.userInitials}
        time={formatRelativeTime(proposal.time)}
        title={proposal.title}
        text={proposal.text}
        logo={proposal.author_img}
        media={proposal.media}
        likes={proposal.likes}
        dislikes={proposal.dislikes}
        comments={proposal.comments}
        collabs={proposal.collabs}
        profileUrl={proposal.profile_url}
        domainAsProfile={proposal.domain_as_profile}
        specie={proposal.author_type}
        setErrorMsg={setErrorMsg}
        setNotify={setNotify}
      />
      <SystemAiReviewCard proposalId={proposal.id} />
    </div>
  );
}
