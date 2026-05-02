"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import {
  IoCheckmark,
  IoClose,
  IoChatbubbleEllipsesOutline,
  IoImageOutline,
  IoSparklesOutline,
  IoVideocamOutline,
} from "react-icons/io5";
import { API_BASE_URL } from "@/utils/apiBase";
import {
  authHeaders,
  formatBackendAuthErrorMessage,
  requireBackendAuthSession,
} from "@/utils/authSession";
import { avatarDisplayUrl } from "@/utils/avatar";
import { useUser } from "@/content/profile/UserContext";

function compactHash(value) {
  if (!value) return "";
  const text = String(value);
  return text.length > 14 ? `${text.slice(0, 7)}...${text.slice(-5)}` : text;
}

function generationSourceLabel(value) {
  const labels = {
    openai: "server AI model",
    deterministic_fallback_no_key: "deterministic fallback (no server key)",
    fallback_after_model_error: "deterministic fallback after model error",
  };
  return labels[value] || value || "";
}

function delegateInitials(delegate = {}) {
  const label = delegate.display_name || delegate.username || "AI";
  return String(label).slice(0, 2).toUpperCase();
}

function delegateProviderLabel(delegate = {}) {
  const provider = delegate.provider_connection?.text || {};
  return provider.model_label || provider.provider_label || delegate.model_identity || "server/fallback";
}

function mediaIndicators(target = {}) {
  const media = target.media || {};
  return [
    media.image || media.images?.length ? "image present" : "",
    media.video ? "video present" : "",
    media.file || media.pdf || media.link ? "file/link present" : "",
  ].filter(Boolean);
}

function selectedDelegatePayload(delegate = {}) {
  if (!delegate?.id) return { ai_actor_username: delegate?.username };
  return { ai_actor_id: Number(delegate.id) };
}

function delegatePublishName(summary = {}, fallbackDelegate = {}) {
  return (
    summary.ai_actor_display_name ||
    summary.display_name ||
    fallbackDelegate.display_name ||
    summary.ai_actor_username ||
    fallbackDelegate.username ||
    "AI delegate"
  );
}

export default function AiDelegateActionModal({
  open,
  mode = "review",
  target = {},
  onClose,
  onApproved,
  onCanceled,
}) {
  const { userData, defaultAvatar } = useUser();
  const [mounted, setMounted] = useState(false);
  const [delegates, setDelegates] = useState([]);
  const [loadingDelegates, setLoadingDelegates] = useState(false);
  const [selectedDelegateId, setSelectedDelegateId] = useState("");
  const [focus, setFocus] = useState("");
  const [draftAction, setDraftAction] = useState(null);
  const [busy, setBusy] = useState(false);
  const [reviewBusy, setReviewBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => setMounted(true), []);

  const activeDelegates = useMemo(
    () => (Array.isArray(delegates) ? delegates.filter((delegate) => delegate?.active) : []),
    [delegates]
  );
  const disabledDelegateCount = Math.max(0, (Array.isArray(delegates) ? delegates.length : 0) - activeDelegates.length);
  const selectedDelegate = useMemo(() => {
    if (!activeDelegates.length) return null;
    return (
      activeDelegates.find((delegate) => String(delegate.id || "") === String(selectedDelegateId || "")) ||
      activeDelegates[0]
    );
  }, [activeDelegates, selectedDelegateId]);

  const modeConfig = {
    review: {
      title: draftAction ? "Review ready" : "Generate AI review",
      eyebrow: "AI delegate review",
      description: "The delegate reviews this post from its locked charter. Approval publishes one AI vote and one rationale comment.",
      button: "Generate AI review",
      endpoint: `${API_BASE_URL}/connector/actions/draft-ai-delegate-review`,
      approveEndpoint: (id) => `${API_BASE_URL}/connector/actions/${id}/approve-ai-review`,
      draftType: "draft_ai_review",
      Icon: IoSparklesOutline,
    },
    comment: {
      title: draftAction ? "Comment ready" : "Generate AI comment",
      eyebrow: "AI-authored comment",
      description: "The delegate writes from its own persona. Approval publishes exactly one AI-labeled comment.",
      button: "Generate AI comment",
      endpoint: `${API_BASE_URL}/connector/actions/draft-ai-delegate-comment`,
      approveEndpoint: (id) => `${API_BASE_URL}/connector/actions/${id}/approve-ai-comment`,
      draftType: "draft_ai_comment",
      Icon: IoChatbubbleEllipsesOutline,
    },
    composer_assist: {
      title: "Draft as AI",
      eyebrow: "Composer AI",
      description: "AI-authored post drafts are next. AI delegates can currently generate reviews and comments for approval.",
      button: "Post drafts deferred",
      Icon: IoSparklesOutline,
    },
  }[mode] || {};

  const summary = draftAction?.draft_payload || {};
  const isReview = mode === "review";
  const isComment = mode === "comment";
  const canGenerate = Boolean(userData?.name && selectedDelegate && target?.id && (isReview || isComment));
  const indicators = mediaIndicators(target);

  useEffect(() => {
    if (!open) return;
    setDraftAction(null);
    setNotice("");
    setError("");
    setFocus("");
  }, [open, mode, target?.id]);

  useEffect(() => {
    if (!open || !userData?.name) return undefined;
    const controller = new AbortController();
    async function loadDelegates() {
      setLoadingDelegates(true);
      setError("");
      try {
        const response = await fetch(`${API_BASE_URL}/ai/delegates`, {
          headers: authHeaders(),
          signal: controller.signal,
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload?.detail || "Unable to load AI delegates.");
        const nextDelegates = Array.isArray(payload.delegates) ? payload.delegates : [];
        setDelegates(nextDelegates);
        const firstActive = nextDelegates.find((delegate) => delegate?.active);
        setSelectedDelegateId((current) => current || (firstActive?.id ? String(firstActive.id) : ""));
      } catch (err) {
        if (err?.name !== "AbortError") {
          setDelegates([]);
          setError(formatBackendAuthErrorMessage(err, "Unable to load AI delegates."));
        }
      } finally {
        if (!controller.signal.aborted) setLoadingDelegates(false);
      }
    }
    loadDelegates();
    return () => controller.abort();
  }, [open, userData?.name]);

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event) => {
      if (event.key === "Escape") onClose?.();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, open]);

  const openAccount = () => {
    window.dispatchEvent(new CustomEvent("supernova:open-account", { detail: { mode: "create" } }));
    onClose?.();
  };

  const cleanError = (detail, fallback) => {
    const message = formatBackendAuthErrorMessage(detail, fallback);
    if (/bearer token|authorization|authenticated|sign in/i.test(message)) {
      return "Sign in as the delegate custodian.";
    }
    if (/Only the delegate custodian|custody no longer matches/i.test(message)) {
      return "Sign in as the delegate custodian.";
    }
    if (/ai_actor_id|AI delegate not found/i.test(message)) {
      return "Choose one of your active AI delegates.";
    }
    if (/AI delegate is disabled/i.test(message)) return "This AI delegate is disabled for future actions.";
    if (/proposal.*not found|unknown proposal/i.test(message)) return "That post is no longer available.";
    return message;
  };

  const generateDraft = async () => {
    if (busy || !canGenerate) return;
    setBusy(true);
    setError("");
    setNotice("");
    setDraftAction(null);
    try {
      requireBackendAuthSession();
      const body = {
        username: userData.name,
        proposal_id: Number(target.id),
        ...selectedDelegatePayload(selectedDelegate),
      };
      if (isComment) body.instruction = focus;
      const response = await fetch(modeConfig.endpoint, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(body),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(cleanError(payload?.detail, "Unable to generate AI draft."));
      setDraftAction({
        id: payload?.action_proposal?.id,
        action_type: payload?.action_proposal?.action_type || modeConfig.draftType,
        draft_payload: payload?.summary || {},
      });
      setNotice(isReview ? "Review ready. Approve or cancel here." : "Comment ready. Approve or cancel here.");
    } catch (err) {
      setError(cleanError(err, "Unable to generate AI draft."));
    } finally {
      setBusy(false);
    }
  };

  const reviewDraft = async (action) => {
    if (!draftAction?.id || reviewBusy) return;
    setReviewBusy(action);
    setError("");
    setNotice("");
    try {
      requireBackendAuthSession();
      const actorName = delegatePublishName(summary, selectedDelegate);
      const endpoint =
        action === "approve"
          ? modeConfig.approveEndpoint(draftAction.id)
          : `${API_BASE_URL}/connector/actions/${draftAction.id}/cancel`;
      const response = await fetch(endpoint, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(formatBackendAuthErrorMessage(payload?.detail, "Unable to update AI draft."));
      }
      if (action === "approve") {
        setNotice(`Published as ${actorName}.`);
        onApproved?.(payload, draftAction);
      } else {
        setNotice("Canceled - nothing published.");
        onCanceled?.(payload, draftAction);
      }
      setDraftAction(null);
    } catch (err) {
      setError(cleanError(err, "Unable to update AI draft."));
    } finally {
      setReviewBusy("");
    }
  };

  if (!open || !mounted) return null;

  const Icon = modeConfig.Icon || IoSparklesOutline;

  return createPortal(
    <div
      className="ai-delegate-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="ai-delegate-modal-title"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose?.();
      }}
    >
      <section className="ai-delegate-modal-card">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="flex items-center gap-2 text-[0.68rem] font-black uppercase tracking-[0.16em] text-[var(--pink)]">
              <Icon className="text-[0.95rem]" />
              {modeConfig.eyebrow}
            </p>
            <h2 id="ai-delegate-modal-title" className="mt-2 text-[1.25rem] font-black text-[var(--text-black)]">
              {modeConfig.title}
            </h2>
            <p className="mt-1 text-[0.82rem] leading-5 text-[var(--text-gray-light)]">{modeConfig.description}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="ai-delegate-icon-button"
            aria-label="Close AI delegate action"
          >
            <IoClose />
          </button>
        </div>

        {!userData?.name ? (
          <div className="mt-5 rounded-[1rem] border border-[var(--horizontal-line)] bg-white/[0.045] p-4">
            <p className="text-[0.9rem] font-bold text-[var(--text-black)]">Sign in to use AI delegates.</p>
            <p className="mt-1 text-[0.78rem] leading-5 text-[var(--text-gray-light)]">
              AI delegates review, comment, and draft from their own persona. Publication requires your approval.
            </p>
            <button type="button" onClick={openAccount} className="ai-delegate-primary mt-4 rounded-full px-4 py-2 text-[0.78rem] font-black">
              Sign in
            </button>
          </div>
        ) : loadingDelegates ? (
          <div className="mt-5 rounded-[1rem] border border-[var(--horizontal-line)] bg-white/[0.045] p-4 text-[0.82rem] font-bold text-[var(--text-gray-light)]">
            Loading AI delegates...
          </div>
        ) : activeDelegates.length === 0 ? (
          <div className="mt-5 rounded-[1rem] border border-[var(--horizontal-line)] bg-white/[0.045] p-4">
            <p className="text-[0.9rem] font-bold text-[var(--text-black)]">Create an AI delegate first</p>
            <p className="mt-1 text-[0.78rem] leading-5 text-[var(--text-gray-light)]">
              AI delegates review, comment, and draft from their own persona. Publication requires your approval.
            </p>
            <Link href="/settings/ai-delegates" onClick={onClose} className="ai-delegate-primary mt-4 inline-flex rounded-full px-4 py-2 text-[0.78rem] font-black">
              Create AI delegate
            </Link>
          </div>
        ) : (
          <>
            <div className="mt-5 rounded-[1rem] border border-[var(--horizontal-line)] bg-white/[0.045] p-3">
              <p className="text-[0.68rem] font-black uppercase tracking-[0.14em] text-[var(--text-gray-light)]">Post context</p>
              <p className="mt-1 line-clamp-1 text-[0.9rem] font-bold text-[var(--text-black)]">{target.title || "Selected post"}</p>
              <p className="mt-1 line-clamp-3 text-[0.76rem] leading-5 text-[var(--text-gray-light)]">{target.text || "No post text available."}</p>
              {indicators.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5 text-[0.64rem] font-bold uppercase tracking-[0.1em] text-[var(--text-gray-light)]">
                  {indicators.map((indicator) => (
                    <span key={indicator} className="rounded-full bg-white/[0.06] px-2 py-1">
                      {indicator}
                    </span>
                  ))}
                </div>
              )}
            </div>

            <label className="mt-4 block text-[0.68rem] font-black uppercase tracking-[0.14em] text-[var(--text-gray-light)]">
              AI delegate
              <select
                value={selectedDelegateId}
                onChange={(event) => {
                  setSelectedDelegateId(event.target.value);
                  setDraftAction(null);
                  setNotice("");
                }}
                disabled={loadingDelegates || activeDelegates.length <= 1}
                className="ai-delegate-select mt-2 w-full rounded-[0.95rem] px-3 py-2.5 text-[0.84rem] normal-case tracking-normal"
              >
                {activeDelegates.map((delegate) => (
                  <option key={delegate.id || delegate.username} value={String(delegate.id || "")}>
                    {(delegate.display_name || delegate.username)} (@{delegate.username}) - {delegateProviderLabel(delegate)}
                  </option>
                ))}
              </select>
            </label>

            {selectedDelegate && (
              <div className="mt-3 flex items-center gap-3 rounded-[1rem] border border-[var(--horizontal-line)] bg-white/[0.045] p-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-full bg-[var(--pink)] text-[0.8rem] font-black text-white shadow-[var(--shadow-pink)]">
                  {selectedDelegate.avatar_url ? (
                    <img src={avatarDisplayUrl(selectedDelegate.avatar_url, defaultAvatar)} alt="" className="h-full w-full object-cover" />
                  ) : (
                    delegateInitials(selectedDelegate)
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[0.86rem] font-black text-[var(--text-black)]">
                    {selectedDelegate.display_name || selectedDelegate.username}
                    <span className="ml-1 font-semibold text-[var(--text-gray-light)]">(@{selectedDelegate.username})</span>
                  </p>
                  <p className="truncate text-[0.72rem] text-[var(--text-gray-light)]">{selectedDelegate.custody_label || "Custodied AI delegate"}</p>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {(selectedDelegate.persona_traits || []).slice(0, 3).map((trait) => (
                      <span key={trait} className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[0.62rem] font-bold text-[var(--text-gray-light)]">
                        {trait}
                      </span>
                    ))}
                    <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[0.62rem] font-bold text-[var(--text-gray-light)]">
                      {delegateProviderLabel(selectedDelegate)}
                    </span>
                  </div>
                </div>
              </div>
            )}
            {disabledDelegateCount > 0 && (
              <p className="mt-2 text-[0.68rem] font-semibold text-[var(--text-gray-light)]">
                {disabledDelegateCount} disabled delegate{disabledDelegateCount === 1 ? "" : "s"} hidden from drafting.
              </p>
            )}

            {(isComment || mode === "composer_assist") && !draftAction && (
              <label className="mt-4 block text-[0.68rem] font-black uppercase tracking-[0.14em] text-[var(--text-gray-light)]">
                {isComment ? "Focus" : "Draft focus"}
                <input
                  value={focus}
                  onChange={(event) => setFocus(event.target.value.slice(0, 240))}
                  placeholder={isComment ? "What should the AI consider?" : "What should the AI help draft?"}
                  className="ai-delegate-select mt-2 w-full rounded-[0.95rem] px-3 py-2.5 text-[0.84rem] normal-case tracking-normal"
                />
              </label>
            )}

            {mode === "composer_assist" ? (
              <div className="mt-4 rounded-[1rem] border border-[var(--horizontal-line)] bg-white/[0.045] p-4">
                <div className="flex flex-wrap gap-2">
                  <span className="ai-delegate-chip">Text</span>
                  <span className="ai-delegate-chip">Proposal framing</span>
                  <span className="ai-delegate-chip opacity-65"><IoImageOutline /> Image draft deferred</span>
                  <span className="ai-delegate-chip opacity-65"><IoVideocamOutline /> Video draft deferred</span>
                </div>
                <p className="mt-3 text-[0.78rem] leading-5 text-[var(--text-gray-light)]">
                  Official AI-authored post publishing is intentionally deferred. Use post cards and comments to generate approval-required AI reviews and comments today.
                </p>
              </div>
            ) : draftAction ? (
              <div className="ai-delegate-preview-card mt-4 rounded-[1rem] p-4">
                <p className="text-[0.68rem] font-black uppercase tracking-[0.14em] text-[var(--pink)]">
                  {isReview ? "Review ready" : "Comment ready"}
                </p>
                {isReview ? (
                  <>
                    <p className="mt-2 text-[0.95rem] font-black text-[var(--text-black)]">
                      Vote intent: {summary.intended_choice || summary.normalized_vote || "review"}
                    </p>
                    <p className="mt-2 text-[0.8rem] leading-5 text-[var(--text-gray-light)]">
                      {summary.reasoning_summary || summary.rationale || "AI reasoning generated from the locked charter."}
                    </p>
                  </>
                ) : (
                  <p className="mt-2 text-[0.84rem] leading-5 text-[var(--text-black)]">
                    {summary.generated_comment || summary.body || "AI-authored comment generated from the locked charter."}
                  </p>
                )}
                <div className="mt-3 grid gap-1 text-[0.66rem] leading-4 text-[var(--text-gray-light)] sm:grid-cols-2">
                  <p><span className="font-bold text-[var(--text-black)]">Model:</span> {summary.model_identity || "server/fallback"}</p>
                  <p><span className="font-bold text-[var(--text-black)]">Generation:</span> {generationSourceLabel(summary.generation_source)}</p>
                  {summary.reasoning_hash && <p><span className="font-bold text-[var(--text-black)]">Reasoning:</span> {compactHash(summary.reasoning_hash)}</p>}
                  {summary.content_hash && <p><span className="font-bold text-[var(--text-black)]">Content:</span> {compactHash(summary.content_hash)}</p>}
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={generateDraft}
                disabled={busy || !canGenerate}
                className="ai-delegate-primary mt-4 w-full rounded-full px-4 py-2.5 text-[0.84rem] font-black disabled:opacity-55"
              >
                {busy ? "Generating..." : modeConfig.button}
              </button>
            )}

            <div className="mt-4 rounded-[0.9rem] bg-white/[0.04] px-3 py-2 text-[0.72rem] leading-5 text-[var(--text-gray-light)]">
              AI-authored delegate actions are approval-required. You cannot edit official AI reasoning or content before publishing.
            </div>
          </>
        )}

        {draftAction && (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
            <button
              type="button"
              onClick={() => reviewDraft("cancel")}
              disabled={Boolean(reviewBusy)}
              className="ai-delegate-secondary inline-flex items-center gap-2 rounded-full px-4 py-2 text-[0.78rem] font-black disabled:opacity-55"
              title="Cancel prevents publication."
            >
              <IoClose /> {reviewBusy === "cancel" ? "Canceling..." : "Cancel"}
            </button>
            <button
              type="button"
              onClick={() => reviewDraft("approve")}
              disabled={Boolean(reviewBusy)}
              className="ai-delegate-primary inline-flex items-center gap-2 rounded-full px-4 py-2 text-[0.78rem] font-black disabled:opacity-55"
            >
              <IoCheckmark /> {reviewBusy === "approve" ? "Approving..." : "Approve"}
            </button>
          </div>
        )}

        {(notice || error) && (
          <p className={`mt-4 rounded-[0.85rem] px-3 py-2 text-[0.76rem] font-bold ${error ? "ai-delegate-error" : "ai-delegate-notice"}`}>
            {error || notice}
          </p>
        )}
        {draftAction && (
          <button
            type="button"
            onClick={() => {
              window.dispatchEvent(new CustomEvent("supernova:ai-actions-refresh", { detail: { notice: "AI Actions opened." } }));
              onClose?.();
            }}
            className="mt-3 text-[0.72rem] font-bold text-[var(--text-gray-light)] hover:text-[var(--pink)]"
          >
            Open in AI Actions
          </button>
        )}
      </section>
    </div>,
    document.body
  );
}
