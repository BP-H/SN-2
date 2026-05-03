"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FaCommentAlt, FaFileAlt, FaLink, FaShare } from "react-icons/fa";
import { IoMdBookmark } from "react-icons/io";
import { useQueryClient } from "@tanstack/react-query";
import { useUser } from "@/content/profile/UserContext";
import { API_BASE_URL, absoluteApiUrl } from "@/utils/apiBase";
import {
  BACKEND_AUTH_MISSING_MESSAGE,
  authHeaders,
  formatBackendAuthErrorMessage,
  requireBackendAuthSession,
} from "@/utils/authSession";
import {
  IoCheckmark,
  IoClose,
  IoCreateOutline,
  IoEllipsisHorizontal,
  IoPersonAddOutline,
  IoPersonCircleOutline,
  IoPersonRemoveOutline,
  IoChatbubbleOutline,
  IoFlashOutline,
  IoHandLeftOutline,
  IoShieldCheckmarkOutline,
  IoSparklesOutline,
  IoTimeOutline,
  IoTrashOutline,
} from "react-icons/io5";
import LikesDeslikes from "./LikesDeslikes";
import AiDelegateActionModal from "./AiDelegateActionModal";
import DisplayComments from "./DisplayComments";
import InsertComment from "./InsertComment";
import MediaGallery from "./MediaGallery";
import PdfPager from "./PdfPager";
import { avatarDisplayUrl, normalizeAvatarValue } from "@/utils/avatar";
import { BOOKMARKS_CHANGED_EVENT, isBookmarkedId, toggleBookmarkId } from "@/utils/bookmarks";
import LinkifiedText, { normalizeLinkHref } from "@/utils/linkify";
import { speciesAccentColor, speciesAvatarStyle } from "@/utils/species";
import { useVerifiedMentionUsernames } from "@/utils/verifiedMentions";
import { buildWeightedVoteSummary } from "@/utils/voteWeights";

function formatDecisionCountdown(deadlineValue, fallbackDays, nowMs) {
  const safeFallbackDays = Number(fallbackDays || 0);
  if (!deadlineValue) return safeFallbackDays > 0 ? `${safeFallbackDays}d window` : "Window";
  const deadline = new Date(deadlineValue);
  if (Number.isNaN(deadline.getTime())) {
    return safeFallbackDays > 0 ? `${safeFallbackDays}d window` : "Window";
  }
  const remaining = deadline.getTime() - nowMs;
  if (remaining <= 0) return "Ended";
  const totalMinutes = Math.ceil(remaining / 60000);
  const days = Math.floor(totalMinutes / 1440);
  const hours = Math.floor((totalMinutes % 1440) / 60);
  const minutes = totalMinutes % 60;
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${Math.max(1, minutes)}m`;
}

function normalizeCollabSuggestions(payload = []) {
  const list = Array.isArray(payload) ? payload : Array.isArray(payload?.users) ? payload.users : [];
  const seen = new Set();
  return list
    .map((item) => {
      const username = String(item?.username || "").trim();
      const key = username.toLowerCase();
      const avatar = item?.avatar || item?.avatar_url || item?.profile_pic || item?.profilePic || item?.author_img || "";
      return {
        username,
        key,
        species: String(item?.species || "human").trim() || "human",
        avatar: avatarDisplayUrl(avatar, ""),
        initials: String(item?.initials || username || "SN").slice(0, 2).toUpperCase(),
        canCollab: item?.can_collab ?? item?.canCollab ?? true,
      };
    })
    .filter((item) => {
      if (!item.username || item.canCollab === false || seen.has(item.key)) return false;
      seen.add(item.key);
      return true;
    });
}

function supportSummaryLabel(likes = [], dislikes = [], voteSummary = null) {
  const likeList = Array.isArray(likes) ? likes : [];
  const dislikeList = Array.isArray(dislikes) ? dislikes : [];
  if (likeList.length + dislikeList.length > 0) {
    const weighted = buildWeightedVoteSummary(likeList, dislikeList);
    const percent = Math.max(0, Math.min(100, Math.round(weighted.supportPercent || 0)));
    return `${percent}% support`;
  }

  const summary = voteSummary || {};
  const summaryUp = Number(summary.up ?? summary.likes ?? summary.support);
  const summaryDown = Number(summary.down ?? summary.dislikes ?? summary.oppose);
  const up = Number.isFinite(summaryUp) ? summaryUp : 0;
  const down = Number.isFinite(summaryDown) ? summaryDown : 0;
  const summaryTotal = Number(summary.total);
  const total = Number.isFinite(summaryTotal) && summaryTotal > 0 ? summaryTotal : up + down;
  if (total <= 0) return "";
  const summaryRatio = Number(summary.approval_ratio);
  const ratio = Number.isFinite(summaryRatio) ? (summaryRatio > 1 ? summaryRatio / 100 : summaryRatio) : up / total;
  const percent = Math.max(0, Math.min(100, Math.round(ratio * 100)));
  return `${percent}% support`;
}

function ProposalCard({
  id,
  userName,
  time,
  title,
  text,
  media = {},
  logo,
  likes = [],
  dislikes = [],
  voteSummary = null,
  comments = [],
  collabs = [],
  profileUrl = "",
  domainAsProfile = false,
  specie = "human",
  setErrorMsg,
  setNotify,
  isDetailPage = false,
  showSupportSummary = false,
}) {
  const [showComments, setShowComments] = useState(false);
  const [localComments, setLocalComments] = useState(comments);
  const [localText, setLocalText] = useState(text || "");
  const [editText, setEditText] = useState(text || "");
  const [readMore, setReadMore] = useState(false);
  const [videoLoaded, setVideoLoaded] = useState(false);
  const [videoOpen, setVideoOpen] = useState(false);
  const [bookmarked, setBookmarked] = useState(false);
  const [copied, setCopied] = useState(false);
  const [shareMenuOpen, setShareMenuOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const [ownerBusy, setOwnerBusy] = useState(false);
  const [followBusy, setFollowBusy] = useState(false);
  const [followingAuthor, setFollowingAuthor] = useState(false);
  const [localLogo, setLocalLogo] = useState(logo || "");
  const [deletingCommentId, setDeletingCommentId] = useState(null);
  const [replyTarget, setReplyTarget] = useState(null);
  const [aiCommentFocus, setAiCommentFocus] = useState("");
  const [aiCommentParentId, setAiCommentParentId] = useState(null);
  const [localUserName, setLocalUserName] = useState(userName || "");
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [collabInviteOpen, setCollabInviteOpen] = useState(false);
  const [collabSearch, setCollabSearch] = useState("");
  const [collabSuggestions, setCollabSuggestions] = useState([]);
  const [collabBusy, setCollabBusy] = useState(false);
  const [collabStatus, setCollabStatus] = useState("");
  const [collabError, setCollabError] = useState("");
  const [aiActionModalMode, setAiActionModalMode] = useState("");
  const shareMenuRef = useRef(null);
  const optionsMenuRef = useRef(null);

  const { userData, defaultAvatar, isAuthenticated } = useUser();
  const queryClient = useQueryClient();
  const router = useRouter();
  const authorName = localUserName || userName || "";
  const approvedCollabs = useMemo(() => {
    if (!Array.isArray(collabs)) return [];
    const seen = new Set();
    return collabs
      .filter((collab) => collab?.status === "approved" && collab?.username)
      .map((collab) => {
        const username = String(collab.username || "").trim();
        const key = username.toLowerCase();
        return {
          ...collab,
          username,
          key,
          avatar: avatarDisplayUrl(collab.avatar || collab.avatar_url || collab.profile_pic || "", ""),
          species: collab.species || "human",
        };
      })
      .filter((collab) => {
        if (!collab.username || seen.has(collab.key)) return false;
        seen.add(collab.key);
        return true;
      });
  }, [collabs]);
  const inlineApprovedCollabs = approvedCollabs.slice(0, 2);
  const extraApprovedCollabCount = Math.max(0, approvedCollabs.length - inlineApprovedCollabs.length);
  const avatarApprovedCollabs = approvedCollabs.slice(0, 3);
  const extraAvatarApprovedCollabCount = Math.max(0, approvedCollabs.length - avatarApprovedCollabs.length);
  const isOwner = Boolean(authorName && userData?.name && authorName.toLowerCase() === userData.name.toLowerCase());
  const verifiedMentions = useVerifiedMentionUsernames(localText);
  const authorSpecies = isOwner ? userData?.species || specie : specie || "human";
  const authorAvatarStyle = speciesAvatarStyle(authorSpecies);
  const displayLogo = isOwner && normalizeAvatarValue(userData?.avatar) ? userData.avatar : localLogo;
  const displayAvatar = avatarDisplayUrl(displayLogo, defaultAvatar);
  const governance = media?.governance || null;
  const isDecisionProposal = governance?.kind === "decision";
  const decisionThreshold = Number(governance?.approval_threshold ?? governance?.threshold ?? 0);
  const decisionThresholdLabel = decisionThreshold > 0 ? `${Math.round(decisionThreshold * 100)}%` : "";
  const decisionExecutionMode = String(governance?.execution_mode || governance?.execution || "manual").toLowerCase();
  const isAutomaticExecution = decisionExecutionMode === "automatic" || decisionExecutionMode === "auto";
  const DecisionExecutionIcon = isAutomaticExecution ? IoFlashOutline : IoHandLeftOutline;
  const decisionExecutionLabel = isAutomaticExecution ? "Auto" : "Manual";
  const decisionExecutionTitle = isAutomaticExecution ? "Automatic execution" : "Manual execution";
  const decisionDeadlineLabel = isDecisionProposal
    ? formatDecisionCountdown(governance?.voting_deadline, governance?.voting_days, nowMs)
    : "";

  useEffect(() => {
    if (!isDecisionProposal || !governance?.voting_deadline) return undefined;
    const timer = window.setInterval(() => setNowMs(Date.now()), 60000);
    return () => window.clearInterval(timer);
  }, [governance?.voting_deadline, isDecisionProposal]);

  useEffect(() => {
    const openAiDelegateAction = (event) => {
      if (String(event?.detail?.proposalId || "") !== String(id || "")) return;
      const nextMode = event?.detail?.mode === "comment" ? "comment" : "review";
      if (nextMode === "comment") setShowComments(true);
      setAiActionModalMode(nextMode);
    };
    window.addEventListener("supernova:open-ai-delegate-action", openAiDelegateAction);
    return () => window.removeEventListener("supernova:open-ai-delegate-action", openAiDelegateAction);
  }, [id]);

  const openAccountModal = () => {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("supernova:open-account", { detail: { mode: "create" } }));
    }
  };

  const openAiActionModal = (mode, focus = "", parentCommentId = null) => {
    if (!isAuthenticated || !userData?.name) {
      openAccountModal();
      return;
    }
    if (mode === "comment") {
      setShowComments(true);
      setAiCommentFocus(focus || "");
      setAiCommentParentId(parentCommentId || null);
    } else {
      setAiCommentFocus("");
      setAiCommentParentId(null);
    }
    setAiActionModalMode(mode);
  };

  useEffect(() => {
    if (!collabInviteOpen || collabSearch.trim().length < 1) {
      setCollabSuggestions([]);
      return undefined;
    }

    const controller = new AbortController();
    const timeout = window.setTimeout(async () => {
      try {
        const response = await fetch(
          `${API_BASE_URL}/social-users?search=${encodeURIComponent(collabSearch.trim())}&limit=8`,
          { signal: controller.signal }
        );
        if (!response.ok) {
          setCollabSuggestions([]);
          return;
        }
        const selfKey = String(userData?.name || "").toLowerCase();
        setCollabSuggestions(
          normalizeCollabSuggestions(await response.json().catch(() => [])).filter((user) => user.key !== selfKey)
        );
      } catch (error) {
        if (error?.name !== "AbortError") setCollabSuggestions([]);
      }
    }, 180);

    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [collabInviteOpen, collabSearch, userData?.name]);

  useEffect(() => {
    if (id === undefined || id === null || id === "") return;
    const syncBookmarkState = () => setBookmarked(isBookmarkedId(id));
    syncBookmarkState();
    window.addEventListener(BOOKMARKS_CHANGED_EVENT, syncBookmarkState);
    window.addEventListener("storage", syncBookmarkState);
    return () => {
      window.removeEventListener(BOOKMARKS_CHANGED_EVENT, syncBookmarkState);
      window.removeEventListener("storage", syncBookmarkState);
    };
  }, [id]);

  const handleToggleBookmark = () => {
    if (id === undefined || id === null || id === "") return;
    const isSaved = toggleBookmarkId(id);
    setBookmarked(isSaved);
    setMenuOpen(false);
  };

  const commentsById = useMemo(() => {
    const map = new Map();
    localComments.forEach((comment) => {
      if (comment?.id != null) {
        map.set(String(comment.id), comment);
      }
    });
    return map;
  }, [localComments]);
  const threadedComments = useMemo(() => {
    const roots = [];
    const children = new Map();
    localComments.forEach((comment, index) => {
      const item = { comment, index };
      const parentId = comment?.parent_comment_id;
      const parentKey = parentId == null ? "" : String(parentId);
      if (parentKey && commentsById.has(parentKey)) {
        const list = children.get(parentKey) || [];
        list.push(item);
        children.set(parentKey, list);
      } else {
        roots.push(item);
      }
    });

    const ordered = [];
    const visit = (item, depth = 0) => {
      ordered.push({ ...item, depth });
      const key = item.comment?.id == null ? "" : String(item.comment.id);
      (children.get(key) || []).forEach((child) => visit(child, Math.min(depth + 1, 2)));
    };
    roots.forEach((item) => visit(item, 0));
    return ordered;
  }, [commentsById, localComments]);

  const getFullImageUrl = (url) => {
    const value = normalizeAvatarValue(url);
    if (!value) return null;
    if (value.startsWith("http://") || value.startsWith("https://")) return value;
    return absoluteApiUrl(value);
  };

  const getYouTubeId = (url) => {
    if (!url) return "";
    const regExp =
      /(?:youtube\.com\/(?:watch\?v=|embed\/|v\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/;
    return url.match(regExp)?.[1] || "";
  };

  const getEmbedUrl = (url) => {
    if (!url) return "";
    try {
      if (url.includes("youtube.com/embed/")) return url;
      const videoId = getYouTubeId(url);
      if (videoId) return `https://www.youtube.com/embed/${videoId}`;
      return url;
    } catch {
      return url;
    }
  };

  useEffect(() => {
    if (!shareMenuOpen) return undefined;
    const closeShareMenu = (event) => {
      if (!shareMenuRef.current?.contains(event.target)) {
        setShareMenuOpen(false);
      }
    };
    const closeOnScroll = () => setShareMenuOpen(false);
    document.addEventListener("pointerdown", closeShareMenu);
    window.addEventListener("scroll", closeOnScroll, true);
    window.addEventListener("wheel", closeOnScroll, { passive: true });
    return () => {
      document.removeEventListener("pointerdown", closeShareMenu);
      window.removeEventListener("scroll", closeOnScroll, true);
      window.removeEventListener("wheel", closeOnScroll);
    };
  }, [shareMenuOpen]);

  useEffect(() => {
    if (!menuOpen) return undefined;
    const closeOptionsMenu = (event) => {
      if (!optionsMenuRef.current?.contains(event.target)) {
        setMenuOpen(false);
      }
    };
    const closeOnScroll = () => setMenuOpen(false);
    document.addEventListener("pointerdown", closeOptionsMenu);
    window.addEventListener("scroll", closeOnScroll, true);
    window.addEventListener("wheel", closeOnScroll, { passive: true });
    return () => {
      document.removeEventListener("pointerdown", closeOptionsMenu);
      window.removeEventListener("scroll", closeOnScroll, true);
      window.removeEventListener("wheel", closeOnScroll);
    };
  }, [menuOpen]);

  const handleShareLink = async () => {
    const url = `${window.location.origin}/proposals/${id || ""}`;
    const shareText = title ? `Check out: ${title}` : "Check out this proposal";
    if (navigator.share) {
      try {
        await navigator.share({ title: shareText, url });
        setShareMenuOpen(false);
        return;
      } catch {
        // User cancelled or the native share sheet failed; copy as fallback.
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard unavailable */ }
    setShareMenuOpen(false);
  };

  const handleMessageShare = () => {
    setShareMenuOpen(false);
    if (!userData?.name) {
      window.dispatchEvent(new CustomEvent("supernova:open-account", { detail: { mode: "create" } }));
      return;
    }
    const url = `${window.location.origin}/proposals/${id || ""}`;
    const shareText = title ? `Check out: ${title}` : "Check out this proposal";
    try {
      sessionStorage.setItem(
        "supernova_dm_share_draft",
        JSON.stringify({
          proposalId: id,
          title: shareText,
          url,
          text: `${shareText}\n${url}`,
        })
      );
    } catch {
      // If storage is unavailable, the messages page still opens normally.
    }
    setNotify?.(["Choose someone in messages to share this post."]);
    router.push("/messages");
  };

  const refreshFeeds = () => {
    queryClient.invalidateQueries({ queryKey: ["home-feed"] });
    queryClient.invalidateQueries({ queryKey: ["home-following"] });
    queryClient.invalidateQueries({ queryKey: ["proposals"] });
    queryClient.invalidateQueries({ queryKey: ["user-posts"] });
    queryClient.invalidateQueries({ queryKey: ["desktop-social-graph"] });
    queryClient.invalidateQueries({ queryKey: ["universe-social-graph"] });
  };

  const handleSaveEdit = async () => {
    if (!editText.trim()) {
      setErrorMsg?.(["Post text cannot be empty."]);
      return;
    }
    setOwnerBusy(true);
    try {
      const response = await fetch(`${API_BASE_URL}/proposals/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          title: editText.trim().replace(/\s+/g, " ").slice(0, 70),
          body: editText.trim(),
          author: userData.name,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(formatBackendAuthErrorMessage(payload?.detail, "Unable to edit post."));
      setLocalText(payload.text || editText.trim());
      setEditing(false);
      setMenuOpen(false);
      setNotify?.(["Post updated."]);
      refreshFeeds();
    } catch (error) {
      setErrorMsg?.([formatBackendAuthErrorMessage(error, "Unable to edit post.")]);
    } finally {
      setOwnerBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!isOwner || !window.confirm("Delete this post?")) return;
    setOwnerBusy(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/proposals/${encodeURIComponent(id)}?author=${encodeURIComponent(userData.name)}`,
        { method: "DELETE", headers: authHeaders() }
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(formatBackendAuthErrorMessage(payload?.detail, "Unable to delete post."));
      setDeleted(true);
      setNotify?.(["Post deleted."]);
      refreshFeeds();
    } catch (error) {
      setErrorMsg?.([formatBackendAuthErrorMessage(error, "Unable to delete post.")]);
    } finally {
      setOwnerBusy(false);
    }
  };

  const handleRequestCollab = async (username) => {
    const collaboratorUsername = String(username || collabSearch || "").trim();
    if (!collaboratorUsername || collabBusy) return;
    if (!userData?.name) {
      window.dispatchEvent(new CustomEvent("supernova:open-account", { detail: { mode: "create" } }));
      return;
    }
    if (collaboratorUsername.toLowerCase() === userData.name.toLowerCase()) {
      setCollabError("Choose someone other than yourself.");
      return;
    }

    setCollabBusy(true);
    setCollabError("");
    setCollabStatus("");
    try {
      requireBackendAuthSession();
      const response = await fetch(`${API_BASE_URL}/proposal-collabs/request`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          proposal_id: Number(id),
          collaborator_username: collaboratorUsername,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(formatBackendAuthErrorMessage(payload?.detail, "Unable to invite collaborator."));
      }
      setCollabStatus(`Invite sent to @${payload?.collab?.collaborator?.username || collaboratorUsername}.`);
      setNotify?.([`Collab invite sent to ${payload?.collab?.collaborator?.username || collaboratorUsername}.`]);
      setCollabSearch("");
      setCollabSuggestions([]);
      queryClient.invalidateQueries({ queryKey: ["proposal-collabs"] });
    } catch (error) {
      const message = formatBackendAuthErrorMessage(error, BACKEND_AUTH_MISSING_MESSAGE);
      setCollabError(message);
      setErrorMsg?.([message]);
    } finally {
      setCollabBusy(false);
    }
  };

  const handleMessageAuthor = () => {
    if (!userData?.name) {
      window.dispatchEvent(new CustomEvent("supernova:open-account", { detail: { mode: "create" } }));
      return;
    }
    if (!authorName || isOwner) return;
    setMenuOpen(false);
    router.push(`/messages?to=${encodeURIComponent(authorName)}`);
  };

  const handleToggleFollow = async () => {
    if (!userData?.name) {
      window.dispatchEvent(new CustomEvent("supernova:open-account", { detail: { mode: "create" } }));
      return;
    }
    if (!authorName || isOwner || followBusy) return;
    setFollowBusy(true);
    try {
      const response = await fetch(
        followingAuthor
          ? `${API_BASE_URL}/follows?follower=${encodeURIComponent(userData.name)}&target=${encodeURIComponent(authorName)}`
          : `${API_BASE_URL}/follows`,
        {
          method: followingAuthor ? "DELETE" : "POST",
          headers: followingAuthor ? authHeaders() : authHeaders({ "Content-Type": "application/json" }),
          body: followingAuthor
            ? undefined
            : JSON.stringify({ follower: userData.name, target: authorName }),
        }
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(formatBackendAuthErrorMessage(payload?.detail, "Follow action failed."));
      setFollowingAuthor(Boolean(payload.following));
      setNotify?.([payload.following ? `Following ${authorName}.` : `Unfollowed ${authorName}.`]);
      queryClient.invalidateQueries({ queryKey: ["home-following"] });
      queryClient.invalidateQueries({ queryKey: ["desktop-social-graph"] });
      queryClient.invalidateQueries({ queryKey: ["universe-social-graph"] });
    } catch (error) {
      setErrorMsg?.([formatBackendAuthErrorMessage(error, "Follow action failed.")]);
    } finally {
      setFollowBusy(false);
      setMenuOpen(false);
    }
  };

  const handleDeleteComment = async (commentId) => {
    if (!commentId || !userData?.name || deletingCommentId) return;
    setDeletingCommentId(commentId);
    try {
      const response = await fetch(
        `${API_BASE_URL}/comments/${encodeURIComponent(commentId)}?user=${encodeURIComponent(userData.name)}`,
        { method: "DELETE", headers: authHeaders() }
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(formatBackendAuthErrorMessage(payload?.detail, "Unable to delete comment."));
      setLocalComments((prevComments) => {
        const prunedIds = new Set((payload?.pruned_comment_ids || []).map((item) => String(item)));
        if (payload?.tombstone && payload?.comment) {
          return prevComments
            .filter((comment) => !prunedIds.has(String(comment.id || "")))
            .map((comment) =>
              String(comment.id || "") === String(commentId)
                ? { ...comment, ...payload.comment }
                : comment
            );
        }
        return prevComments.filter(
          (comment) => String(comment.id || "") !== String(commentId) && !prunedIds.has(String(comment.id || ""))
        );
      });
      if (String(replyTarget?.id || "") === String(commentId)) {
        setReplyTarget(null);
      }
      setNotify?.([payload?.tombstone ? "Comment removed, replies preserved." : "Comment deleted."]);
      refreshFeeds();
    } catch (error) {
      setErrorMsg?.([formatBackendAuthErrorMessage(error, "Unable to delete comment.")]);
    } finally {
      setDeletingCommentId(null);
    }
  };

  const handleEditComment = async (commentId, nextText) => {
    if (!commentId || !userData?.name) throw new Error("Sign in to edit this comment.");
    const response = await fetch(`${API_BASE_URL}/comments/${encodeURIComponent(commentId)}`, {
      method: "PATCH",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        user: userData.name,
        comment: nextText,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(formatBackendAuthErrorMessage(payload?.detail, "Unable to edit comment."));
    const updatedComment = payload?.comment ? payload : payload?.comments?.[0] || null;
    setLocalComments((prevComments) =>
      prevComments.map((comment) =>
        String(comment.id || "") === String(commentId)
          ? { ...comment, ...(updatedComment || {}), comment: updatedComment?.comment || nextText }
          : comment
      )
    );
    refreshFeeds();
  };

  const displayVideo = media.video || (getYouTubeId(media.link) ? media.link : null);
  const displayLink = displayVideo === media.link ? null : media.link;
  const displayImages =
    Array.isArray(media.images) && media.images.length > 0
      ? media.images
      : media.image
      ? [media.image]
      : [];
  const displayFile = media.file ? getFullImageUrl(media.file) : "";
  const isPdfFile = /\.pdf(?:$|\?)/i.test(displayFile || "");
  const mediaLayout = media.layout === "grid" ? "grid" : "carousel";
  const userHref = authorName ? `/users/${encodeURIComponent(authorName)}` : "/profile";
  const profileDomainHref = domainAsProfile && profileUrl ? normalizeLinkHref(profileUrl) : "";
  const userVote = likes.some((v) => v.voter === userData?.name)
    ? "like"
    : dislikes.some((v) => v.voter === userData?.name)
    ? "dislike"
    : "";
  const supportSummary = showSupportSummary ? supportSummaryLabel(likes, dislikes, voteSummary) : "";
  const authorLabel = authorName || "Unknown";

  const youtubeId = getYouTubeId(displayVideo);
  const videoThumbnail = youtubeId
    ? `https://i.ytimg.com/vi_webp/${youtubeId}/maxresdefault.webp`
    : "";
  const videoThumbnailFallback = youtubeId
    ? `https://i.ytimg.com/vi/${youtubeId}/hqdefault.jpg`
    : "";

  useEffect(() => {
    const handlePostAction = (event) => {
      const detail = event.detail || {};
      if (String(detail.id) !== String(id)) return;
      if (detail.action === "comment" || detail.action === "engage") {
        setShowComments(true);
      }
      if (detail.action === "comment-posted" && detail.comment) {
        setShowComments(true);
        setLocalComments((prevComments) => [...prevComments, detail.comment]);
      }
    };
    window.addEventListener("supernova:post-action", handlePostAction);
    return () => window.removeEventListener("supernova:post-action", handlePostAction);
  }, [id]);

  useEffect(() => {
    setLocalText(text || "");
    setEditText(text || "");
  }, [id, text]);

  useEffect(() => {
    setLocalComments(Array.isArray(comments) ? comments : []);
  }, [comments, id]);

  useEffect(() => {
    setLocalLogo(logo || "");
  }, [id, logo]);

  useEffect(() => {
    if (!menuOpen || isOwner || !userData?.name || !authorName) return undefined;
    let cancelled = false;
    fetch(
      `${API_BASE_URL}/follows/status?follower=${encodeURIComponent(userData.name)}&target=${encodeURIComponent(authorName)}`,
      { headers: authHeaders() }
    )
      .then((response) => (response.ok ? response.json() : null))
      .then((payload) => {
        if (!cancelled && payload) setFollowingAuthor(Boolean(payload.following));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [authorName, isOwner, menuOpen, userData?.name]);

  useEffect(() => {
    setLocalUserName(userName || "");
  }, [id, userName]);

  useEffect(() => {
    const handleAvatarUpdate = (event) => {
      const detail = event.detail || {};
      if (!detail.username || !authorName) return;
      const aliases = [detail.username, detail.previousUsername, detail.oldUsername]
        .filter(Boolean)
        .map((value) => String(value).toLowerCase());
      if (!aliases.includes(String(authorName).toLowerCase())) return;
      setLocalUserName(detail.username || authorName);
      setLocalLogo(detail.avatar || "");
      setLocalComments((prevComments) =>
        prevComments.map((comment) => {
          const commentUser = String(comment.user || "");
          if (commentUser === "[deleted]" || !aliases.includes(commentUser.toLowerCase())) return comment;
          return {
            ...comment,
            user: detail.username || comment.user,
            user_img: detail.avatar || comment.user_img || "",
            species: detail.species || comment.species,
          };
        })
      );
    };
    window.addEventListener("supernova:profile-avatar-updated", handleAvatarUpdate);
    return () => window.removeEventListener("supernova:profile-avatar-updated", handleAvatarUpdate);
  }, [authorName]);

  if (deleted) return null;

  return (
    <div
      data-proposal-card
      data-proposal-id={id}
      data-proposal-title={(title || localText || "").slice(0, 180)}
      data-proposal-author={authorName || ""}
      data-proposal-text={(localText || title || "").slice(0, 360)}
      data-proposal-user-vote={userVote}
      className={`mobile-post-card bgWhiteTrue social-panel-compact relative mx-auto flex w-full flex-col gap-4 rounded-[1.75rem] p-5 text-[var(--text-black)] shadow-sm ${
        isDetailPage ? "" : "hover:shadow-md"
      }`}
    >
      {/* Header: avatar, name, time, options */}
      <div className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-2">
        <div className="flex min-w-0 items-center gap-3">
          <div className="proposal-author-avatar-cluster flex shrink-0 items-center">
            {profileDomainHref ? (
              <a
                href={profileDomainHref}
                target="_blank"
                rel="noopener noreferrer"
                title="Open profile domain"
                className="proposal-author-avatar-link shrink-0"
                onClick={(event) => event.stopPropagation()}
              >
                <img
                  src={displayAvatar || defaultAvatar}
                  alt="user avatar"
                  onError={(event) => {
                    event.currentTarget.src = defaultAvatar;
                  }}
                  className="h-10 w-10 rounded-full border object-cover"
                  style={authorAvatarStyle}
                />
              </a>
            ) : (
              <Link
                href={userHref}
                scroll
                className="proposal-author-avatar-link shrink-0"
                onClick={(event) => event.stopPropagation()}
              >
                <img
                  src={displayAvatar || defaultAvatar}
                  alt="user avatar"
                  onError={(event) => {
                    event.currentTarget.src = defaultAvatar;
                  }}
                  className="h-10 w-10 rounded-full border object-cover"
                  style={authorAvatarStyle}
                />
              </Link>
            )}
            {avatarApprovedCollabs.length > 0 && (
              <div className="proposal-approved-collab-avatars flex shrink-0 items-center -space-x-2">
                {avatarApprovedCollabs.map((collab) => (
                  <Link
                    key={collab.key}
                    href={`/users/${encodeURIComponent(collab.username)}`}
                    scroll
                    onClick={(event) => event.stopPropagation()}
                    className="proposal-approved-collab-avatar flex h-7 w-7 items-center justify-center overflow-hidden rounded-full text-[0.56rem] font-black uppercase"
                    style={{
                      ...speciesAvatarStyle(collab.species || "human"),
                      backgroundColor: speciesAccentColor(collab.species || "human"),
                    }}
                    title={`Approved collaborator @${collab.username}`}
                  >
                    {collab.avatar ? (
                      <img
                        src={collab.avatar}
                        alt=""
                        className="h-full w-full object-cover"
                        loading="lazy"
                        referrerPolicy="no-referrer"
                      />
                    ) : (
                      collab.username.slice(0, 2).toUpperCase()
                    )}
                  </Link>
                ))}
                {extraAvatarApprovedCollabCount > 0 && (
                  <span className="proposal-approved-collab-avatar proposal-approved-collab-avatar-extra flex h-7 w-7 items-center justify-center rounded-full text-[0.56rem] font-black">
                    +{extraAvatarApprovedCollabCount}
                  </span>
                )}
              </div>
            )}
          </div>
          <div className="min-w-0 text-[0.9rem] leading-tight">
            <div className="proposal-author-inline-line flex min-w-0 flex-wrap items-baseline gap-x-1">
              <Link
                href={userHref}
                scroll
                onClick={(event) => event.stopPropagation()}
                className="proposal-author-inline-name max-w-full truncate font-semibold text-[var(--text-black)]"
              >
                {authorLabel}
              </Link>
              {inlineApprovedCollabs.map((collab) => (
                <span key={collab.key} className="inline-flex min-w-0 items-baseline">
                  <span className="text-[var(--text-gray-light)]">,</span>
                  <Link
                    href={`/users/${encodeURIComponent(collab.username)}`}
                    scroll
                    onClick={(event) => event.stopPropagation()}
                    className="proposal-inline-collab-link ml-1 truncate font-semibold"
                    title={`Approved collaborator ${collab.username}`}
                  >
                    {collab.username}
                  </Link>
                </span>
              ))}
              {extraApprovedCollabCount > 0 && (
                <span className="proposal-inline-collab-extra ml-1 font-black">
                  +{extraApprovedCollabCount}
                </span>
              )}
              <span className="mx-1 text-[var(--text-gray-light)]">{"\u2022"}</span>
              <span className="text-[var(--text-gray-light)]">{time}</span>
            </div>
          </div>
        </div>

        {/* Species icon badge - replaces text label */}
        <div ref={optionsMenuRef} className="relative">
          <button
            type="button"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              setMenuOpen((value) => !value);
            }}
            className="flex h-8 w-8 items-center justify-center rounded-full text-[var(--text-gray-light)] hover:bg-white/[0.07]"
            aria-label="Post options"
          >
            <IoEllipsisHorizontal />
          </button>
          {menuOpen && (
            <div className="proposal-options-menu absolute right-0 top-9 z-20 w-40 overflow-hidden rounded-[0.9rem] border border-[var(--horizontal-line)] bg-[rgba(10,13,19,0.96)] p-1 text-[0.76rem] shadow-[var(--shadow)] backdrop-blur-xl">
              {profileDomainHref && authorName && (
                <Link
                  href={userHref}
                  scroll
                  onClick={() => setMenuOpen(false)}
                  className="flex w-full items-center gap-2 rounded-[0.7rem] px-3 py-2 text-left hover:bg-white/[0.07]"
                >
                  <IoPersonCircleOutline /> View profile
                </Link>
              )}
              <button
                type="button"
                onClick={handleToggleBookmark}
                className={`flex w-full items-center gap-2 rounded-[0.7rem] px-3 py-2 text-left hover:bg-white/[0.07] ${
                  bookmarked ? "text-[var(--blue)]" : ""
                }`}
              >
                <IoMdBookmark /> {bookmarked ? "Saved" : "Save"}
              </button>
              {isOwner ? (
                <>
                  <button
                    type="button"
                    onClick={() => {
                      setEditText(localText || "");
                      setEditing(true);
                      setMenuOpen(false);
                    }}
                    className="flex w-full items-center gap-2 rounded-[0.7rem] px-3 py-2 text-left hover:bg-white/[0.07]"
                  >
                    <IoCreateOutline /> Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setCollabInviteOpen((value) => !value);
                      setCollabStatus("");
                      setCollabError("");
                      setMenuOpen(false);
                    }}
                    className="flex w-full items-center gap-2 rounded-[0.7rem] px-3 py-2 text-left hover:bg-white/[0.07]"
                  >
                    <IoPersonAddOutline /> Invite collab
                  </button>
                  <button
                    type="button"
                    onClick={handleDelete}
                    disabled={ownerBusy}
                    className="flex w-full items-center gap-2 rounded-[0.7rem] px-3 py-2 text-left text-[var(--pink)] hover:bg-white/[0.07] disabled:opacity-50"
                  >
                    <IoTrashOutline /> Delete
                  </button>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={handleMessageAuthor}
                    className="flex w-full items-center gap-2 rounded-[0.7rem] px-3 py-2 text-left hover:bg-white/[0.07]"
                  >
                    <IoChatbubbleOutline /> Message
                  </button>
                  <button
                    type="button"
                    onClick={handleToggleFollow}
                    disabled={followBusy}
                    className="flex w-full items-center gap-2 rounded-[0.7rem] px-3 py-2 text-left hover:bg-white/[0.07] disabled:opacity-50"
                  >
                    {followingAuthor ? <IoPersonRemoveOutline /> : <IoPersonAddOutline />}
                    {followingAuthor ? "Unfollow" : "Follow"}
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {supportSummary && (
        <div className="proposal-support-summary mt-2 inline-flex w-fit max-w-full items-center gap-1.5 rounded-full px-2.5 py-1 text-[0.68rem] font-black uppercase tracking-[0.08em]">
          <IoCheckmark className="text-[0.82rem]" />
          <span className="truncate">{supportSummary}</span>
        </div>
      )}

      {isOwner && collabInviteOpen && (
        <div
          className="collab-invite-panel rounded-[1rem] p-3"
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
          }}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[0.78rem] font-semibold text-[var(--text-black)]">Invite collaborator</p>
              <p className="mt-0.5 text-[0.72rem] text-[var(--text-gray-light)]">
                They must approve before this post appears as a collab.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setCollabInviteOpen(false)}
              className="collab-mini-button flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
              aria-label="Close collaborator invite"
            >
              <IoClose />
            </button>
          </div>
          <div className="mt-3 flex flex-col gap-2">
            <input
              value={collabSearch}
              onChange={(event) => {
                setCollabSearch(event.target.value);
                setCollabStatus("");
                setCollabError("");
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  handleRequestCollab(collabSuggestions[0]?.username || collabSearch);
                }
                if (event.key === "Escape") setCollabInviteOpen(false);
              }}
              placeholder="Search username"
              className="collab-invite-input w-full rounded-[0.85rem] px-3 py-2 text-[0.84rem] outline-none"
            />
            {collabSearch.trim() && collabSuggestions.length > 0 && (
              <div className="flex max-h-44 flex-col gap-1 overflow-y-auto pr-1">
                {collabSuggestions.map((user) => (
                  <button
                    type="button"
                    key={user.username}
                    onClick={() => handleRequestCollab(user.username)}
                    disabled={collabBusy}
                    className="collab-user-suggestion flex w-full items-center gap-2 rounded-[0.8rem] px-2.5 py-2 text-left disabled:opacity-55"
                  >
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center overflow-hidden rounded-full bg-white/[0.08] text-[0.62rem] font-black uppercase">
                      {user.avatar ? (
                        <img
                          src={user.avatar}
                          alt=""
                          className="h-full w-full object-cover"
                          loading="lazy"
                          referrerPolicy="no-referrer"
                        />
                      ) : (
                        user.initials
                      )}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-[0.8rem] font-semibold">@{user.username}</span>
                    <span className="shrink-0 rounded-full bg-white/[0.07] px-1.5 py-0.5 text-[0.58rem] font-semibold uppercase tracking-[0.08em] text-[var(--text-gray-light)]">
                      {user.species}
                    </span>
                  </button>
                ))}
              </div>
            )}
            {collabSearch.trim() && !collabSuggestions.length && !collabBusy && (
              <p className="text-[0.72rem] text-[var(--text-gray-light)]">No matching users yet.</p>
            )}
            {collabStatus && <p className="text-[0.74rem] font-semibold text-[var(--neon-blue)]">{collabStatus}</p>}
            {collabError && <p className="text-[0.74rem] font-semibold text-[var(--pink)]">{collabError}</p>}
          </div>
        </div>
      )}

      {/* Post content (text + media) */}
      <div className="flex w-full min-w-0 flex-col gap-3">
        <div className="flex min-w-0 flex-col gap-3">
          {editing ? (
            <div className="flex flex-col gap-2">
              <textarea
                value={editText}
                onChange={(event) => setEditText(event.target.value)}
                className="composer-textarea min-h-28 resize-y rounded-[1rem] border border-[var(--horizontal-line)] bg-white/[0.055] px-3 py-3 text-[0.92rem] outline-none"
              />
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setEditing(false);
                    setEditText(localText || "");
                  }}
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-white/[0.07] text-[var(--text-gray-light)]"
                  aria-label="Cancel edit"
                >
                  <IoClose />
                </button>
                <button
                  type="button"
                  onClick={handleSaveEdit}
                  disabled={ownerBusy}
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--pink)] text-white shadow-[var(--shadow-pink)] disabled:opacity-50"
                  aria-label="Save edit"
                >
                  <IoCheckmark />
                </button>
              </div>
            </div>
          ) : localText && (
            <div className="flex min-w-0 flex-col gap-1">
              <p
                className="post-text text-[0.94rem] leading-6 break-words text-[var(--transparent-black)]"
                style={readMore ? undefined : { maxHeight: "7.5rem", overflow: "hidden" }}
              >
                <LinkifiedText text={localText} enableMentions validMentionUsernames={verifiedMentions} />
              </p>
              {(localText.length > 220 || (localText.match(/\n/g) || []).length >= 4) && (
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); e.preventDefault(); setReadMore((v) => !v); }}
                  className="w-fit text-[0.82rem] font-medium text-[var(--neon-blue)]"
                >
                  {readMore ? "Show Less" : "Read More"}
                </button>
              )}
            </div>
          )}

          {isDecisionProposal && (
            <div className="flex flex-wrap items-center gap-1.5 text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-[var(--text-gray-light)]">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--horizontal-line)] bg-white/[0.045] px-2.5 py-1 text-[var(--pink)]">
                <IoShieldCheckmarkOutline className="text-[0.82rem]" />
                Decision{decisionThresholdLabel ? ` ${decisionThresholdLabel}` : ""}
              </span>
              {decisionDeadlineLabel && (
                <span
                  className="inline-flex items-center gap-1.5 rounded-full border border-[var(--horizontal-line)] bg-white/[0.035] px-2.5 py-1"
                  title="Voting countdown"
                >
                  <IoTimeOutline className="text-[0.78rem] text-[var(--pink)]" />
                  {decisionDeadlineLabel}
                </span>
              )}
              <span
                className="inline-flex items-center gap-1.5 rounded-full border border-[var(--horizontal-line)] bg-white/[0.035] px-2.5 py-1"
                title={decisionExecutionTitle}
              >
                <DecisionExecutionIcon className="text-[0.78rem] text-[var(--pink)]" />
                {decisionExecutionLabel}
              </span>
            </div>
          )}

          {displayImages.length > 0 && (
            <MediaGallery
              images={displayImages}
              layout={mediaLayout}
              title={title}
              getUrl={getFullImageUrl}
            />
          )}

          {displayVideo && (
            <>
              {youtubeId && !videoOpen ? (
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); e.preventDefault(); setVideoOpen(true); }}
                  className="mobile-media-bleed relative aspect-video w-full overflow-hidden rounded-[1.15rem] bg-[var(--gray)] shadow-sm"
                >
                  <img
                    src={videoThumbnail}
                    alt={title}
                    className="h-full w-full object-cover"
                    onError={(e) => { if (e.currentTarget.src !== videoThumbnailFallback) e.currentTarget.src = videoThumbnailFallback; }}
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/45 to-transparent" />
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className="flex h-16 w-16 items-center justify-center rounded-full bg-[rgba(255,59,48,0.94)] text-[1.4rem] text-white shadow-[0_0_24px_rgba(255,59,48,0.45)]">▶</span>
                  </div>
                </button>
              ) : youtubeId ? (
                <>
                  {!videoLoaded && (
                    <div className="mobile-media-bleed flex h-52 w-full items-center justify-center rounded-[18px] bg-[var(--gray)] shadow-sm">
                      <img src="/spinner.svg" alt="loading" />
                    </div>
                  )}
                  <div className={`mobile-media-bleed aspect-video w-full overflow-hidden rounded-[18px] bg-[var(--gray)] shadow-sm ${videoLoaded ? "" : "hidden"}`}>
                    <iframe
                      src={getEmbedUrl(displayVideo)}
                      title="Video"
                      width="100%"
                      height="100%"
                      frameBorder="0"
                      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                      allowFullScreen
                      onLoad={() => setVideoLoaded(true)}
                      className="h-full w-full"
                    />
                  </div>
                </>
              ) : (
                <div className="mobile-media-bleed aspect-video w-full overflow-hidden rounded-[18px] bg-[var(--gray)] shadow-sm">
                  <video
                    src={getFullImageUrl(displayVideo)}
                    controls
                    preload="metadata"
                    className="h-full w-full object-cover"
                  />
                </div>
              )}
            </>
          )}
        </div>

        {displayLink && (
          <div className="flex items-center gap-3 rounded-[0.8rem] bg-[rgba(255,255,255,0.05)] p-4 hover:bg-[rgba(255,255,255,0.08)] transition-colors">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--blue)] text-white shadow-[var(--shadow-blue)]">
              <FaLink className="text-[1.2rem]" />
            </div>
            <div className="min-w-0 flex-1">
              <a href={displayLink} target="_blank" rel="noopener noreferrer"
                className="truncate block text-[0.85rem] font-medium text-[var(--neon-blue)] hover:underline"
                onClick={(e) => e.stopPropagation()}>
                {displayLink}
              </a>
            </div>
          </div>
        )}

        {displayFile && isPdfFile && (
          <div className="mobile-media-bleed">
            <PdfPager src={displayFile} title={`${title || "Post"} PDF`} />
          </div>
        )}

        {displayFile && !isPdfFile && (
          <a
            href={displayFile}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="flex w-fit cursor-pointer items-center gap-2 rounded-full bg-[var(--blue)] px-3 py-2 text-white shadow-[var(--shadow-blue)]"
          >
            <FaFileAlt className="text-[1.2rem]" />
            <p>View document</p>
          </a>
        )}

        {/* Unified action bar: voting, comments, and share */}
        <div
          className="post-action-bar mt-0.5 flex w-full items-center gap-2 rounded-[0.8rem] px-1.5 py-1.5"
          onClick={(e) => { e.stopPropagation(); e.preventDefault(); }}
        >
          {/* Left: voting controls */}
          <div className="min-w-0 flex-1">
            <LikesDeslikes
              setErrorMsg={setErrorMsg}
              initialLikes={likes.length}
              initialDislikes={dislikes.length}
              initialLikesList={likes}
              initialDislikesList={dislikes}
              initialClicked={userVote || null}
              proposalId={id}
            />
          </div>

          {/* Right: comment and share */}
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              onClick={() => openAiActionModal("review")}
              className={`flex h-8 w-8 items-center justify-center rounded-full transition-colors ${
                aiActionModalMode === "review"
                  ? "bg-[var(--pink)] text-white shadow-[var(--shadow-pink)]"
                  : "text-[var(--text-gray-light)] hover:bg-[rgba(255,255,255,0.07)]"
              }`}
              title="Generate AI review"
              aria-label="Generate AI review"
              aria-expanded={aiActionModalMode === "review"}
            >
              <IoSparklesOutline className="text-[0.9rem]" />
            </button>
            {/* Comment toggle */}
            <button
              type="button"
              onClick={() => setShowComments((v) => !v)}
              className={`flex h-8 items-center gap-1.5 rounded-full px-2 transition-colors ${
                showComments
                  ? "bg-[var(--pink)] text-white shadow-[var(--shadow-pink)]"
                  : "text-[var(--text-gray-light)] hover:bg-[rgba(255,255,255,0.07)]"
              }`}
            >
              <FaCommentAlt className="text-[0.72rem]" />
              <span className="text-[0.75rem] font-medium">{localComments.length}</span>
            </button>

            {/* Share */}
            <div ref={shareMenuRef} className="relative">
              <button
                type="button"
                onClick={() => setShareMenuOpen((value) => !value)}
                className={`flex h-8 w-8 items-center justify-center rounded-full transition-colors ${
                  copied || shareMenuOpen
                    ? "bg-[rgba(255,255,255,0.12)] text-[var(--pink)]"
                    : "text-[var(--text-gray-light)] hover:bg-[rgba(255,255,255,0.07)]"
                }`}
                title={copied ? "Link copied!" : "Share"}
                aria-label="Share"
                aria-haspopup="menu"
                aria-expanded={shareMenuOpen}
              >
                <FaShare className="text-[0.78rem]" />
              </button>
              {shareMenuOpen && (
                <div
                  role="menu"
                  className="absolute bottom-10 right-0 z-30 w-40 overflow-hidden rounded-[0.9rem] border border-[var(--horizontal-line)] bg-[var(--surface-strong)] p-1.5 text-[0.78rem] font-semibold text-[var(--text-black)] shadow-[0_18px_60px_rgba(0,0,0,0.35)] backdrop-blur-xl"
                >
                  <button
                    type="button"
                    role="menuitem"
                    onClick={handleMessageShare}
                    className="flex w-full items-center gap-2 rounded-[0.7rem] px-2.5 py-2 text-left transition-colors hover:bg-[rgba(255,255,255,0.08)]"
                  >
                    <IoChatbubbleOutline className="text-[0.95rem] text-[var(--pink)]" />
                    Send in DM
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={handleShareLink}
                    className="flex w-full items-center gap-2 rounded-[0.7rem] px-2.5 py-2 text-left transition-colors hover:bg-[rgba(255,255,255,0.08)]"
                  >
                    <FaLink className="text-[0.78rem] text-[var(--pink)]" />
                    {copied ? "Copied" : "Share link"}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Comments section */}
        {(showComments || isDetailPage) && (
          <div className="comments-section flex min-w-0 flex-col gap-2 rounded-[15px] bg-[rgba(255,255,255,0.03)] p-2">
            <div className="flex min-w-0 items-center justify-between gap-3 px-1">
              <span className="truncate text-[0.72rem] font-semibold uppercase tracking-[0.14em] text-[var(--text-gray-light)]">
                Comments
              </span>
              <div className="flex shrink-0 items-center gap-1.5">
                <button
                  type="button"
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    openAiActionModal("comment");
                  }}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-[var(--horizontal-line)] text-[var(--text-black)] hover:border-[var(--pink)] hover:text-[var(--pink)]"
                  aria-label="Generate AI comment"
                  title="Generate AI comment"
                  aria-expanded={aiActionModalMode === "comment"}
                >
                  <IoSparklesOutline className="text-[0.82rem]" />
                </button>
                <span className="rounded-full bg-white/[0.055] px-2.5 py-1 text-[0.68rem] font-bold text-[var(--text-gray-light)]">
                  {localComments.length}
                </span>
              </div>
            </div>
            <div onClick={(e) => { e.stopPropagation(); e.preventDefault(); }}>
              <InsertComment
                setErrorMsg={setErrorMsg}
                setNotify={setNotify}
                proposalId={id}
                setLocalComments={setLocalComments}
                parentComment={null}
                onCancelReply={() => setReplyTarget(null)}
              />
            </div>
            <div className="comments-thread-list flex min-w-0 flex-col gap-2">
              {threadedComments.map(({ comment, index, depth }) => {
                const commentId = comment.id ?? "";
                const parent = comment.parent_comment_id == null ? null : commentsById.get(String(comment.parent_comment_id));
                const isActiveReplyTarget = Boolean(
                  replyTarget?.id && commentId && String(replyTarget.id) === String(commentId)
                );
                const isDeletedComment = Boolean(comment.deleted || comment.user === "[deleted]");
                const isCommentAuthor = Boolean(
                  comment.user &&
                    userData?.name &&
                    String(comment.user).toLowerCase() === String(userData.name).toLowerCase()
                );
                const canDeleteComment = Boolean(!isDeletedComment && commentId && isCommentAuthor);
                return (
                  <DisplayComments
                    key={commentId || `${comment.user || "comment"}-${index}`}
                    commentId={commentId}
                    proposalId={id}
                    name={comment.user}
                    image={comment.user_img}
                    species={comment.species}
                    comment={comment.comment}
                    likes={comment.likes}
                    dislikes={comment.dislikes}
                    canDelete={canDeleteComment}
                    canEdit={Boolean(!isDeletedComment && commentId && isCommentAuthor)}
                    deleting={String(deletingCommentId || "") === String(commentId)}
                    onDelete={() => handleDeleteComment(commentId)}
                    onEdit={handleEditComment}
                    onReply={(target) => {
                      setReplyTarget(target);
                      setShowComments(true);
                    }}
                    onAskAi={(target) => {
                      const excerpt = String(target?.comment || "").replace(/\s+/g, " ").slice(0, 160);
                      openAiActionModal("comment", `Respond to @${target?.user || "this comment"}: ${excerpt}`, target?.id || null);
                    }}
                    replyingToName={parent?.user || ""}
                    depth={depth}
                    setErrorMsg={setErrorMsg}
                    setNotify={setNotify}
                  >
                    {isActiveReplyTarget && (
                      <div onClick={(e) => { e.stopPropagation(); e.preventDefault(); }}>
                        <InsertComment
                          setErrorMsg={setErrorMsg}
                          setNotify={setNotify}
                          proposalId={id}
                          setLocalComments={setLocalComments}
                          parentComment={replyTarget}
                          onCancelReply={() => setReplyTarget(null)}
                        />
                      </div>
                    )}
                  </DisplayComments>
                );
              })}
            </div>
          </div>
        )}
      </div>
      <AiDelegateActionModal
        open={Boolean(aiActionModalMode)}
        mode={aiActionModalMode}
        target={{
          id,
          title,
          text: localText,
          author: authorName,
          species: specie,
          media,
          parent_comment_id: aiActionModalMode === "comment" ? aiCommentParentId : null,
        }}
        initialFocus={aiActionModalMode === "comment" ? aiCommentFocus : ""}
        onClose={() => {
          setAiActionModalMode("");
          setAiCommentParentId(null);
        }}
        onApproved={(payload, draftAction) => {
          const publishedComment = payload?.summary?.comment;
          if (publishedComment && typeof publishedComment === "object" && (aiActionModalMode === "comment" || aiActionModalMode === "review")) {
            setLocalComments((items) => [...items, publishedComment]);
            setShowComments(true);
          }
          if (aiActionModalMode === "review" && payload?.summary?.vote) {
            window.dispatchEvent(new CustomEvent("supernova:post-action", {
              detail: {
                id,
                action: "vote-recorded",
                vote: payload.summary.vote,
                voter: payload.summary.actor,
                voter_type: payload.summary.actor_species || "ai",
              },
            }));
          }
          const draftPayload = draftAction?.draft_payload || {};
          const actorName =
            draftPayload.ai_actor_display_name ||
            draftPayload.display_name ||
            draftPayload.ai_actor_username ||
            "AI delegate";
          setNotify?.([`Published as ${actorName}.`]);
          refreshFeeds();
        }}
        onCanceled={() => {
          setNotify?.(["Canceled - nothing published."]);
        }}
      />
    </div>
  );
}

export default ProposalCard;
