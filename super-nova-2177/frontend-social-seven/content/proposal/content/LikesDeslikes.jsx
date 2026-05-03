"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { BiSolidDislike, BiSolidLike } from "react-icons/bi";
import { IoChevronUp } from "react-icons/io5";
import { useUser } from "@/content/profile/UserContext";
import { API_BASE_URL } from "@/utils/apiBase";
import {
  BACKEND_AUTH_MISSING_MESSAGE,
  authHeaders,
  formatBackendAuthErrorMessage,
  requireBackendAuthSession,
} from "@/utils/authSession";
import { buildWeightedVoteSummary } from "@/utils/voteWeights";
import LikesInfo from "./LikesInfo";

const SLIDER_BLUE = "#5e8dfa";

/* Interpolate between AI blue and pink. Old blue start: hsl(230,80%,75%). */
function getSliderColor(ratio) {
  const pinkShare = Math.round(Math.min(Math.max(ratio, 0), 100));
  return `color-mix(in srgb, ${SLIDER_BLUE} ${100 - pinkShare}%, var(--pink) ${pinkShare}%)`;
}

function LikesDeslikes({
  initialLikes,
  initialDislikes,
  initialLikesList = [],
  initialDislikesList = [],
  initialClicked = null,
  proposalId,
  setErrorMsg = () => {},
}) {
  const [clicked, setClicked] = useState(initialClicked);
  const [likes, setLikes] = useState(initialLikes);
  const [dislikes, setDislikes] = useState(initialDislikes);
  const [likesList, setLikesList] = useState(initialLikesList);
  const [dislikesList, setDislikesList] = useState(initialDislikesList);
  const [showInfo, setShowInfo] = useState(false);
  const containerRef = useRef(null);
  const { userData, isAuthenticated } = useUser();
  const backendUrl = userData?.activeBackend || API_BASE_URL;
  const voterType = userData?.species?.trim() || "human";

  useEffect(() => {
    setLikes(Number(initialLikes) || 0);
    setDislikes(Number(initialDislikes) || 0);
    setLikesList(initialLikesList || []);
    setDislikesList(initialDislikesList || []);
    setClicked(initialClicked);
  }, [initialLikes, initialDislikes, initialLikesList, initialDislikesList, initialClicked]);

  useEffect(() => {
    const postCard = containerRef.current?.closest?.("[data-proposal-card]");
    if (postCard) postCard.dataset.proposalUserVote = clicked || "";
  }, [clicked]);

  useEffect(() => {
    const handleProfileUpdate = (event) => {
      const detail = event.detail || {};
      if (!detail.username) return;
      const aliases = [detail.previousUsername, detail.oldUsername]
        .filter(Boolean)
        .map((value) => String(value).toLowerCase());
      if (!aliases.length) return;
      const renameVote = (vote) =>
        aliases.includes(String(vote?.voter || "").toLowerCase())
          ? { ...vote, voter: detail.username }
          : vote;
      setLikesList((items) => items.map(renameVote));
      setDislikesList((items) => items.map(renameVote));
    };
    window.addEventListener("supernova:profile-avatar-updated", handleProfileUpdate);
    return () => window.removeEventListener("supernova:profile-avatar-updated", handleProfileUpdate);
  }, []);

  const weighted = useMemo(() => {
    return buildWeightedVoteSummary(likesList, dislikesList);
  }, [likesList, dislikesList]);

  const pct = Math.max(weighted.supportPercent || 0, 0);
  const approvalRatio = Math.round(pct);
  const knobColor = getSliderColor(pct);
  const voteModal =
    showInfo && typeof document !== "undefined"
      ? createPortal(
          <div className="vote-modal-backdrop" onClick={() => setShowInfo(false)}>
            <div data-vote-modal className="vote-modal-card" onClick={(e) => e.stopPropagation()}>
              <LikesInfo
                proposalId={proposalId}
                likesData={likesList}
                dislikesData={dislikesList}
              />
            </div>
          </div>,
          document.body
        )
      : null;

  /* Close popup on outside click */
  useEffect(() => {
    if (!showInfo) return undefined;
    const handleOutsideClick = (e) => {
      if (e.target.closest("[data-vote-modal]")) return;
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setShowInfo(false);
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [showInfo]);

  async function getApiError(response, fallback) {
    try {
      const payload = await response.json();
      return formatBackendAuthErrorMessage(payload?.detail || payload?.message, fallback);
    } catch {
      try { return formatBackendAuthErrorMessage(await response.text(), fallback); } catch { return fallback; }
    }
  }

  const validateProfile = () => {
    if (!isAuthenticated) {
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("supernova:open-account", { detail: { mode: "create" } }));
      }
      return false;
    }
    try {
      requireBackendAuthSession();
    } catch {
      setErrorMsg([BACKEND_AUTH_MISSING_MESSAGE]);
      return false;
    }
    const errors = [];
    if (!backendUrl) errors.push("API base URL is not configured.");
    if (isAuthenticated && !userData?.name) errors.push("Add a display name in your profile before voting.");
    if (errors.length > 0) {
      setErrorMsg(errors);
      return false;
    }
    return true;
  };

  async function sendVote(choice) {
    try {
      const response = await fetch(`${backendUrl}/votes`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ proposal_id: proposalId, username: userData.name, choice, voter_type: voterType }),
      });
      if (!response.ok) { setErrorMsg([await getApiError(response, `Vote failed: ${response.status}`)]); return false; }
      return true;
    } catch (err) { setErrorMsg([formatBackendAuthErrorMessage(err, "Vote failed.")]); return false; }
  }

  async function removeVote() {
    try {
      const params = new URLSearchParams({
        proposal_id: String(proposalId),
        username: userData.name,
      });
      const response = await fetch(`${backendUrl}/votes?${params.toString()}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      if (!response.ok) { setErrorMsg([await getApiError(response, `Remove failed: ${response.status}`)]); return false; }
      return true;
    } catch (err) { setErrorMsg([formatBackendAuthErrorMessage(err, "Remove failed.")]); return false; }
  }

  const handleLikeClick = async ({ allowToggle = true } = {}) => {
    if (!validateProfile()) return;
    if (clicked === "like") {
      if (!allowToggle) return;
      if (await removeVote()) {
        setLikes((v) => Math.max(0, v - 1));
        setLikesList((v) => v.filter((vote) => vote.voter !== userData.name));
        setClicked(null);
      }
      return;
    }
    if (clicked === "dislike") {
      if (!(await removeVote())) return;
      setDislikes((v) => Math.max(0, v - 1));
      setDislikesList((v) => v.filter((vote) => vote.voter !== userData.name));
    }
    if (await sendVote("up")) {
      setLikes((v) => v + 1);
      setLikesList((v) => [...v, { voter: userData.name, type: voterType }]);
      setClicked("like");
    }
  };

  const handleDislikeClick = async ({ allowToggle = true } = {}) => {
    if (!validateProfile()) return;
    if (clicked === "dislike") {
      if (!allowToggle) return;
      if (await removeVote()) {
        setDislikes((v) => Math.max(0, v - 1));
        setDislikesList((v) => v.filter((vote) => vote.voter !== userData.name));
        setClicked(null);
      }
      return;
    }
    if (clicked === "like") {
      if (!(await removeVote())) return;
      setLikes((v) => Math.max(0, v - 1));
      setLikesList((v) => v.filter((vote) => vote.voter !== userData.name));
    }
    if (await sendVote("down")) {
      setDislikes((v) => v + 1);
      setDislikesList((v) => [...v, { voter: userData.name, type: voterType }]);
      setClicked("dislike");
    }
  };

  useEffect(() => {
    const handleCursorAction = (event) => {
      const detail = event.detail || {};
      if (String(detail.id) !== String(proposalId)) return;
      const allowToggle =
        typeof detail.allowToggle === "boolean"
          ? detail.allowToggle
          : detail.source !== "ai-widget";
      if (detail.action === "like") {
        handleLikeClick({ allowToggle });
      }
      if (detail.action === "dislike") {
        handleDislikeClick({ allowToggle });
      }
      if (detail.action === "vote-recorded") {
        const voter = detail.voter || detail.username || "AI delegate";
        const type = detail.voter_type || detail.type || "ai";
        const nextVote = detail.vote === "up" || detail.vote === "support" ? "like" : detail.vote === "down" || detail.vote === "oppose" ? "dislike" : "";
        if (!nextVote || !voter) return;
        setLikesList((items) => {
          const filtered = items.filter((vote) => String(vote?.voter || "").toLowerCase() !== String(voter).toLowerCase());
          const next = nextVote === "like" ? [...filtered, { voter, type }] : filtered;
          setLikes(next.length);
          return next;
        });
        setDislikesList((items) => {
          const filtered = items.filter((vote) => String(vote?.voter || "").toLowerCase() !== String(voter).toLowerCase());
          const next = nextVote === "dislike" ? [...filtered, { voter, type }] : filtered;
          setDislikes(next.length);
          return next;
        });
      }
    };

    window.addEventListener("supernova:post-action", handleCursorAction);
    return () => window.removeEventListener("supernova:post-action", handleCursorAction);
  }, [proposalId, handleLikeClick, handleDislikeClick]);

  return (
    <>
    <div ref={containerRef} className="relative flex items-center gap-2">
      {/* DOWN - left */}
      <button
        type="button"
        onClick={handleDislikeClick}
        aria-label="Vote no"
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-all ${
          clicked === "dislike"
            ? "bg-[var(--blue)] text-white shadow-[var(--shadow-blue)] scale-110"
            : "text-[var(--text-gray-light)] hover:bg-[rgba(255,255,255,0.07)]"
        }`}
      >
        <BiSolidDislike className="text-[0.9rem]" />
      </button>

      {/* Slider */}
      <div className="relative flex min-w-[4.5rem] flex-1 items-center py-1">
        <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 text-[0.58rem] font-bold tabular-nums" style={{ color: knobColor }}>
          {approvalRatio}%
        </span>
        <div className="relative h-[3px] w-full rounded-full bg-[rgba(255,255,255,0.1)]">
          {/* Fill - solid color that matches the endpoint position */}
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${pct}%`,
              background: `linear-gradient(90deg, ${SLIDER_BLUE} 0%, ${knobColor} 100%)`,
            }}
          />
          {/* Knob - glowing dot */}
          <div
            className="absolute top-1/2 -translate-y-1/2 transition-all duration-500"
            style={{ left: `calc(${Math.min(pct, 100)}% - (${Math.min(pct, 100)} * 14px / 100))` }}
          >
            <div
              className="h-3.5 w-3.5 rounded-full border-2 border-[rgba(255,255,255,0.9)]"
              style={{
                background: knobColor,
                boxShadow:
                  "0 0 6px color-mix(in srgb, var(--pink) 55%, transparent), 0 0 14px color-mix(in srgb, var(--pink) 25%, transparent)",
              }}
            />
          </div>
        </div>
      </div>

      {/* UP - right */}
      <button
        type="button"
        onClick={handleLikeClick}
        aria-label="Vote yes"
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-all ${
          clicked === "like"
            ? "bg-[var(--pink)] text-white shadow-[var(--shadow-pink)] scale-110"
            : "text-[var(--text-gray-light)] hover:bg-[rgba(255,255,255,0.07)]"
        }`}
      >
        <BiSolidLike className="text-[0.9rem]" />
      </button>

      {/* Expand chevron */}
      <button
        type="button"
        onClick={() => setShowInfo((v) => !v)}
        aria-label={showInfo ? "Hide vote breakdown" : "Show vote breakdown"}
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[var(--text-gray-light)] hover:bg-[rgba(255,255,255,0.07)]"
      >
        <IoChevronUp className={`text-[0.8rem] transition-transform ${showInfo ? "rotate-180" : ""}`} />
      </button>

    </div>
    {voteModal}
    </>
  );
}

export default LikesDeslikes;
