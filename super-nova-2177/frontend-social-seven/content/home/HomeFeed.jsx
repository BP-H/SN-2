"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  IoBarChartOutline,
  IoDocumentTextOutline,
  IoImageOutline,
  IoSend,
  IoSparklesOutline,
  IoVideocamOutline,
  IoStarOutline,
} from "react-icons/io5";
import { BiSolidLike, BiSolidDislike } from "react-icons/bi";
import { API_BASE_URL, absoluteApiUrl } from "@/utils/apiBase";
import { authHeaders, formatBackendAuthErrorMessage } from "@/utils/authSession";
import { avatarDisplayUrl } from "@/utils/avatar";
import { speciesAvatarStyle } from "@/utils/species";
import { useUser } from "@/content/profile/UserContext";
import { buildWeightedVoteSummary } from "@/utils/voteWeights";
import CreatePost from "../create post/CreatePost";
import InputFields from "../create post/InputFields";
import ProposalCard from "../proposal/content/ProposalCard";
import LikesInfo from "../proposal/content/LikesInfo";
import CardLoading from "../CardLoading";

function formatRelativeTime(dateString) {
  if (!dateString) return "now";
  const now = new Date();
  const raw = String(dateString);
  const date = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(raw) ? raw : `${raw}Z`);
  if (Number.isNaN(date.getTime())) return "now";
  const diffMs = now.getTime() - date.getTime();
  if (diffMs < 0) return "now";
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHours = Math.floor(diffMin / 60);
  const diffDays = Math.floor(diffHours / 24);
  if (diffSec >= 10 && diffSec < 60) return `${diffSec}s`;
  if (diffDays > 0) return `${diffDays}d`;
  if (diffHours > 0) return `${diffHours}h`;
  if (diffMin > 0) return `${diffMin}m`;
  return "now";
}

// Backend can override these via /system-vote so live deployments avoid stale UI.
const SYSTEM_VOTE_CONFIG = {
  question: "Should SuperNova prioritize AI rights as the next major research focus?",
  deadline: "2026-04-27T18:00:00-07:00",
};
const FEED_PAGE_SIZE = 30;
const HOME_SCROLL_TOP_KEY = "supernova-home-scroll-top";

function normalizeAuthorName(name = "") {
  return String(name || "").trim().toLowerCase();
}

function postAgeHours(timeValue) {
  if (!timeValue) return 0;
  const raw = String(timeValue);
  const date = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(raw) ? raw : `${raw}Z`);
  if (Number.isNaN(date.getTime())) return 0;
  return Math.max(0, (Date.now() - date.getTime()) / 36e5);
}

function homeRankScore(post, priorityAuthors) {
  const authorKey = normalizeAuthorName(post?.userName);
  const followedOrSelf = priorityAuthors.has(authorKey);
  const likes = Array.isArray(post?.likes) ? post.likes.length : 0;
  const dislikes = Array.isArray(post?.dislikes) ? post.dislikes.length : 0;
  const comments = Array.isArray(post?.comments) ? post.comments.length : 0;
  const totalVotes = likes + dislikes;
  const ageHours = postAgeHours(post?.time);
  const freshness = 1 / (1 + ageHours / 18);
  const engagement = Math.log1p(totalVotes * 1.5 + comments * 2.6) * 8;
  const supportBalance = totalVotes ? ((likes - dislikes) / totalVotes) * 8 : 0;
  const followBoost = followedOrSelf ? 18 * Math.sqrt(freshness) : 0;

  return freshness * 46 + engagement + supportBalance + followBoost;
}

function formatCountdown(deadlineString, nowMs) {
  const deadline = new Date(deadlineString);
  if (Number.isNaN(deadline.getTime())) return "Set deadline";
  const remaining = deadline.getTime() - nowMs;
  if (remaining <= 0) return "Ended";
  const totalMinutes = Math.ceil(remaining / 60000);
  const days = Math.floor(totalMinutes / 1440);
  const hours = Math.floor((totalMinutes % 1440) / 60);
  const minutes = totalMinutes % 60;
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

export default function HomeFeed({ setErrorMsg, setNotify, activeBE }) {
  const [discard, setDiscard] = useState(true);
  const [pendingMediaPicker, setPendingMediaPicker] = useState("");
  const [pendingAiOpen, setPendingAiOpen] = useState(false);
  const [systemNow, setSystemNow] = useState(() => Date.now());

  // Auto-open composer if navigated from a global '+' button click
  useEffect(() => {
    if (typeof window !== "undefined" && sessionStorage.getItem("autoOpenComposer") === "true") {
      sessionStorage.removeItem("autoOpenComposer");
      setDiscard(false);
      setTimeout(() => window.scrollTo({ top: 0, behavior: "smooth" }), 100);
    }
  }, []);
  const [showSystemVoteInfo, setShowSystemVoteInfo] = useState(false);
  const [systemVoteClicked, setSystemVoteClicked] = useState(null);
  const { userData, defaultAvatar, isAuthenticated } = useUser();
  const queryClient = useQueryClient();
  const backendUrl = userData?.activeBackend || API_BASE_URL;
  const voterType = userData?.species?.trim() || "human";
  const userAvatar = isAuthenticated ? avatarDisplayUrl(userData?.avatar, defaultAvatar) : defaultAvatar;
  const userAvatarStyle = speciesAvatarStyle(voterType);

  useEffect(() => {
    if (typeof window === "undefined") return;
    sessionStorage.removeItem(HOME_SCROLL_TOP_KEY);
    window.dispatchEvent(new Event("supernova:show-header"));
    window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "auto" }));
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setSystemNow(Date.now()), 30000);
    return () => window.clearInterval(timer);
  }, []);

  const requireAccount = (message) => {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("supernova:open-account", { detail: { mode: "create", reason: message } }));
    }
  };

  const openComposerWithMedia = (type) => {
    if (!isAuthenticated) {
      requireAccount("Sign in to attach media and post on SuperNova.");
      return;
    }
    setPendingMediaPicker(type);
    setDiscard(false);
  };

  const openComposerWithAi = () => {
    if (!isAuthenticated) {
      requireAccount("Sign in to create AI delegate posts on SuperNova.");
      return;
    }
    setPendingAiOpen(true);
    setDiscard(false);
  };

  const {
    data: postsData,
    isLoading,
    isError,
    error,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ["home-feed", activeBE],
    queryFn: async ({ pageParam = null }) => {
      const cursor = pageParam ? `&before_id=${encodeURIComponent(pageParam)}` : "";
      const response = await fetch(`${API_BASE_URL}/proposals?filter=latest&limit=${FEED_PAGE_SIZE}${cursor}`);
      if (!response.ok) throw new Error("Failed to fetch posts");
      return response.json();
    },
    initialPageParam: null,
    getNextPageParam: (lastPage) => {
      if (!Array.isArray(lastPage) || lastPage.length < FEED_PAGE_SIZE) return undefined;
      return lastPage[lastPage.length - 1]?.id || undefined;
    },
  });
  const posts = useMemo(() => postsData?.pages?.flat() || [], [postsData]);

  const { data: followsData } = useQuery({
    queryKey: ["home-following", userData?.name || ""],
    enabled: Boolean(isAuthenticated && userData?.name),
    queryFn: async () => {
      const response = await fetch(`${API_BASE_URL}/follows?user=${encodeURIComponent(userData.name)}`, {
        headers: authHeaders(),
      });
      if (!response.ok) throw new Error("Failed to load follows");
      return response.json();
    },
    staleTime: 30_000,
  });

  const priorityAuthors = useMemo(() => {
    const names = new Set();
    if (userData?.name) names.add(normalizeAuthorName(userData.name));
    (followsData?.following || []).forEach((item) => {
      const username = normalizeAuthorName(item?.username);
      if (username) names.add(username);
    });
    return names;
  }, [followsData, userData?.name]);

  const orderedPosts = useMemo(() => {
    return posts
      .map((post, index) => ({
        post,
        index,
        score: homeRankScore(post, priorityAuthors),
      }))
      .sort((a, b) => b.score - a.score || a.index - b.index)
      .map((entry) => entry.post);
  }, [posts, priorityAuthors]);

  const { data: systemVoteData } = useQuery({
    queryKey: ["system-vote", backendUrl, userData?.name || ""],
    queryFn: async () => {
      const query = userData?.name ? `?username=${encodeURIComponent(userData.name)}` : "";
      const response = await fetch(`${backendUrl}/system-vote${query}`);
      if (!response.ok) throw new Error("Failed to fetch system vote");
      return response.json();
    },
    keepPreviousData: true,
  });

  /* Dedicated yes/no system vote; backend config wins, local constant is only a safe fallback. */
  const systemVote = useMemo(() => {
    const likes = systemVoteData?.likes || [];
    const dislikes = systemVoteData?.dislikes || [];
    const weighted = buildWeightedVoteSummary(likes, dislikes);
    const userVote = systemVoteData?.user_vote || null;
    const question = systemVoteData?.question || SYSTEM_VOTE_CONFIG.question;
    const deadline = systemVoteData?.deadline || SYSTEM_VOTE_CONFIG.deadline;

    return {
      question,
      yesRatio: Math.round(weighted.supportPercent || 0),
      weighted,
      likes,
      dislikes,
      endsIn: formatCountdown(deadline, systemNow),
      userVote,
    };
  }, [systemNow, systemVoteData]);

  /* Sync system vote clicked state from data */
  useEffect(() => {
    setSystemVoteClicked(systemVote.userVote);
  }, [systemVote.userVote]);

  /* System vote handler — casts an independent system-level vote */
  const handleSystemVote = async (choice) => {
    if (!isAuthenticated) {
      requireAccount("Sign in to cast a system vote.");
      return;
    }
    if (!userData?.name) {
      setErrorMsg(["Add a display name in your profile before voting."]);
      return;
    }

    const isToggle = systemVoteClicked === choice;

    try {
      if (isToggle) {
        const response = await fetch(`${backendUrl}/system-vote?username=${encodeURIComponent(userData.name)}`, {
          method: "DELETE",
          headers: authHeaders(),
        });
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(formatBackendAuthErrorMessage(payload?.detail, "Unable to remove system vote."));
        }
        setSystemVoteClicked(null);
      } else {
        const voteChoice = choice === "like" ? "yes" : "no";
        const response = await fetch(`${backendUrl}/system-vote`, {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            username: userData.name,
            choice: voteChoice,
            voter_type: voterType,
          }),
        });
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(formatBackendAuthErrorMessage(payload?.detail, "Unable to cast system vote."));
        }
        setSystemVoteClicked(choice);
      }

      // Refetch to update all data
      queryClient.invalidateQueries({ queryKey: ["system-vote"] });
      queryClient.invalidateQueries({ queryKey: ["home-feed"] });
      queryClient.invalidateQueries({ queryKey: ["proposals"] });
    } catch (err) {
      setErrorMsg([formatBackendAuthErrorMessage(err, "System vote failed.")]);
    }
  };

  /* Close system vote overlay on outside click */
  useEffect(() => {
    if (!showSystemVoteInfo) return undefined;
    const close = (e) => {
      if (!e.target.closest("[data-system-vote-overlay]")) setShowSystemVoteInfo(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [showSystemVoteInfo]);

  const pct = Math.max(systemVote.weighted.supportPercent || 0, 0);
  const voteAccentColor = "var(--pink)";
  const systemVoteModal =
    showSystemVoteInfo && typeof document !== "undefined"
      ? createPortal(
          <div className="vote-modal-backdrop" onClick={() => setShowSystemVoteInfo(false)}>
            <div
              data-system-vote-overlay
              className="vote-modal-card"
              onClick={(e) => e.stopPropagation()}
            >
              <LikesInfo likesData={systemVote.likes} dislikesData={systemVote.dislikes} />
            </div>
          </div>,
          document.body
        )
      : null;

  return (
    <div className="social-shell px-0 pb-5">
      <CreatePost discard={discard} setDiscard={setDiscard} />

      <div className="space-y-2.5">
        {/* ── System Vote ── */}
        <section className="mobile-feed-panel social-panel rounded-[1.35rem] px-4 py-4">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <IoStarOutline className="text-[1rem] text-[var(--pink)]" />
              <span className="text-[0.72rem] font-bold uppercase tracking-[0.18em] text-[var(--pink)]">
                System Decision
              </span>
            </div>
            <span className="text-[0.72rem] text-[var(--text-gray-light)]">
              {systemVote.endsIn === "Ended" ? "Vote ended" : `Ends in ${systemVote.endsIn}`}
            </span>
          </div>
          <p className="mb-4 text-[0.92rem] font-medium text-[var(--text-black)]">
            {systemVote.question}
          </p>

          {/* System vote controls — same style as post action bar */}
          <div className="flex items-center gap-2 rounded-full bg-[rgba(255,255,255,0.04)] px-2.5 py-1.5">
            {/* 👎 NO — left */}
            <button
              type="button"
              onClick={() => handleSystemVote("dislike")}
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-all ${
                systemVoteClicked === "dislike"
                  ? "bg-[var(--blue)] text-white shadow-[var(--shadow-blue)] scale-110"
                  : "bg-[rgba(255,255,255,0.08)] text-[var(--text-gray-light)] hover:bg-[rgba(255,255,255,0.14)]"
              }`}
            >
              <BiSolidDislike className="text-[1rem]" />
            </button>

            {/* Slider */}
            <div className="relative flex-1 py-1">
              <span
                className="absolute -top-2.5 left-1/2 -translate-x-1/2 text-[0.6rem] font-bold tabular-nums"
                style={{ color: voteAccentColor }}
              >
                {systemVote.yesRatio}% yes
              </span>
              <div className="relative h-1 rounded-full bg-[rgba(255,255,255,0.09)]">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${pct}%`,
                    background: voteAccentColor,
                  }}
                />
                <div
                  className="absolute top-1/2 -translate-y-1/2 transition-all duration-500"
                  style={{ left: `calc(${Math.min(pct, 100)}% - (${Math.min(pct, 100)} * 14px / 100))` }}
                >
                  <div
                    className="h-3.5 w-3.5 rounded-full border-2 border-[rgba(255,255,255,0.9)]"
                    style={{
                      background: voteAccentColor,
                      boxShadow: "0 0 6px rgba(255, 79, 143, 0.38), 0 0 14px rgba(255, 79, 143, 0.18)",
                    }}
                  />
                </div>
              </div>
            </div>

            {/* 👍 YES — right */}
            <button
              type="button"
              onClick={() => handleSystemVote("like")}
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-all ${
                systemVoteClicked === "like"
                  ? "bg-[var(--pink)] text-white shadow-[var(--shadow-pink)] scale-110"
                  : "bg-[rgba(255,255,255,0.08)] text-[var(--text-gray-light)] hover:bg-[rgba(255,255,255,0.14)]"
              }`}
            >
              <BiSolidLike className="text-[1rem]" />
            </button>

            {/* Breakdown */}
            <button
              type="button"
              onClick={() => setShowSystemVoteInfo((v) => !v)}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[rgba(255,255,255,0.08)] text-[var(--text-gray-light)] hover:bg-[rgba(255,255,255,0.14)]"
              aria-label="Show species vote breakdown"
            >
              <IoBarChartOutline className="text-[0.92rem]" />
            </button>
          </div>

        </section>
        {systemVoteModal}

        {/* ── Create Post ── */}
        <section className="mobile-feed-panel social-panel overflow-hidden rounded-[1.35rem] px-4 py-4 transition-all duration-300 ease-out">
          {discard ? (
            <div className="flex items-center gap-2.5">
              {userAvatar ? (
                <img
                  src={userAvatar}
                  alt="profile"
                  onError={(event) => {
                    event.currentTarget.src = defaultAvatar;
                  }}
                  className="h-9 w-9 shrink-0 rounded-full border object-cover"
                  style={userAvatarStyle}
                />
              ) : (
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border bgGray text-[0.72rem] font-semibold" style={userAvatarStyle}>
                  {(userData?.name || "SN").slice(0, 2).toUpperCase()}
                </div>
              )}
              <button
                type="button"
                onClick={() => {
                  if (!isAuthenticated) {
                    requireAccount("Sign in to post on SuperNova.");
                    return;
                  }
                  setDiscard(false);
                }}
                className="min-w-0 flex-1 rounded-full border border-[var(--horizontal-line)] bg-[rgba(255,255,255,0.03)] px-3.5 py-2.5 text-left text-[0.88rem] text-[var(--text-gray-light)]"
              >
                Share your thoughts...
              </button>

              <div className="flex shrink-0 items-center gap-1.5 text-[var(--text-gray-light)]">
                <button type="button" onClick={() => openComposerWithMedia("image")} className="composer-icon-button flex h-9 w-9 items-center justify-center rounded-full" aria-label="Add media">
                  <IoImageOutline className="text-[1rem]" />
                </button>
                <button type="button" onClick={() => openComposerWithMedia("video")} className="composer-icon-button flex h-9 w-9 items-center justify-center rounded-full" aria-label="Add video">
                  <IoVideocamOutline className="text-[1rem]" />
                </button>
                <button type="button" onClick={() => openComposerWithMedia("file")} className="composer-icon-button flex h-9 w-9 items-center justify-center rounded-full" aria-label="Add document">
                  <IoDocumentTextOutline className="text-[1rem]" />
                </button>
                <button type="button" onClick={openComposerWithAi} className="composer-icon-button flex h-9 w-9 items-center justify-center rounded-full text-[var(--pink)]" aria-label="AI post" title="AI post">
                  <IoSparklesOutline className="text-[1rem]" />
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (!isAuthenticated) {
                      requireAccount("Sign in to post on SuperNova.");
                      return;
                    }
                    setDiscard(false);
                  }}
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--pink)] text-white shadow-[var(--shadow-pink)]"
                  aria-label="Post"
                  title="Post"
                >
                  <IoSend className="text-[1rem]" />
                </button>
              </div>
            </div>
          ) : (
            <InputFields
              embedded
              autoFocus
              setDiscard={setDiscard}
              setNotify={setNotify}
              autoOpenMediaType={pendingMediaPicker}
              onAutoOpenConsumed={() => setPendingMediaPicker("")}
              autoOpenAi={pendingAiOpen}
              onAutoOpenAiConsumed={() => setPendingAiOpen(false)}
              refetchPosts={refetch}
            />
          )}
        </section>

        {/* ── Feed ── */}
        <div className="space-y-2.5">
          {isLoading ? (
            Array.from({ length: 3 }).map((_, index) => <CardLoading key={index} />)
          ) : isError ? (
            <div className="mobile-feed-panel social-panel rounded-[1rem] px-5 py-8 text-center text-[0.86rem] text-[var(--text-gray-light)]">
              <p className="font-semibold text-[var(--text-black)]">Could not load the feed.</p>
              <p className="mt-1">{error?.message || "The backend did not return posts."}</p>
              <button
                type="button"
                onClick={() => refetch()}
                className="mt-4 rounded-full bg-[var(--pink)] px-4 py-2 text-[0.78rem] font-bold text-white shadow-[var(--shadow-pink)]"
              >
                Retry
              </button>
            </div>
          ) : orderedPosts.length === 0 ? (
            <div className="mobile-feed-panel social-panel rounded-[1rem] px-5 py-8 text-center text-[0.86rem] text-[var(--text-gray-light)]">
              No posts yet.
            </div>
          ) : (
            <>
              {orderedPosts.map((post) => (
                <ProposalCard
                  key={post.id}
                  id={post.id}
                  userName={post.userName}
                  userInitials={post.userInitials}
                  time={formatRelativeTime(post.time)}
                  title={post.title}
                  logo={post.author_img}
                  media={{
                    image: post.media?.image ? absoluteApiUrl(post.media.image) : post.image ? absoluteApiUrl(post.image) : "",
                    images: Array.isArray(post.media?.images)
                      ? post.media.images.map((image) => absoluteApiUrl(image))
                      : [],
                    layout: post.media?.layout || "carousel",
                    governance: post.media?.governance || null,
                    video: post.media?.video || post.video || "",
                    link: post.media?.link || post.link || "",
                    file: post.media?.file ? absoluteApiUrl(post.media.file) : post.file ? absoluteApiUrl(post.file) : "",
                  }}
                  text={post.text}
                  comments={post.comments}
                  collabs={post.collabs}
                  likes={post.likes}
                  dislikes={post.dislikes}
                  profileUrl={post.profile_url}
                  domainAsProfile={post.domain_as_profile}
                  setErrorMsg={setErrorMsg}
                  setNotify={setNotify}
                  specie={post.author_type}
                />
              ))}
              {hasNextPage && (
                <button
                  type="button"
                  onClick={() => fetchNextPage()}
                  disabled={isFetchingNextPage}
                  className="mobile-feed-panel social-panel mx-[0.35rem] rounded-[1rem] px-5 py-3 text-center text-[0.86rem] font-bold text-[var(--text-black)] disabled:opacity-60"
                >
                  {isFetchingNextPage ? "Loading..." : "Load more"}
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
