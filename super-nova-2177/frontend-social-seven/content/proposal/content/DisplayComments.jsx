import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createPortal } from "react-dom";
import { BiSolidDislike, BiSolidLike } from "react-icons/bi";
import { useQueryClient } from "@tanstack/react-query";
import {
  IoArrowUndoOutline,
  IoChatbubbleOutline,
  IoCheckmark,
  IoClose,
  IoCreateOutline,
  IoEllipsisHorizontal,
  IoPersonAddOutline,
  IoPersonRemoveOutline,
  IoShareSocialOutline,
  IoSparklesOutline,
  IoTrashOutline,
} from "react-icons/io5";
import { API_BASE_URL } from "@/utils/apiBase";
import { authHeaders, formatBackendAuthErrorMessage } from "@/utils/authSession";
import { avatarDisplayUrl, normalizeAvatarValue } from "@/utils/avatar";
import LinkifiedText from "@/utils/linkify";
import { speciesAvatarStyle } from "@/utils/species";
import { useVerifiedMentionUsernames } from "@/utils/verifiedMentions";
import { useUser } from "@/content/profile/UserContext";

function DisplayComments({
  commentId = "",
  proposalId = "",
  comment,
  name,
  image,
  species = "human",
  likes = [],
  dislikes = [],
  canDelete = false,
  canEdit = false,
  onDelete = () => {},
  onEdit = async () => {},
  onReply = () => {},
  onAskAi = () => {},
  replyingToName = "",
  depth = 0,
  deleting = false,
  setErrorMsg = () => {},
  setNotify = () => {},
  children = null,
}) {
  const [imageFailed, setImageFailed] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(comment || "");
  const [editBusy, setEditBusy] = useState(false);
  const [followBusy, setFollowBusy] = useState(false);
  const [voteBusy, setVoteBusy] = useState(false);
  const [localLikes, setLocalLikes] = useState(Array.isArray(likes) ? likes : []);
  const [localDislikes, setLocalDislikes] = useState(Array.isArray(dislikes) ? dislikes : []);
  const [followingAuthor, setFollowingAuthor] = useState(false);
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0 });
  const menuButtonRef = useRef(null);
  const menuPanelRef = useRef(null);
  const router = useRouter();
  const queryClient = useQueryClient();
  const { userData, isAuthenticated } = useUser();
  const verifiedMentions = useVerifiedMentionUsernames(comment);

  const getInitials = (fullName) => {
    if (!fullName) return "SN";
    const parts = fullName.trim().split(/\s+/);
    const firstInitial = parts[0]?.[0] || "";
    const lastInitial = parts.length > 1 ? parts[parts.length - 1]?.[0] || "" : "";
    return (firstInitial + lastInitial).toUpperCase() || "SN";
  };

  const initials = getInitials(name);
  const imageUrl = normalizeAvatarValue(image) ? avatarDisplayUrl(image) : "";
  const avatarStyle = speciesAvatarStyle(species);
  const profileHref = name ? `/users/${encodeURIComponent(name)}` : "/profile";
  const depthOffsetStyle = depth
    ? { marginLeft: `${Math.min(depth, 2) * 0.85}rem`, width: `calc(100% - ${Math.min(depth, 2) * 0.85}rem)` }
    : undefined;
  const isSelf = Boolean(
    name && userData?.name && String(name).toLowerCase() === String(userData.name).toLowerCase()
  );
  const isDeleted = name === "[deleted]";
  const showMenu = !isDeleted && Boolean(name || canDelete || canEdit);
  const userVote = userData?.name && localLikes.some((vote) => String(vote?.voter || "").toLowerCase() === String(userData.name).toLowerCase())
    ? "like"
    : userData?.name && localDislikes.some((vote) => String(vote?.voter || "").toLowerCase() === String(userData.name).toLowerCase())
    ? "dislike"
    : "";

  useEffect(() => {
    setEditText(comment || "");
  }, [comment]);

  useEffect(() => {
    setLocalLikes(Array.isArray(likes) ? likes : []);
    setLocalDislikes(Array.isArray(dislikes) ? dislikes : []);
  }, [likes, dislikes]);

  useEffect(() => {
    if (!menuOpen || isSelf || !isAuthenticated || !userData?.name || !name) return undefined;
    let cancelled = false;
    fetch(
      `${API_BASE_URL}/follows/status?follower=${encodeURIComponent(userData.name)}&target=${encodeURIComponent(name)}`,
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
  }, [isAuthenticated, isSelf, menuOpen, name, userData?.name]);

  useEffect(() => {
    if (!menuOpen || typeof window === "undefined") return undefined;

    const updateMenuPosition = () => {
      const rect = menuButtonRef.current?.getBoundingClientRect();
      if (!rect) return;
      const width = 160;
      const rowCount = Number(canEdit) + Number(canDelete) + (!isSelf && name ? 2 : 0);
      const menuHeight = Math.max(44, rowCount * 36 + 8);
      const left = Math.min(Math.max(8, rect.right - width), window.innerWidth - width - 8);
      let top = rect.bottom + 6;
      if (top + menuHeight > window.innerHeight - 8) {
        top = Math.max(8, rect.top - menuHeight - 6);
      }
      setMenuPosition({ top, left });
    };

    updateMenuPosition();
    window.addEventListener("resize", updateMenuPosition);
    window.addEventListener("scroll", updateMenuPosition, true);
    return () => {
      window.removeEventListener("resize", updateMenuPosition);
      window.removeEventListener("scroll", updateMenuPosition, true);
    };
  }, [canDelete, canEdit, isSelf, menuOpen, name]);

  useEffect(() => {
    if (!menuOpen || typeof document === "undefined") return undefined;
    const handleOutside = (event) => {
      if (menuButtonRef.current?.contains(event.target)) return;
      if (menuPanelRef.current?.contains(event.target)) return;
      setMenuOpen(false);
    };
    document.addEventListener("pointerdown", handleOutside);
    return () => document.removeEventListener("pointerdown", handleOutside);
  }, [menuOpen]);

  useEffect(() => {
    if (!menuOpen || typeof window === "undefined") return undefined;
    const closeOnScroll = () => setMenuOpen(false);
    window.addEventListener("scroll", closeOnScroll, true);
    window.addEventListener("wheel", closeOnScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", closeOnScroll, true);
      window.removeEventListener("wheel", closeOnScroll);
    };
  }, [menuOpen]);

  const requireAccount = () => {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("supernova:open-account", { detail: { mode: "create" } }));
    }
  };

  const handleMessage = () => {
    if (!isAuthenticated || !userData?.name) {
      requireAccount();
      return;
    }
    if (!name || isSelf) return;
    setMenuOpen(false);
    router.push(`/messages?to=${encodeURIComponent(name)}`);
  };

  const handleToggleFollow = async () => {
    if (!isAuthenticated || !userData?.name) {
      requireAccount();
      return;
    }
    if (!name || isSelf || followBusy) return;
    setFollowBusy(true);
    try {
      const response = await fetch(
        followingAuthor
          ? `${API_BASE_URL}/follows?follower=${encodeURIComponent(userData.name)}&target=${encodeURIComponent(name)}`
          : `${API_BASE_URL}/follows`,
        {
          method: followingAuthor ? "DELETE" : "POST",
          headers: followingAuthor ? authHeaders() : authHeaders({ "Content-Type": "application/json" }),
          body: followingAuthor ? undefined : JSON.stringify({ follower: userData.name, target: name }),
        }
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(formatBackendAuthErrorMessage(payload?.detail, "Follow action failed."));
      setFollowingAuthor(Boolean(payload.following));
      setNotify([payload.following ? `Following ${name}.` : `Unfollowed ${name}.`]);
      queryClient.invalidateQueries({ queryKey: ["home-following"] });
      queryClient.invalidateQueries({ queryKey: ["desktop-social-graph"] });
      queryClient.invalidateQueries({ queryKey: ["universe-social-graph"] });
    } catch (error) {
      setErrorMsg([formatBackendAuthErrorMessage(error, "Follow action failed.")]);
    } finally {
      setFollowBusy(false);
      setMenuOpen(false);
    }
  };

  const updateVoteLists = (payload, choice = "") => {
    const nextLikes = Array.isArray(payload?.likes) ? payload.likes : [];
    const nextDislikes = Array.isArray(payload?.dislikes) ? payload.dislikes : [];
    setLocalLikes(nextLikes);
    setLocalDislikes(nextDislikes);
  };

  const handleCommentVote = async (choice) => {
    if (!commentId || voteBusy || isDeleted) return;
    if (!isAuthenticated || !userData?.name) {
      requireAccount();
      return;
    }
    const isToggleOff = (choice === "up" && userVote === "like") || (choice === "down" && userVote === "dislike");
    setVoteBusy(true);
    try {
      const endpoint = `${API_BASE_URL}/comments/${encodeURIComponent(commentId)}/votes`;
      const response = await fetch(
        isToggleOff ? `${endpoint}?username=${encodeURIComponent(userData.name)}` : endpoint,
        {
          method: isToggleOff ? "DELETE" : "POST",
          headers: isToggleOff ? authHeaders() : authHeaders({ "Content-Type": "application/json" }),
          body: isToggleOff
            ? undefined
            : JSON.stringify({
                username: userData.name,
                choice,
                voter_type: userData.species || "human",
              }),
        }
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(formatBackendAuthErrorMessage(payload?.detail, "Unable to vote on comment."));
      updateVoteLists(payload, isToggleOff ? "" : choice);
      queryClient.invalidateQueries({ queryKey: ["home-feed"] });
      queryClient.invalidateQueries({ queryKey: ["proposals"] });
    } catch (error) {
      setErrorMsg([formatBackendAuthErrorMessage(error, "Unable to vote on comment.")]);
    } finally {
      setVoteBusy(false);
    }
  };

  const handleShareComment = async () => {
    if (!proposalId || !commentId || typeof window === "undefined") return;
    const url = `${window.location.origin}/proposals/${proposalId}#comment-${commentId}`;
    try {
      if (navigator.share) {
        await navigator.share({ title: `Comment by ${name || "SuperNova"}`, url });
      } else {
        await navigator.clipboard.writeText(url);
        setNotify(["Comment link copied."]);
      }
    } catch {
      try {
        await navigator.clipboard.writeText(url);
        setNotify(["Comment link copied."]);
      } catch {
        setErrorMsg(["Unable to share this comment from this browser."]);
      }
    }
  };

  const handleSaveEdit = async () => {
    const nextText = editText.trim();
    if (!nextText) {
      setErrorMsg(["Comment cannot be empty."]);
      return;
    }
    setEditBusy(true);
    try {
      await onEdit(commentId, nextText);
      setEditing(false);
      setMenuOpen(false);
      setNotify(["Comment updated."]);
    } catch (error) {
      setErrorMsg([formatBackendAuthErrorMessage(error, "Unable to edit comment.")]);
    } finally {
      setEditBusy(false);
    }
  };

  const menuPanel =
    menuOpen && typeof document !== "undefined"
      ? createPortal(
          <div
            ref={menuPanelRef}
            className="proposal-options-menu fixed z-[2147482500] w-40 overflow-hidden rounded-[0.9rem] border border-[var(--horizontal-line)] bg-[rgba(10,13,19,0.96)] p-1 text-[0.76rem] shadow-[var(--shadow)] backdrop-blur-xl"
            style={{ top: menuPosition.top, left: menuPosition.left }}
          >
            {canEdit && (
              <button
                type="button"
                onClick={() => {
                  setEditText(comment || "");
                  setEditing(true);
                  setMenuOpen(false);
                }}
                className="flex w-full items-center gap-2 rounded-[0.7rem] px-3 py-2 text-left hover:bg-white/[0.07]"
              >
                <IoCreateOutline /> Edit
              </button>
            )}
            {commentId && name && !isDeleted && (
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  onReply({ id: commentId, user: name, comment });
                }}
                className="flex w-full items-center gap-2 rounded-[0.7rem] px-3 py-2 text-left hover:bg-white/[0.07]"
              >
                <IoArrowUndoOutline /> Reply
              </button>
            )}
            {canDelete && (
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  onDelete();
                }}
                disabled={deleting}
                className="flex w-full items-center gap-2 rounded-[0.7rem] px-3 py-2 text-left text-[var(--pink)] hover:bg-white/[0.07] disabled:opacity-50"
              >
                <IoTrashOutline /> Delete
              </button>
            )}
            {!isSelf && name && (
              <>
                <button
                  type="button"
                  onClick={handleMessage}
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
          </div>,
          document.body
        )
      : null;

  return (
    <>
    <div
      id={commentId ? `comment-${commentId}` : undefined}
      className="comment-row flex w-full min-w-0 items-start gap-2"
      style={depthOffsetStyle}
    >
      {isDeleted ? (
        <div className="shrink-0" aria-hidden="true">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white/[0.045] p-2 text-[var(--text-gray-light)] shadow-sm">
            <IoTrashOutline />
          </div>
        </div>
      ) : (
        <Link href={profileHref} scroll className="shrink-0" aria-label={`${name || "User"} profile`}>
          {imageUrl && !imageFailed ? (
            <img
              src={imageUrl}
              alt={name}
              className="h-9 w-9 rounded-full border object-cover"
              style={avatarStyle}
              onError={() => setImageFailed(true)}
            />
          ) : (
            <div className="flex h-9 w-9 items-center justify-center rounded-full border bg-[var(--gray)] p-2" style={avatarStyle}>
              <p className="text-[0.78rem] font-semibold">{initials}</p>
            </div>
          )}
        </Link>
      )}

      <div className="comment-bubble flex min-w-0 flex-1 flex-col gap-1 rounded-[0.95rem] bg-[rgba(255,255,255,0.04)] p-3 shadow-sm">
        <div className="flex min-w-0 items-center justify-between gap-2">
          {isDeleted ? (
            <span className="truncate text-[0.88rem] font-semibold text-[var(--text-gray-light)]">
              Deleted comment
            </span>
          ) : (
            <Link href={profileHref} className="truncate text-[0.88rem] font-semibold text-[var(--text-black)]">
              {name}
            </Link>
          )}
          {showMenu && (
            <div className="relative shrink-0">
              <button
                ref={menuButtonRef}
                type="button"
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  setMenuOpen((value) => !value);
                }}
                className="flex h-7 w-7 items-center justify-center rounded-full text-[var(--text-gray-light)] hover:bg-white/[0.07]"
                aria-label="Comment options"
              >
                <IoEllipsisHorizontal />
              </button>
            </div>
          )}
        </div>
        {editing ? (
          <div className="flex flex-col gap-2">
            <textarea
              value={editText}
              onChange={(event) => setEditText(event.target.value)}
              className="composer-textarea min-h-20 resize-none rounded-[0.85rem] border border-[var(--horizontal-line)] bg-white/[0.055] px-3 py-2 text-[0.86rem] leading-5 outline-none"
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setEditing(false);
                  setEditText(comment || "");
                }}
                className="flex h-8 w-8 items-center justify-center rounded-full bg-white/[0.07] text-[var(--text-gray-light)]"
                aria-label="Cancel comment edit"
              >
                <IoClose />
              </button>
              <button
                type="button"
                onClick={handleSaveEdit}
                disabled={editBusy}
                className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--pink)] text-white shadow-[var(--shadow-pink)] disabled:opacity-50"
                aria-label="Save comment edit"
              >
                <IoCheckmark />
              </button>
            </div>
          </div>
        ) : (
          <>
            {replyingToName && (
              <p className="text-[0.68rem] font-semibold text-[var(--text-gray-light)]">
                Replying to {replyingToName}
              </p>
            )}
            <p className={`break-words text-[0.86rem] leading-6 [overflow-wrap:anywhere] ${
              isDeleted ? "italic text-[var(--text-gray-light)]" : "text-[var(--transparent-black)]"
            }`}>
              <LinkifiedText text={comment} enableMentions validMentionUsernames={verifiedMentions} />
            </p>
          </>
        )}
      </div>
    </div>
    {!isDeleted && (
      <div className="comment-inline-actions flex w-full min-w-0" style={depthOffsetStyle}>
        <div className="ml-11 flex min-w-0 flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => handleCommentVote("down")}
            disabled={voteBusy}
            className={`comment-action-icon ${userVote === "dislike" ? "is-dislike" : ""}`}
            aria-label="Downvote comment"
            title="Downvote"
          >
            <BiSolidDislike />
            {localDislikes.length > 0 && <span>{localDislikes.length}</span>}
          </button>
          <button
            type="button"
            onClick={() => handleCommentVote("up")}
            disabled={voteBusy}
            className={`comment-action-icon ${userVote === "like" ? "is-like" : ""}`}
            aria-label="Upvote comment"
            title="Upvote"
          >
            <BiSolidLike />
            {localLikes.length > 0 && <span>{localLikes.length}</span>}
          </button>
          {commentId && name && (
            <button
              type="button"
              onClick={() => onReply({ id: commentId, user: name, comment })}
              className="comment-action-icon"
              aria-label="Reply to comment"
              title="Reply"
            >
              <IoArrowUndoOutline />
            </button>
          )}
          <button
            type="button"
            onClick={() => onAskAi({ id: commentId, user: name, comment })}
            className="comment-action-icon"
            aria-label="Ask AI delegate to comment"
            title="Ask AI"
          >
            <IoSparklesOutline />
          </button>
          <button
            type="button"
            onClick={handleShareComment}
            className="comment-action-icon"
            aria-label="Share comment"
            title="Share"
          >
            <IoShareSocialOutline />
          </button>
        </div>
      </div>
    )}
    {children && (
      <div className="comment-inline-reply flex w-full min-w-0" style={depthOffsetStyle}>
        <div className="ml-11 min-w-0 flex-1">
          {children}
        </div>
      </div>
    )}
    {menuPanel}
    </>
  );
}

export default DisplayComments;
