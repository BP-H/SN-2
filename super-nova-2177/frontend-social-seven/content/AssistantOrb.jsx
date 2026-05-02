"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import { normalizeAvatarValue } from "@/utils/avatar";
import { FaCommentAlt, FaShare } from "react-icons/fa";
import {
  IoChatbubbleEllipsesOutline,
  IoClose,
  IoKeyOutline,
  IoListCircleOutline,
  IoPlanetOutline,
  IoSparklesOutline,
} from "react-icons/io5";
import { RiVoiceAiFill } from "react-icons/ri";
import { BiSolidDislike, BiSolidLike } from "react-icons/bi";
import { API_BASE_URL } from "@/utils/apiBase";
import {
  BACKEND_AUTH_MISSING_MESSAGE,
  authHeaders,
  formatBackendAuthErrorMessage,
  requireBackendAuthSession,
} from "@/utils/authSession";
import { MentionAutocomplete, useMentionAutocomplete } from "@/utils/mentionAutocomplete";
import { useUser } from "@/content/profile/UserContext";

const KEY_STORAGE = "supernova-ai-cursor-key";
const ORB_SIZE = 56;
const DIAL_SIZE = 184;

const AiWidgetIcon = ({ className = "" }) => <RiVoiceAiFill className={className} />;

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function isKeyboardEditable(element) {
  if (!element?.closest?.("[data-ai-cursor-root]")) return false;
  const tag = element.tagName?.toLowerCase();
  return tag === "input" || tag === "textarea" || Boolean(element.isContentEditable);
}

function fallbackFor(action, target) {
  const title = target?.title || "this post";
  const author = target?.author || "the author";
  const text = target?.text || title;

  if (action === "brief") {
    return `${title} by ${author}. Core signal: ${text.slice(0, 150)}${text.length > 150 ? "..." : ""}`;
  }

  if (action === "comment") {
    return "Strong signal. I would love to see the next step framed across humans, AI, and ORGs so the vote can turn into action.";
  }

  return "Post selected. Comments are open so you can engage directly.";
}

function buildPrompt(action, target) {
  const text = target?.text || "";
  if (action === "comment") {
    return `Write one concise, thoughtful social-network comment for this SuperNova post. Keep it human, constructive, and not salesy.\n\nAuthor: ${target?.author}\nTitle: ${target?.title}\nText: ${text}`;
  }
  return `Summarize this SuperNova social post in two short bullets and name one useful next action.\n\nAuthor: ${target?.author}\nTitle: ${target?.title}\nText: ${text}`;
}

function aiConfigMessage(payload = {}) {
  const code = payload?.error_code || "";
  if (code === "server_key_missing") return "Server AI key missing. Set OPENAI_API_KEY in Vercel.";
  if (code === "client_keys_disabled") return "Local keys are disabled on this deployment.";
  if (code === "openai_request_failed") return "OpenAI request failed.";
  return "AI unavailable; fallback text will be used.";
}

function hasUsableAiReply(response, payload = {}) {
  return Boolean(response?.ok && payload?.ai_configured === true && payload?.reply);
}

function connectorActionLabel(actionType = "") {
  const labels = {
    draft_ai_review: "AI review draft",
    draft_vote: "Vote draft",
    draft_comment: "Comment draft",
    draft_proposal: "Post draft",
    draft_collab_request: "Collab draft",
  };
  return labels[actionType] || "Draft action";
}

function connectorActionTargetLabel(action = {}) {
  const payload = action.draft_payload || {};
  if (payload.proposal_title) return payload.proposal_title;
  if (payload.title) return payload.title;
  if (action.target_type && action.target_id) return `${action.target_type} #${action.target_id}`;
  return "Connector action";
}

function connectorActionPreview(action = {}) {
  const payload = action.draft_payload || {};
  if (action.action_type === "draft_ai_review") {
    const vote = payload.intended_choice || payload.normalized_vote || "review";
    const rationale = payload.rationale || payload.comment || payload.body || "";
    const cleanRationale = String(rationale || "").replace(/\s+/g, " ").trim();
    const preview = `${vote}: ${cleanRationale || "AI review draft"}`;
    return preview.length > 120 ? `${preview.slice(0, 120)}...` : preview;
  }
  const text =
    payload.body ||
    payload.comment ||
    payload.intended_choice ||
    payload.normalized_vote ||
    payload.collaborator_username ||
    payload.action ||
    "Awaiting review";
  const cleanText = String(text || "").replace(/\s+/g, " ").trim();
  return cleanText.length > 96 ? `${cleanText.slice(0, 96)}...` : cleanText;
}

function connectorActionConfidence(action = {}) {
  const value = action?.draft_payload?.confidence;
  if (value === null || value === undefined || value === "") return "";
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return `${Math.round(Math.max(0, Math.min(number, 1)) * 100)}% confidence`;
}

function compactActionHash(value) {
  if (!value) return "";
  const text = String(value);
  return text.length > 14 ? `${text.slice(0, 7)}...${text.slice(-5)}` : text;
}

function aiReviewDetailRows(action = {}) {
  const payload = action.draft_payload || {};
  if (action.action_type !== "draft_ai_review") return [];
  const prefs = payload.autonomy_preferences && typeof payload.autonomy_preferences === "object" ? payload.autonomy_preferences : {};
  const actorName = payload.ai_actor_display_name || payload.display_name || payload.actor || payload.ai_actor_username;
  return [
    actorName && ["AI delegate", `${actorName}${payload.ai_actor_username ? ` (@${payload.ai_actor_username})` : ""}`],
    payload.custody_label && ["Custody", payload.custody_label],
    payload.intended_choice && ["Intended vote", payload.intended_choice],
    payload.model_identity && ["Model/policy", payload.model_identity],
    payload.reasoning_hash && ["Reasoning hash", compactActionHash(payload.reasoning_hash)],
    prefs.reviews && ["Autonomy", prefs.reviews === "custodian_approval_required" ? "reviews require custodian approval" : prefs.reviews],
  ].filter(Boolean);
}

function connectorActionCreatedAt(action = {}) {
  if (!action.created_at) return "";
  try {
    return new Date(action.created_at).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export default function AssistantOrb() {
  const router = useRouter();
  const { userData, isAuthenticated } = useUser();
  const dockRef = useRef(null);
  const orbRef = useRef(null);
  const commentInputRef = useRef(null);
  const hoverElementRef = useRef(null);
  const returnTimerRef = useRef(null);
  const keyboardFocusRef = useRef(false);
  const dragRef = useRef({
    active: false,
    moved: false,
    startX: 0,
    startY: 0,
    x: 0,
    y: 0,
    offsetX: ORB_SIZE / 2,
    offsetY: ORB_SIZE / 2,
    source: "dock",
  });
  const [mounted, setMounted] = useState(false);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const [ghostVisible, setGhostVisible] = useState(false);
  const [returning, setReturning] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [target, setTarget] = useState(null);
  const [hoverTarget, setHoverTarget] = useState(null);
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [aiSettingsNotice, setAiSettingsNotice] = useState("");
  const [aiTesting, setAiTesting] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [commentOpen, setCommentOpen] = useState(false);
  const [commentText, setCommentText] = useState("");
  const [commentSending, setCommentSending] = useState(false);
  const [actionsOpen, setActionsOpen] = useState(false);
  const [connectorActions, setConnectorActions] = useState([]);
  const [connectorActionsLoading, setConnectorActionsLoading] = useState(false);
  const [connectorActionsError, setConnectorActionsError] = useState("");
  const [connectorActionsNotice, setConnectorActionsNotice] = useState("");
  const [connectorActionBusyId, setConnectorActionBusyId] = useState(null);
  const [collabIncoming, setCollabIncoming] = useState([]);
  const [collabOutgoing, setCollabOutgoing] = useState([]);
  const [collabRequestsLoading, setCollabRequestsLoading] = useState(false);
  const [collabRequestsError, setCollabRequestsError] = useState("");
  const [lastSignal, setLastSignal] = useState(null);
  const mentionAutocomplete = useMentionAutocomplete({
    value: commentText,
    setValue: setCommentText,
    inputRef: commentInputRef,
  });
  const trackCommentMentionCaret = mentionAutocomplete.trackCaret;

  const getDockPosition = useCallback(() => {
    if (typeof window === "undefined") return { x: 0, y: 0 };
    const rect = dockRef.current?.getBoundingClientRect();
    if (!rect) {
      return {
        x: Math.max(8, window.innerWidth - ORB_SIZE - 10),
        y: Math.max(8, 12 + (40 - ORB_SIZE) / 2),
      };
    }
    return {
      x: clamp(rect.left + rect.width / 2 - ORB_SIZE / 2, 8, window.innerWidth - ORB_SIZE - 8),
      y: clamp(rect.top + rect.height / 2 - ORB_SIZE / 2, 8, window.innerHeight - ORB_SIZE - 8),
    };
  }, []);

  const getPostElementAtPoint = useCallback((x, y) => {
    const orb = orbRef.current;
    if (orb) orb.style.pointerEvents = "none";
    const element = document.elementFromPoint(x, y);
    if (orb) orb.style.pointerEvents = "";
    return element?.closest?.("[data-proposal-card]") || null;
  }, []);

  const getPostData = useCallback((post) => {
    if (!post) return null;
    return {
      id: post.dataset.proposalId,
      title: post.dataset.proposalTitle || "Selected post",
      author: post.dataset.proposalAuthor || "Unknown",
      text: post.dataset.proposalText || post.dataset.proposalTitle || "",
      userVote: post.dataset.proposalUserVote || "",
    };
  }, []);

  const clearHover = useCallback(() => {
    hoverElementRef.current?.classList.remove("ai-cursor-target");
    hoverElementRef.current = null;
    setHoverTarget(null);
  }, []);

  const returnToDock = useCallback(() => {
    if (typeof window === "undefined") return;
    window.clearTimeout(returnTimerRef.current);
    clearHover();
    setMenuOpen(false);
    setSettingsOpen(false);
    setCommentOpen(false);
    setActionsOpen(false);
    setReply("");
    setDragging(false);
    setReturning(true);
    setPos(getDockPosition());
    returnTimerRef.current = window.setTimeout(() => {
      setGhostVisible(false);
      setReturning(false);
      dockRef.current?.classList.remove("ai-cursor-dock-hidden");
    }, 460);
  }, [clearHover, getDockPosition]);

  useEffect(() => {
    setMounted(true);
    setApiKey(localStorage.getItem(KEY_STORAGE) || "");
    const frame = window.requestAnimationFrame(() => setPos(getDockPosition()));
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(returnTimerRef.current);
    };
  }, [getDockPosition]);

  useEffect(() => {
    if (!mounted) return undefined;

    const handleResize = () => {
      if (!dragRef.current.active && !ghostVisible && !menuOpen && !settingsOpen && !commentOpen && !actionsOpen && !reply) {
        setPos(getDockPosition());
      }
    };

    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [actionsOpen, commentOpen, getDockPosition, ghostVisible, menuOpen, mounted, reply, settingsOpen]);

  useEffect(() => {
    if (!mounted) return undefined;

    const syncKeyboardFocus = () => {
      keyboardFocusRef.current = isKeyboardEditable(document.activeElement);
    };
    const syncAfterFocusLeaves = () => {
      window.setTimeout(syncKeyboardFocus, 0);
    };

    document.addEventListener("focusin", syncKeyboardFocus);
    document.addEventListener("focusout", syncAfterFocusLeaves);
    syncKeyboardFocus();
    return () => {
      document.removeEventListener("focusin", syncKeyboardFocus);
      document.removeEventListener("focusout", syncAfterFocusLeaves);
    };
  }, [mounted]);

  useEffect(() => {
    if (!mounted) return undefined;

    const handleMove = (event) => {
      if (!dragRef.current.active) return;
      const nextX = clamp(event.clientX - dragRef.current.offsetX, 8, window.innerWidth - ORB_SIZE - 8);
      const nextY = clamp(event.clientY - dragRef.current.offsetY, 70, window.innerHeight - ORB_SIZE - 8);
      const moved =
        Math.abs(event.clientX - dragRef.current.startX) > 5 ||
        Math.abs(event.clientY - dragRef.current.startY) > 5;
      dragRef.current = {
        ...dragRef.current,
        moved: dragRef.current.moved || moved,
        x: event.clientX,
        y: event.clientY,
      };
      setPos({ x: nextX, y: nextY });

      const hoveredPost = getPostElementAtPoint(event.clientX, event.clientY);
      if (hoveredPost !== hoverElementRef.current) {
        hoverElementRef.current?.classList.remove("ai-cursor-target");
        hoveredPost?.classList.add("ai-cursor-target");
        hoverElementRef.current = hoveredPost;
        setHoverTarget(hoveredPost ? getPostData(hoveredPost) : null);
      }
    };

    const handleUp = () => {
      if (!dragRef.current.active) return;
      const wasMoved = dragRef.current.moved;
      const point = { x: dragRef.current.x, y: dragRef.current.y };
      const source = dragRef.current.source;
      dragRef.current.active = false;
      setDragging(false);
      clearHover();

      if (wasMoved) {
        const nextTarget = getPostData(getPostElementAtPoint(point.x, point.y));
        if (nextTarget) {
          setTarget(nextTarget);
          setReply("");
          setSettingsOpen(false);
          setCommentOpen(false);
          setMenuOpen(true);
          setGhostVisible(true);
          return;
        }
        returnToDock();
        return;
      }

      if (source === "orb") {
        setGhostVisible(true);
        setSettingsOpen(false);
        setCommentOpen(false);
        setReply("");
        setMenuOpen((value) => (target ? !value : true));
        if (!target) setReply("Drag the AI cursor onto a post first.");
        return;
      }

      setGhostVisible(true);
      setMenuOpen(false);
      setCommentOpen(false);
      setReply("");
      setSettingsOpen((value) => !value);
    };

    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
    window.addEventListener("pointercancel", handleUp);
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
      window.removeEventListener("pointercancel", handleUp);
    };
  }, [clearHover, getPostData, getPostElementAtPoint, mounted, returnToDock, target]);

  useEffect(() => {
    if (!mounted) return undefined;

    const handleOutside = (event) => {
      const hasActiveUi = ghostVisible || menuOpen || settingsOpen || commentOpen || actionsOpen || Boolean(reply);
      if (!hasActiveUi || dragRef.current.active) return;
      if (event.target?.closest?.("[data-ai-cursor-root]")) return;
      returnToDock();
    };

    document.addEventListener("pointerdown", handleOutside);
    return () => document.removeEventListener("pointerdown", handleOutside);
  }, [actionsOpen, commentOpen, ghostVisible, menuOpen, mounted, reply, returnToDock, settingsOpen]);

  useEffect(() => {
    if (!commentOpen) return undefined;
    const timer = window.setTimeout(() => {
      const textarea = commentInputRef.current;
      if (!textarea) return;
      textarea.focus();
      const caret = textarea.value.length;
      textarea.setSelectionRange(caret, caret);
      trackCommentMentionCaret(textarea);
    }, 80);
    return () => window.clearTimeout(timer);
  }, [commentOpen, trackCommentMentionCaret]);

  useEffect(() => {
    setLastSignal(target?.userVote || null);
  }, [target?.id, target?.userVote]);

  useEffect(() => {
    if (!mounted) return undefined;

    const retreat = (event) => {
      if (dragRef.current.active) return;
      if (event?.target?.closest?.("[data-ai-cursor-root]")) return;
      if (event?.type !== "wheel" && keyboardFocusRef.current && isKeyboardEditable(document.activeElement)) return;
      if (menuOpen || settingsOpen || commentOpen || actionsOpen || reply) returnToDock();
    };
    const escape = (event) => {
      if (event.key === "Escape") returnToDock();
    };

    window.addEventListener("scroll", retreat, { passive: true });
    window.addEventListener("wheel", retreat, { passive: true });
    window.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener("scroll", retreat);
      window.removeEventListener("wheel", retreat);
      window.removeEventListener("keydown", escape);
    };
  }, [actionsOpen, commentOpen, menuOpen, mounted, reply, returnToDock, settingsOpen]);

  const startDrag = (event) => {
    if (event.button !== undefined && event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    window.clearTimeout(returnTimerRef.current);

    const fromDock = event.currentTarget === dockRef.current;
    const startPos = fromDock ? getDockPosition() : pos;
    if (fromDock) dockRef.current?.classList.add("ai-cursor-dock-hidden");
    setPos(startPos);
    setGhostVisible(true);
    setReturning(false);
    setDragging(true);
    setMenuOpen(false);
    setSettingsOpen(false);
    setCommentOpen(false);
    setActionsOpen(false);
    setReply("");
    event.currentTarget.setPointerCapture?.(event.pointerId);
    dragRef.current = {
      active: true,
      moved: false,
      startX: event.clientX,
      startY: event.clientY,
      x: event.clientX,
      y: event.clientY,
      offsetX: clamp(event.clientX - startPos.x, 8, ORB_SIZE - 8),
      offsetY: clamp(event.clientY - startPos.y, 8, ORB_SIZE - 8),
      source: fromDock ? "dock" : "orb",
    };
  };

  const persistKey = (value) => {
    setApiKey(value);
    setAiSettingsNotice("");
    if (value.trim()) localStorage.setItem(KEY_STORAGE, value.trim());
    else localStorage.removeItem(KEY_STORAGE);
  };

  const testAi = async () => {
    if (aiTesting) return;
    setAiTesting(true);
    setAiSettingsNotice("");
    try {
      const response = await fetch("/api/ai", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: "Reply with: SuperNova AI ready.",
          apiKey: apiKey.trim() || undefined,
        }),
      });
      const data = await response.json().catch(() => ({}));
      setAiSettingsNotice(hasUsableAiReply(response, data) ? "AI is working." : aiConfigMessage(data));
    } catch {
      setAiSettingsNotice("AI unavailable; fallback text will be used.");
    } finally {
      setAiTesting(false);
    }
  };

  const closeActivePanel = () => {
    setSettingsOpen(false);
    setCommentOpen(false);
    setActionsOpen(false);
    setReply("");
    setBusy(false);
    if (target) setMenuOpen(true);
    setGhostVisible(true);
  };

  const loadConnectorActions = useCallback(async () => {
    setConnectorActionsLoading(true);
    setConnectorActionsError("");
    try {
      requireBackendAuthSession();
      const response = await fetch(`${API_BASE_URL}/connector/actions?status=draft&limit=50`, {
        headers: authHeaders(),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(formatBackendAuthErrorMessage(payload?.detail, "Unable to load AI Actions."));
      }
      setConnectorActions(Array.isArray(payload?.actions) ? payload.actions : []);
    } catch (error) {
      setConnectorActions([]);
      setConnectorActionsError(formatBackendAuthErrorMessage(error, BACKEND_AUTH_MISSING_MESSAGE));
    } finally {
      setConnectorActionsLoading(false);
    }
  }, []);

  const loadCollabRequests = useCallback(async () => {
    setCollabRequestsLoading(true);
    setCollabRequestsError("");
    try {
      requireBackendAuthSession();
      const fetchRole = async (role) => {
        const response = await fetch(`${API_BASE_URL}/proposal-collabs?role=${role}&status=pending&limit=50`, {
          headers: authHeaders(),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(formatBackendAuthErrorMessage(payload?.detail, "Unable to load collab requests."));
        }
        return Array.isArray(payload?.collabs) ? payload.collabs : [];
      };
      const [incoming, outgoing] = await Promise.all([fetchRole("collaborator"), fetchRole("author")]);
      setCollabIncoming(incoming);
      setCollabOutgoing(outgoing);
    } catch (error) {
      setCollabIncoming([]);
      setCollabOutgoing([]);
      setCollabRequestsError(formatBackendAuthErrorMessage(error, BACKEND_AUTH_MISSING_MESSAGE));
    } finally {
      setCollabRequestsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!mounted) return undefined;

    const handleAiActionsRefresh = (event) => {
      const notice = event?.detail?.notice || "AI Action draft queued for review.";
      setMenuOpen(false);
      setSettingsOpen(false);
      setCommentOpen(false);
      setActionsOpen(true);
      setReply("");
      setGhostVisible(true);
      setConnectorActionsNotice(notice);
      Promise.allSettled([loadConnectorActions(), loadCollabRequests()]);
    };

    window.addEventListener("supernova:ai-actions-refresh", handleAiActionsRefresh);
    return () => window.removeEventListener("supernova:ai-actions-refresh", handleAiActionsRefresh);
  }, [loadCollabRequests, loadConnectorActions, mounted]);

  const reviewConnectorAction = async (action, reviewAction) => {
    if (!action?.id || connectorActionBusyId) return;
    setConnectorActionBusyId(`${reviewAction}:${action.id}`);
    setConnectorActionsError("");
    setConnectorActionsNotice("");
    try {
      requireBackendAuthSession();
      const approveEndpoint =
        action.action_type === "draft_ai_review"
          ? `${API_BASE_URL}/connector/actions/${action.id}/approve-ai-review`
          : `${API_BASE_URL}/connector/actions/${action.id}/approve-vote`;
      const endpoint =
        reviewAction === "approve"
          ? approveEndpoint
          : `${API_BASE_URL}/connector/actions/${action.id}/cancel`;
      const response = await fetch(endpoint, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(formatBackendAuthErrorMessage(payload?.detail, "Unable to update AI Action."));
      }
      setConnectorActions((items) => items.filter((item) => item.id !== action.id));
      setConnectorActionsNotice(
        reviewAction === "approve"
          ? action.action_type === "draft_ai_review"
            ? "AI review published."
            : "Vote action approved."
          : "Draft action canceled."
      );
    } catch (error) {
      setConnectorActionsError(formatBackendAuthErrorMessage(error, "Unable to update AI Action."));
    } finally {
      setConnectorActionBusyId(null);
    }
  };

  const runAction = async (action) => {
    if (action === "universe") {
      setMenuOpen(false);
      setSettingsOpen(false);
      setCommentOpen(false);
      setActionsOpen(false);
      setReply("");
      setGhostVisible(false);
      dockRef.current?.classList.remove("ai-cursor-dock-hidden");
      router.push("/universe");
      return;
    }

    if (action === "key") {
      setSettingsOpen((value) => !value);
      setCommentOpen(false);
      setActionsOpen(false);
      setReply("");
      setMenuOpen(Boolean(target));
      return;
    }

    if (action === "actions") {
      setMenuOpen(false);
      setSettingsOpen(false);
      setCommentOpen(false);
      setActionsOpen(true);
      setReply("");
      setGhostVisible(true);
      setConnectorActionsNotice("");
      await Promise.allSettled([loadConnectorActions(), loadCollabRequests()]);
      return;
    }

    if (!target && action !== "key") {
      setReply("Drag the AI cursor onto a post first.");
      setMenuOpen(true);
      return;
    }

    if (action === "like" || action === "dislike") {
      if (!isAuthenticated) {
        setMenuOpen(true);
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("supernova:open-account", { detail: { mode: "create" } }));
        }
        return;
      }
      const shouldRemove = lastSignal === action;
      window.dispatchEvent(
        new CustomEvent("supernova:post-action", {
          detail: { id: target.id, action, source: "ai-widget", allowToggle: shouldRemove },
        })
      );
      setLastSignal(shouldRemove ? null : action);
      setTarget((value) => (value ? { ...value, userVote: shouldRemove ? "" : action } : value));
      setReply("");
      setSettingsOpen(false);
      setCommentOpen(false);
      setActionsOpen(false);
      setMenuOpen(true);
      return;
    }

    if (action === "engage") {
      if (!isAuthenticated) {
        setMenuOpen(true);
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("supernova:open-account", { detail: { mode: "create" } }));
        }
        return;
      }
      setBusy(true);
      setSettingsOpen(false);
      setActionsOpen(false);
      setCommentOpen(false);
      setReply("");
      try {
        const response = await fetch("/api/ai", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: buildPrompt("comment", target), apiKey: apiKey.trim() || undefined }),
        });
        const data = await response.json().catch(() => ({}));
        if (hasUsableAiReply(response, data)) {
          setCommentText(data.reply);
          setReply("");
        } else {
          setCommentText(fallbackFor("comment", target));
          setReply("AI was unavailable, so fallback text was used.");
        }
      } catch {
        setCommentText(fallbackFor("comment", target));
        setReply("AI was unavailable, so fallback text was used.");
      } finally {
        setBusy(false);
        setCommentOpen(true);
        setMenuOpen(true);
      }
      return;
    }

    if (action === "comment") {
      if (!isAuthenticated) {
        setMenuOpen(true);
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("supernova:open-account", { detail: { mode: "create" } }));
        }
        return;
      }
      setCommentText("");
      setCommentOpen(true);
      setMenuOpen(true);
      setSettingsOpen(false);
      setActionsOpen(false);
      setReply("");
      return;
    }

    if (action === "share") {
      const url = `${window.location.origin}/proposals/${target.id}`;
      try {
        await navigator.clipboard?.writeText?.(url);
        setReply("Post link copied.");
        setMenuOpen(true);
      } catch {
        setReply(url);
        setMenuOpen(true);
      }
      return;
    }

    setBusy(true);
    try {
      const response = await fetch("/api/ai", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: buildPrompt(action, target), apiKey: apiKey.trim() || undefined }),
      });
      const data = await response.json().catch(() => ({}));
      const aiReply = hasUsableAiReply(response, data)
        ? data.reply
        : `AI was unavailable, so fallback text was used.\n\n${fallbackFor(action, target)}`;
      setReply(aiReply);
      setMenuOpen(true);
    } catch {
      setReply(`AI was unavailable, so fallback text was used.\n\n${fallbackFor(action, target)}`);
      setMenuOpen(true);
    } finally {
      setBusy(false);
    }
  };

  const submitComment = async () => {
    const value = commentText.trim();
    if (!target || !value) return;
    if (!isAuthenticated || !userData?.name) {
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("supernova:open-account", { detail: { mode: "create" } }));
      }
      return;
    }

    setCommentSending(true);
    try {
      const response = await fetch(`${API_BASE_URL}/comments`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          proposal_id: Number(target.id),
          user: userData.name,
          user_img: normalizeAvatarValue(userData.avatar || ""),
          species: userData.species || "human",
          comment: value,
        }),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(formatBackendAuthErrorMessage(payload?.detail, "Comment failed."));
      }

      const payload = await response.json().catch(() => ({}));
      const newComment = payload?.comments?.[0] || {
        proposal_id: Number(target.id),
        user: userData.name,
        user_img: normalizeAvatarValue(userData.avatar || ""),
        species: userData.species || "human",
        comment: value,
      };
      window.dispatchEvent(
        new CustomEvent("supernova:post-action", {
          detail: { id: target.id, action: "comment-posted", comment: newComment },
        })
      );
      setCommentText("");
      setCommentOpen(false);
      setReply("Comment posted.");
      setMenuOpen(true);
    } catch (error) {
      setReply(formatBackendAuthErrorMessage(error, "Comment failed."));
    } finally {
      setCommentSending(false);
    }
  };

  const actions = [
    { action: "dislike", label: "Challenge", icon: BiSolidDislike, dx: -56, dy: -88, size: "primary", tone: "blue" },
    { action: "like", label: "Support", icon: BiSolidLike, dx: 56, dy: -88, size: "primary", tone: "pink" },
    { action: "actions", label: "AI Actions", icon: IoListCircleOutline, dx: 0, dy: -124, tone: "blue" },
    { action: "comment", label: "Comment", icon: FaCommentAlt, dx: -100, dy: -28 },
    { action: "brief", label: "Brief", icon: IoSparklesOutline, dx: 100, dy: -28 },
    { action: "engage", label: "Draft", icon: IoChatbubbleEllipsesOutline, dx: -90, dy: 48 },
    { action: "share", label: "Share", icon: FaShare, dx: 90, dy: 48 },
    { action: "universe", label: "Universe", icon: IoPlanetOutline, dx: -34, dy: 96 },
    { action: "key", label: "AI Settings", icon: IoKeyOutline, dx: 34, dy: 96 },
  ];
  const dockHidden = dragging || ghostVisible || menuOpen || settingsOpen || commentOpen || actionsOpen || Boolean(reply);
  const floatingPanelStyle =
    mounted && typeof window !== "undefined"
      ? (() => {
          const width = Math.min(window.innerWidth - 16, 352);
          const viewport = window.visualViewport;
          const viewportTop = viewport?.offsetTop || 0;
          const viewportHeight = viewport?.height || window.innerHeight;
          const panelHeight = actionsOpen ? 488 : commentOpen ? 246 : settingsOpen ? 330 : 168;
          const rightRoom = window.innerWidth - (pos.x + ORB_SIZE + 12);
          const leftRoom = pos.x - 12;
          const canUseSide = Math.max(rightRoom, leftRoom) >= width;
          const desiredLeft =
            canUseSide && rightRoom >= leftRoom
              ? pos.x + ORB_SIZE + 12
              : canUseSide
              ? pos.x - width - 12
              : 8;
          const desiredTop = canUseSide
            ? pos.y + ORB_SIZE / 2 - panelHeight / 2
            : pos.y > window.innerHeight / 2
            ? pos.y - panelHeight - 92
            : pos.y + ORB_SIZE + 92;
          const minTop = Math.max(72, viewportTop + 8);
          const maxTop = Math.max(minTop, viewportTop + viewportHeight - panelHeight - 8);
          return {
            width: `${width}px`,
            left: `${clamp(desiredLeft, 8, window.innerWidth - width - 8)}px`,
            top: `${clamp(desiredTop, minTop, maxTop)}px`,
          };
        })()
      : {};

  const floatingUi = (
    <>
      {ghostVisible && (
        <div
          ref={orbRef}
          data-ai-cursor-root
          className={`fixed z-[2147482500] ${dragging ? "" : "transition-[left,top,opacity,transform] duration-500 ease-out"} ${
            returning ? "ai-cursor-returning scale-75 opacity-60" : "scale-100 opacity-100"
          }`}
          style={{ left: pos.x, top: pos.y, touchAction: "none" }}
        >
          <button
            data-ai-cursor-root
            type="button"
            onPointerDown={startDrag}
            aria-label="Drag SuperNova AI cursor"
            className={`ai-cursor-core flex h-14 w-14 items-center justify-center rounded-full text-white ${
              dragging ? "scale-105 cursor-grabbing" : "cursor-grab"
            }`}
          >
            <AiWidgetIcon className="text-[1.7rem]" />
          </button>
        </div>
      )}

      {dragging && hoverTarget && (
        <div
          data-ai-cursor-root
          className="ai-cursor-tooltip pointer-events-none fixed z-[2147482502] max-w-[15rem] rounded-full px-3 py-2 text-[0.72rem] font-semibold backdrop-blur-xl"
          style={{
            left: clamp(pos.x - 82, 8, window.innerWidth - 248),
            top: Math.max(80, pos.y - 44),
          }}
        >
          Targeting {hoverTarget.title}
        </div>
      )}

      {menuOpen && (
        <>
          <div
            data-ai-cursor-root
            className="pointer-events-none fixed z-[2147482500] rounded-full ai-cursor-dial"
            style={{
              left: pos.x + ORB_SIZE / 2 - DIAL_SIZE / 2,
              top: pos.y + ORB_SIZE / 2 - DIAL_SIZE / 2,
              "--ai-dial-size": `${DIAL_SIZE}px`,
            }}
          />
          {actions.map((item) => {
            const Icon = item.icon;
            const buttonSize = item.size === "primary" ? 46 : 42;
            const centerX = pos.x + ORB_SIZE / 2;
            const centerY = pos.y + ORB_SIZE / 2;
            const signalActive = item.action === lastSignal;
            return (
              <button
                key={item.action}
                data-ai-cursor-root
                data-active={signalActive ? "true" : "false"}
                data-tone={item.tone || "neutral"}
                type="button"
                onClick={() => runAction(item.action)}
                className="ai-cursor-action-button fixed z-[2147482502] flex items-center justify-center rounded-full backdrop-blur-xl transition-transform active:scale-95"
                style={{
                  left: clamp(centerX + item.dx - buttonSize / 2, 8, window.innerWidth - buttonSize - 8),
                  top: clamp(centerY + item.dy - buttonSize / 2, 72, window.innerHeight - buttonSize - 8),
                  width: buttonSize,
                  height: buttonSize,
                }}
                aria-label={item.label}
                title={item.label}
              >
                <Icon className={item.size === "primary" ? "text-[1.16rem]" : "text-[1rem]"} />
              </button>
            );
          })}
        </>
      )}

      {(settingsOpen || commentOpen || actionsOpen || busy || reply) && (
        <div
          data-ai-cursor-root
          className="ai-cursor-panel fixed z-[2147482503] max-h-[calc(100dvh-6rem)] overflow-y-auto rounded-[1rem] p-3 backdrop-blur-xl"
          style={floatingPanelStyle}
        >
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[0.68rem] uppercase tracking-[0.18em] text-[var(--pink)]">
                {settingsOpen ? "AI Settings" : commentOpen ? "Comment" : actionsOpen ? "AI Actions" : "AI Cursor"}
              </p>
              <p className="truncate text-[0.82rem] text-[var(--text-gray-light)]">
                {settingsOpen
                  ? "Drag onto a post, then choose Brief or Draft"
                  : actionsOpen
                  ? "Review connector drafts"
                  : target
                  ? target.title
                  : "Drag onto a post first"}
              </p>
            </div>
            <button
              type="button"
              onClick={closeActivePanel}
              className="ai-cursor-panel-icon-button flex h-8 w-8 items-center justify-center rounded-full text-[0.9rem] font-semibold"
              aria-label="Close popup"
              title="Close popup"
            >
              <IoClose />
            </button>
          </div>

          {settingsOpen && (
            <div className="mt-3 flex flex-col gap-2">
              <div className="ai-cursor-result-box rounded-[0.85rem] p-3 text-[0.72rem] leading-5">
                Drag the AI cursor onto a post, then choose Brief or Draft. A server key uses OPENAI_API_KEY in Vercel.
                A local browser key only works when ALLOW_CLIENT_AI_KEY=true. Saving a key does not automatically
                generate anything.
              </div>
              <input
                value={apiKey}
                onChange={(event) => persistKey(event.target.value)}
                type="password"
                placeholder="OpenAI API key for local testing"
                className="ai-cursor-field w-full rounded-[0.8rem] px-3 py-2 text-[0.78rem] outline-none"
              />
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => {
                    persistKey(apiKey);
                    setAiSettingsNotice("Key saved locally. Drag onto a post and choose Brief or Draft.");
                  }}
                  className="ai-cursor-secondary-button rounded-full px-3 py-2 text-[0.74rem] font-semibold"
                >
                  Save local key
                </button>
                <button
                  type="button"
                  onClick={testAi}
                  disabled={aiTesting}
                  className="rounded-full bg-[var(--pink)] px-3 py-2 text-[0.74rem] font-semibold text-white shadow-[var(--shadow-pink)] disabled:opacity-55"
                >
                  {aiTesting ? "Testing..." : "Test AI"}
                </button>
              </div>
              {aiSettingsNotice && (
                <div className="ai-action-notice rounded-[0.8rem] px-3 py-2 text-[0.74rem]">
                  {aiSettingsNotice}
                </div>
              )}
              <button
                type="button"
                onClick={() => {
                  setSettingsOpen(false);
                  setActionsOpen(true);
                  setConnectorActionsNotice("");
                  loadConnectorActions();
                  loadCollabRequests();
                }}
                className="ai-cursor-secondary-button rounded-full px-3 py-2 text-[0.74rem] font-semibold"
              >
                Review AI Actions
              </button>
            </div>
          )}

          {commentOpen && (
            <div className="mt-3 flex flex-col gap-2">
              <div className="relative">
                <textarea
                  ref={commentInputRef}
                  value={commentText}
                  onChange={(event) => {
                    setCommentText(event.target.value);
                    mentionAutocomplete.trackCaret(event.currentTarget);
                  }}
                  onClick={(event) => mentionAutocomplete.trackCaret(event.currentTarget)}
                  onKeyDown={mentionAutocomplete.handleKeyDown}
                  onKeyUp={(event) => mentionAutocomplete.trackCaret(event.currentTarget)}
                  placeholder="Write a comment..."
                  className="ai-cursor-field min-h-24 w-full rounded-[0.85rem] px-3 py-2 text-[0.84rem] outline-none"
                />
                <MentionAutocomplete controller={mentionAutocomplete} withinAiCursor />
              </div>
              <div className="flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={closeActivePanel}
                  className="ai-cursor-secondary-button rounded-full px-3 py-2 text-[0.76rem] font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={submitComment}
                  disabled={!commentText.trim() || commentSending}
                  className="rounded-full bg-[var(--pink)] px-4 py-2 text-[0.76rem] font-semibold text-white shadow-[var(--shadow-pink)] disabled:opacity-55"
                >
                  {commentSending ? "Posting..." : "Post"}
                </button>
              </div>
            </div>
          )}

          {actionsOpen && (
            <div className="mt-3 flex flex-col gap-2">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[0.74rem] font-semibold text-[var(--text-gray-light)]">
                  Pending approval-required actions
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setConnectorActionsNotice("");
                    loadConnectorActions();
                    loadCollabRequests();
                  }}
                  disabled={connectorActionsLoading || collabRequestsLoading}
                  className="ai-cursor-secondary-button rounded-full px-3 py-1.5 text-[0.7rem] font-semibold disabled:opacity-60"
                >
                  Refresh
                </button>
              </div>

              {connectorActionsNotice && (
                <div className="ai-action-notice rounded-[0.8rem] px-3 py-2 text-[0.74rem]">
                  {connectorActionsNotice}
                </div>
              )}

              {connectorActionsLoading ? (
                <div className="ai-cursor-result-box rounded-[0.85rem] p-3 text-[0.78rem]">
                  Loading AI Actions...
                </div>
              ) : connectorActionsError ? (
                <div className="ai-action-error rounded-[0.85rem] p-3 text-[0.78rem]">
                  {connectorActionsError}
                </div>
              ) : connectorActions.length === 0 ? (
                <div className="ai-cursor-result-box rounded-[0.85rem] p-3 text-[0.78rem]">
                  No draft actions waiting. AI review drafts, vote drafts, and collab requests will appear here before anything publishes.
                </div>
              ) : (
                <div className="ai-actions-list flex max-h-64 flex-col gap-2 overflow-y-auto pr-1">
                  {connectorActions.map((action) => {
                    const busyKey = connectorActionBusyId || "";
                    const isApproving = busyKey === `approve:${action.id}`;
                    const isCanceling = busyKey === `cancel:${action.id}`;
                    const isVoteDraft = action.action_type === "draft_vote";
                    const isAiReviewDraft = action.action_type === "draft_ai_review";
                    const isApprovableDraft = isVoteDraft || isAiReviewDraft;
                    const confidenceLabel = connectorActionConfidence(action);
                    const aiReviewRows = aiReviewDetailRows(action);
                    return (
                      <article key={action.id} className="ai-action-card rounded-[0.9rem] p-3">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="truncate text-[0.8rem] font-semibold">
                              {connectorActionLabel(action.action_type)}
                            </p>
                            <p className="truncate text-[0.72rem] text-[var(--text-gray-light)]">
                              {connectorActionTargetLabel(action)}
                            </p>
                          </div>
                          <span className="ai-action-status-pill shrink-0 rounded-full px-2 py-1 text-[0.62rem] font-semibold uppercase tracking-[0.1em]">
                            {action.status || "draft"}
                          </span>
                        </div>
                        <p className="mt-2 line-clamp-2 text-[0.74rem] leading-5 text-[var(--text-gray-light)]">
                          {connectorActionPreview(action)}
                        </p>
                        {isAiReviewDraft && (
                          <div className="mt-2 rounded-[0.7rem] border border-[var(--pink)]/20 bg-[var(--pink)]/8 px-2.5 py-2">
                            <p className="text-[0.68rem] font-semibold leading-5 text-[var(--text-gray-light)]">
                              Approval publishes exactly one AI vote and one rationale comment.
                            </p>
                            {aiReviewRows.length > 0 && (
                              <div className="mt-2 grid gap-1 text-[0.66rem] leading-4 text-[var(--text-gray-light)]">
                                {aiReviewRows.map(([label, value]) => (
                                  <p key={label}>
                                    <span className="font-semibold text-[var(--text-black)]">{label}:</span> {value}
                                  </p>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                          <span className="text-[0.68rem] text-[var(--text-gray-light)]">
                            {[connectorActionCreatedAt(action), confidenceLabel].filter(Boolean).join(" · ")}
                          </span>
                          <div className="flex items-center gap-2">
                            {isApprovableDraft ? (
                              <button
                                type="button"
                                onClick={() => reviewConnectorAction(action, "approve")}
                                disabled={Boolean(connectorActionBusyId)}
                                className="ai-action-approve-button rounded-full px-3 py-1.5 text-[0.7rem] font-semibold disabled:opacity-55"
                              >
                                {isApproving ? "Approving..." : "Approve"}
                              </button>
                            ) : (
                              <span className="ai-action-disabled-pill rounded-full px-3 py-1.5 text-[0.68rem] font-semibold">
                                Approve soon
                              </span>
                            )}
                            <button
                              type="button"
                              onClick={() => reviewConnectorAction(action, "cancel")}
                              disabled={Boolean(connectorActionBusyId)}
                              className="ai-cursor-secondary-button rounded-full px-3 py-1.5 text-[0.7rem] font-semibold disabled:opacity-55"
                              title="Cancel prevents publication."
                            >
                              {isCanceling ? "Canceling..." : "Cancel"}
                            </button>
                          </div>
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}

              <div className="mt-3 border-t border-white/[0.08] pt-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[0.74rem] font-semibold text-[var(--text-gray-light)]">
                    Collab requests
                  </p>
                  <span className="ai-action-status-pill rounded-full px-2 py-1 text-[0.62rem] font-semibold uppercase tracking-[0.1em]">
                    {collabIncoming.length + collabOutgoing.length}
                  </span>
                </div>

                {collabRequestsLoading ? (
                  <div className="ai-cursor-result-box mt-2 rounded-[0.85rem] p-3 text-[0.78rem]">
                    Loading collab requests...
                  </div>
                ) : collabRequestsError ? (
                  <div className="ai-action-error mt-2 rounded-[0.85rem] p-3 text-[0.78rem]">
                    {collabRequestsError}
                  </div>
                ) : collabIncoming.length === 0 && collabOutgoing.length === 0 ? (
                  <div className="ai-cursor-result-box mt-2 rounded-[0.85rem] p-3 text-[0.78rem]">
                    No pending collab requests.
                  </div>
                ) : (
                  <div className="ai-action-card mt-2 rounded-[0.9rem] p-3">
                    <p className="text-[0.78rem] font-semibold">
                      {collabIncoming.length} incoming, {collabOutgoing.length} outgoing pending.
                    </p>
                    <p className="mt-1 text-[0.72rem] leading-5 text-[var(--text-gray-light)]">
                      Use the people button on your profile header for approve, decline, and cancel controls.
                    </p>
                    <button
                      type="button"
                      onClick={() => {
                        setActionsOpen(false);
                        setMenuOpen(false);
                        if (userData?.name) router.push(`/users/${encodeURIComponent(userData.name)}`);
                      }}
                      className="ai-cursor-secondary-button mt-3 rounded-full px-3 py-1.5 text-[0.7rem] font-semibold"
                    >
                      Open profile
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}

          {(busy || reply) && (
            <div className="ai-cursor-result-box mt-3 max-h-36 overflow-y-auto rounded-[0.85rem] p-3 text-[0.78rem] leading-5">
              {busy ? "Thinking..." : reply}
            </div>
          )}
        </div>
      )}
    </>
  );

  return (
    <>
      <button
        ref={dockRef}
        data-ai-cursor-root
        type="button"
        onPointerDown={startDrag}
        aria-label="SuperNova AI cursor"
        aria-hidden={dockHidden}
        className={`mobile-topbar-action ai-cursor-dock flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-white transition-all duration-150 ${
          dockHidden ? "ai-cursor-dock-hidden pointer-events-none opacity-0" : "opacity-100"
        }`}
      >
        <AiWidgetIcon className="text-[1.12rem]" />
      </button>

      {mounted && typeof document !== "undefined" ? createPortal(floatingUi, document.body) : null}
    </>
  );
}
