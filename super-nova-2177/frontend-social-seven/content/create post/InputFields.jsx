"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import imageCompression from "browser-image-compression";
import { FaFileAlt } from "react-icons/fa";
import {
  IoAlbumsOutline,
  IoBarChartOutline,
  IoChevronBack,
  IoChevronForward,
  IoClose,
  IoDocumentTextOutline,
  IoGridOutline,
  IoImageOutline,
  IoPersonAddOutline,
  IoSend,
  IoShieldCheckmarkOutline,
  IoSparklesOutline,
  IoTimeOutline,
  IoVideocamOutline,
} from "react-icons/io5";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import LiquidGlass from "../liquid glass/LiquidGlass";
import { useUser } from "../profile/UserContext";
import ErrorMessage from "../Error";
import MediaInput from "./Media";
import PdfPager from "../proposal/content/PdfPager";
import AiDelegateActionModal from "../proposal/content/AiDelegateActionModal";
import { API_BASE_URL, absoluteApiUrl } from "@/utils/apiBase";
import {
  BACKEND_AUTH_MISSING_MESSAGE,
  authHeaders,
  formatBackendAuthErrorMessage,
  requireBackendAuthSession,
} from "@/utils/authSession";
import { avatarDisplayUrl, normalizeAvatarValue } from "@/utils/avatar";
import { MentionAutocomplete, useMentionAutocomplete } from "@/utils/mentionAutocomplete";
import { speciesAccentColor, speciesAvatarStyle } from "@/utils/species";

function InputFields({
  setDiscard,
  setPosts,
  refetchPosts,
  setNotify = () => {},
  embedded = false,
  autoFocus = false,
  autoOpenMediaType = "",
  onAutoOpenConsumed,
  autoOpenAi = false,
  onAutoOpenAiConsumed,
}) {
  const { userData, defaultAvatar, isAuthenticated } = useUser();
  const queryClient = useQueryClient();

  const [text, setText] = useState("");
  const [errorMsg, setErrorMsg] = useState([]);
  const [mediaType, setMediaType] = useState("");
  const [mediaValue, setMediaValue] = useState("");
  const [mediaLayout, setMediaLayout] = useState("carousel");
  const [proposalMode, setProposalMode] = useState("post");
  const [decisionLevel, setDecisionLevel] = useState("standard");
  const [votingDays, setVotingDays] = useState(3);
  const [previewIndex, setPreviewIndex] = useState(0);
  const [selectedFile, setSelectedFile] = useState(null);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [collabPromptUser, setCollabPromptUser] = useState(null);
  const [pendingCollabInvitees, setPendingCollabInvitees] = useState([]);
  const [collabNotice, setCollabNotice] = useState("");
  const [aiComposerOpen, setAiComposerOpen] = useState(false);
  const textAreaRef = useRef(null);
  const imageInputRef = useRef(null);
  const videoInputRef = useRef(null);
  const fileInputRef = useRef(null);
  const previewSwipeRef = useRef({ active: false, x: 0, y: 0, moved: false });
  const imagePreviewUrls = useMemo(() => {
    if (mediaType !== "image") return [];
    return selectedFiles.map((file) => URL.createObjectURL(file));
  }, [mediaType, selectedFiles]);
  const selectedFilePreviewUrl = useMemo(() => {
    if (!selectedFile || mediaType === "image" || typeof URL === "undefined") return "";
    return URL.createObjectURL(selectedFile);
  }, [mediaType, selectedFile]);
  const selectedFileIsPdf =
    mediaType === "file" &&
    Boolean(selectedFile) &&
    (selectedFile.type === "application/pdf" || /\.pdf$/i.test(selectedFile.name || ""));
  const userAvatar = isAuthenticated ? avatarDisplayUrl(userData?.avatar, defaultAvatar) : defaultAvatar;
  const userAvatarStyle = speciesAvatarStyle(userData?.species || "human");
  const isDecisionMode = proposalMode === "decision";
  const decisionThresholdLabel = decisionLevel === "important" ? "90%" : "60%";
  const normalizeComposerCollabUser = useCallback((user) => {
    const username = String(user?.username || "").trim();
    if (!username) return null;
    const rawAvatar = user?.avatar || user?.avatar_url || user?.profile_pic || user?.profilePic || user?.author_img || "";
    return {
      username,
      key: username.toLowerCase(),
      species: String(user?.species || "human").trim() || "human",
      avatar: avatarDisplayUrl(rawAvatar, ""),
      initials: String(user?.initials || username || "SN").slice(0, 2).toUpperCase(),
      canCollab: user?.can_collab ?? user?.canCollab ?? true,
    };
  }, []);
  const handleMentionUserSelected = useCallback(
    (user) => {
      const selected = normalizeComposerCollabUser(user);
      if (!selected) return;
      if (selected.canCollab === false) {
        setCollabPromptUser(null);
        setCollabNotice(`@${selected.username} can be mentioned, but cannot receive collab invites yet.`);
        return;
      }
      if (userData?.name && selected.key === userData.name.toLowerCase()) {
        setCollabPromptUser(null);
        setCollabNotice("You cannot invite yourself as a collaborator.");
        return;
      }
      if (pendingCollabInvitees.some((invitee) => invitee.key === selected.key)) {
        setCollabPromptUser(null);
        setCollabNotice(`@${selected.username} is already in your collab invites.`);
        return;
      }
      setCollabNotice("");
      setCollabPromptUser(selected);
    },
    [normalizeComposerCollabUser, pendingCollabInvitees, userData?.name]
  );
  const mentionAutocomplete = useMentionAutocomplete({
    value: text,
    setValue: setText,
    inputRef: textAreaRef,
    onSelectUser: handleMentionUserSelected,
  });

  const requireAccount = (message) => {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("supernova:open-account", { detail: { mode: "create", reason: message } }));
    }
  };

  useEffect(() => {
    return () => {
      imagePreviewUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [imagePreviewUrls]);

  useEffect(() => {
    return () => {
      if (selectedFilePreviewUrl) URL.revokeObjectURL(selectedFilePreviewUrl);
    };
  }, [selectedFilePreviewUrl]);

  useEffect(() => {
    if (autoFocus && textAreaRef.current) {
      textAreaRef.current.focus();
    }
  }, [autoFocus]);

  useEffect(() => {
    const textarea = textAreaRef.current;
    if (!textarea) return;
    const viewportMax =
      typeof window !== "undefined"
        ? Math.max(220, Math.min(window.innerHeight * 0.72, 980))
        : 720;
    textarea.style.height = "auto";
    const nextHeight = Math.min(Math.max(textarea.scrollHeight, 118), viewportMax);
    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > viewportMax ? "auto" : "hidden";
  }, [text]);

  useEffect(() => {
    if (!autoOpenMediaType) return;
    const inputMap = {
      image: imageInputRef,
      video: videoInputRef,
      file: fileInputRef,
    };
    const now = Date.now();
    const lastPickerOpen = window.__supernovaLastMediaPickerOpen || 0;
    onAutoOpenConsumed?.();
    if (now - lastPickerOpen < 900) return;
    window.__supernovaLastMediaPickerOpen = now;
    window.setTimeout(() => {
      inputMap[autoOpenMediaType]?.current?.click();
    }, 80);
  }, [autoOpenMediaType, onAutoOpenConsumed]);

  useEffect(() => {
    if (!autoOpenAi) return;
    setAiComposerOpen(true);
    onAutoOpenAiConsumed?.();
  }, [autoOpenAi, onAutoOpenAiConsumed]);

  useEffect(() => {
    setPreviewIndex(0);
  }, [selectedFiles.length, mediaLayout]);

  /* Auto-detect URLs in text and set as link media */
  useEffect(() => {
    if (mediaType && mediaType !== "link") return; // don't override image/video/file
    const urlRegex = /(https?:\/\/[^\s]+)/gi;
    const urls = text.match(urlRegex);
    if (urls && urls.length > 0) {
      const firstUrl = urls[0];
      if (!mediaValue || mediaType === "link") {
        setMediaType("link");
        setMediaValue(firstUrl);
      }
    } else if (mediaType === "link") {
      // Clear auto-detected link if URL was removed from text
      setMediaType("");
      setMediaValue("");
    }
  }, [text, mediaType, mediaValue]);

  const handleRemoveMedia = () => {
    setMediaType("");
    setMediaValue("");
    setMediaLayout("carousel");
    setPreviewIndex(0);
    setSelectedFile(null);
    setSelectedFiles([]);
  };

  const ensureNamedFile = (file, originalFile, index = 0) => {
    if (file instanceof File && file.name) return file;
    const originalName = originalFile?.name || "";
    const originalExt = originalName.includes(".") ? originalName.slice(originalName.lastIndexOf(".")) : "";
    const fallbackExt =
      originalExt ||
      (file?.type === "image/png" ? ".png" : file?.type === "image/webp" ? ".webp" : ".jpg");
    return new File([file], originalName || `image-${index + 1}${fallbackExt}`, {
      type: file?.type || originalFile?.type || "image/jpeg",
      lastModified: originalFile?.lastModified || Date.now(),
    });
  };

  const handleFileChange = async (event, type) => {
    if (!isAuthenticated) {
      requireAccount("Sign in before attaching media.");
      event.target.value = null;
      return;
    }

    const files = Array.from(event.target.files || []);
    if (files.length === 0) return;

    if (type === "image") {
      const imageFiles = files.filter((file) => file.type.startsWith("image/"));
      if (imageFiles.length === 0) {
        setErrorMsg(["Choose one or more image files."]);
        event.target.value = null;
        return;
      }
      try {
        const options = { maxSizeMB: 1, maxWidthOrHeight: 1024, useWebWorker: true };
        const compressedFiles = await Promise.all(
          imageFiles.map(async (file, index) => {
            const compressed = await imageCompression(file, options).catch(() => file);
            return ensureNamedFile(compressed, file, index);
          })
        );
        setSelectedFiles(compressedFiles);
        setSelectedFile(compressedFiles[0]);
        setMediaType("image");
        setMediaLayout(compressedFiles.length > 1 ? mediaLayout : "carousel");
        setMediaValue(
          compressedFiles.length > 1 ? `${compressedFiles.length} images selected` : compressedFiles[0].name
        );
      } catch {
        setSelectedFiles(imageFiles);
        setSelectedFile(imageFiles[0]);
        setMediaType("image");
        setMediaLayout(imageFiles.length > 1 ? mediaLayout : "carousel");
        setMediaValue(imageFiles.length > 1 ? `${imageFiles.length} images selected` : imageFiles[0].name);
      }
    } else if (type === "video" && files[0].type.startsWith("video/")) {
      const fileObj = files[0];
      setSelectedFile(fileObj);
      setSelectedFiles([]);
      setMediaType("video");
      setMediaValue(fileObj.name);
    } else if (type === "file") {
      const fileObj = files[0];
      setSelectedFile(fileObj);
      setSelectedFiles([]);
      setMediaType("file");
      setMediaValue(fileObj.name);
    } else {
      setErrorMsg([`Choose a valid ${type} file.`]);
    }

    event.target.value = null;
  };

  const getApiError = async (response, fallback) => {
    try {
      const payload = await response.json();
      return formatBackendAuthErrorMessage(payload?.detail || payload?.message, fallback);
    } catch {
      try {
        const textResponse = await response.text();
        return formatBackendAuthErrorMessage(textResponse, fallback);
      } catch {
        return fallback;
      }
    }
  };

  const addPendingCollabInvitee = (user) => {
    const selected = normalizeComposerCollabUser(user);
    if (!selected) return;
    if (userData?.name && selected.key === userData.name.toLowerCase()) {
      setCollabPromptUser(null);
      setCollabNotice("You cannot invite yourself as a collaborator.");
      return;
    }
    setPendingCollabInvitees((invitees) => {
      if (invitees.some((invitee) => invitee.key === selected.key)) return invitees;
      return [...invitees, selected];
    });
    setCollabPromptUser(null);
    setCollabNotice(`@${selected.username} added as a pending collab invite.`);
  };

  const removePendingCollabInvitee = (username) => {
    const key = String(username || "").toLowerCase();
    setPendingCollabInvitees((invitees) => invitees.filter((invitee) => invitee.key !== key));
    setCollabNotice("");
  };

  const requestComposerCollabs = async (proposalId, invitees = []) => {
    if (!proposalId || invitees.length === 0) {
      return { total: 0, sent: 0, failed: 0 };
    }

    const results = await Promise.allSettled(
      invitees.map(async (invitee) => {
        const response = await fetch(`${API_BASE_URL}/proposal-collabs/request`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...authHeaders(),
          },
          body: JSON.stringify({
            proposal_id: proposalId,
            collaborator_username: invitee.username,
          }),
        });

        if (!response.ok) {
          throw new Error(await getApiError(response, `Unable to invite @${invitee.username}.`));
        }

        return response.json();
      })
    );

    const sent = results.filter((result) => result.status === "fulfilled").length;
    return {
      total: invitees.length,
      sent,
      failed: invitees.length - sent,
    };
  };

  const mutation = useMutation({
    mutationFn: async (newPost) => {
      const formData = new FormData();
      formData.append("title", newPost.title);
      formData.append("body", newPost.text);
      formData.append("author", newPost.userName);
      formData.append("userName", newPost.userName);
      formData.append("userInitials", (newPost.userName || "").slice(0, 2).toUpperCase());
      formData.append("author_type", newPost.author_type);
      formData.append("author_img", newPost.author_img);
      formData.append("date", newPost.date);
      formData.append("governance_kind", newPost.governance_kind || "post");
      if (newPost.governance_kind === "decision") {
        formData.append("decision_level", newPost.decision_level || "standard");
        formData.append("voting_days", String(newPost.voting_days || 3));
        formData.append("execution_mode", "manual");
      }

      if (newPost.images?.length) {
        newPost.images.forEach((imageFile, index) => {
          formData.append("images", imageFile, imageFile.name || `image-${index + 1}.jpg`);
        });
        formData.append("media_layout", newPost.media_layout || "carousel");
      } else if (newPost.image) {
        formData.append("image", newPost.image, newPost.image.name || "image.jpg");
        formData.append("media_layout", newPost.media_layout || "carousel");
      }
      if (newPost.file) formData.append("file", newPost.file, newPost.file.name || "attachment");
      if (newPost.video) formData.append("video_file", newPost.video, newPost.video.name || "video.mp4");
      if (newPost.link) formData.append("link", newPost.link);

      const response = await fetch(`${API_BASE_URL}/proposals`, {
        method: "POST",
        headers: authHeaders(),
        body: formData,
      });

      if (!response.ok) {
        const message = await getApiError(
          response,
          `Failed to create post: ${response.status} ${response.statusText}`
        );
        throw new Error(message);
      }

      const createdPost = await response.json();
      const collabSummary = await requestComposerCollabs(createdPost?.id, newPost.collabInvitees || []);
      return { post: createdPost, collabSummary };
    },
    onSuccess: ({ post, collabSummary }) => {
      if (setPosts) {
        setPosts((oldPosts) => [post, ...oldPosts]);
      }
      queryClient.invalidateQueries({ queryKey: ["home-feed"] });
      queryClient.invalidateQueries({ queryKey: ["proposals"] });
      queryClient.invalidateQueries({ queryKey: ["proposal-collabs"] });
      refetchPosts?.();

      if (collabSummary?.total > 0) {
        const inviteLabel = collabSummary.sent === 1 ? "collab invite" : "collab invites";
        const message = collabSummary.failed
          ? `Post created. ${collabSummary.sent} ${inviteLabel} sent. ${collabSummary.failed} failed.`
          : `Post created. ${collabSummary.sent} ${inviteLabel} sent.`;
        setNotify([message]);
      }

      setDiscard(true);
      handleRemoveMedia();
      setProposalMode("post");
      setDecisionLevel("standard");
      setVotingDays(3);
      setText("");
      setPendingCollabInvitees([]);
      setCollabPromptUser(null);
      setCollabNotice("");
    },
    onError: (error) => setErrorMsg([formatBackendAuthErrorMessage(error, "Failed to create post.")]),
  });

  const publish = () => {
    const errors = [];
    if (!isAuthenticated) {
      requireAccount("Sign in to publish on SuperNova.");
      return;
    }
    try {
      requireBackendAuthSession();
    } catch {
      errors.push(BACKEND_AUTH_MISSING_MESSAGE);
    }
    if (!text.trim()) {
      errors.push(
        mediaValue || selectedFile || selectedFiles.length > 0
          ? "Make your proposal clear in words too. Add the question, context, or call to action for this media."
          : "Write a proposal, update, or question before publishing."
      );
    }
    if (!userData?.name) errors.push("Add your display name in profile settings first.");
    if (!userData?.species) errors.push("Pick a species in profile settings first.");

    if (errors.length > 0) {
      setErrorMsg(errors);
      return;
    }

    setErrorMsg([]);
    const derivedTitle = text.trim()
      ? text.trim().replace(/\s+/g, " ").slice(0, 70)
      : mediaType === "video"
      ? "Shared a video"
      : mediaType === "image"
      ? "Shared an image"
      : mediaType === "file"
      ? "Shared a file"
      : mediaType === "link"
      ? "Shared a link"
      : "New Post";

    mutation.mutate({
      title: derivedTitle,
      text,
      userName: userData.name,
      author_type: userData.species,
      author_img: normalizeAvatarValue(userData.avatar || ""),
      date: new Date().toISOString(),
      images: mediaType === "image" ? selectedFiles : [],
      image: mediaType === "image" ? selectedFile : null,
      media_layout: mediaType === "image" ? mediaLayout : "carousel",
      file: mediaType === "file" ? selectedFile : null,
      video: mediaType === "video" ? selectedFile : "",
      link: mediaType === "link" ? mediaValue : "",
      governance_kind: isDecisionMode ? "decision" : "post",
      decision_level: decisionLevel,
      voting_days: votingDays,
      collabInvitees: pendingCollabInvitees,
    });
  };

  const isYouTube = (url) => {
    return url?.includes("youtube.com") || url?.includes("youtu.be");
  };

  const getYouTubeId = (url) => {
    const regExp = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|&v=)([^#&?]*).*/;
    const match = url?.match(regExp);
    return match && match[2].length === 11 ? match[2] : null;
  };

  const renderMediaPreview = () => {
    if (!mediaType) return null;

    const safePreviewIndex = Math.min(previewIndex, Math.max(0, selectedFiles.length - 1));
    const previewCount = selectedFiles.length;
    const movePreview = (direction) => {
      if (previewCount <= 1) return;
      setPreviewIndex((index) => (index + direction + previewCount) % previewCount);
    };
    const getPreviewPoint = (event) => {
      const touch = event.changedTouches?.[0] || event.touches?.[0];
      if (touch) return { x: touch.clientX, y: touch.clientY };
      return { x: event.clientX, y: event.clientY };
    };
    const startPreviewSwipe = (event) => {
      if (event.button !== undefined && event.button !== 0) return;
      const point = getPreviewPoint(event);
      previewSwipeRef.current = { active: true, x: point.x, y: point.y, moved: false };
    };
    const trackPreviewSwipe = (event) => {
      if (!previewSwipeRef.current.active) return;
      const point = getPreviewPoint(event);
      const deltaX = point.x - previewSwipeRef.current.x;
      const deltaY = point.y - previewSwipeRef.current.y;
      if (Math.abs(deltaX) > 8 || Math.abs(deltaY) > 8) {
        previewSwipeRef.current = { ...previewSwipeRef.current, moved: true };
      }
    };
    const finishPreviewSwipe = (event) => {
      if (previewCount <= 1 || !previewSwipeRef.current.active) return;
      const point = getPreviewPoint(event);
      const deltaX = point.x - previewSwipeRef.current.x;
      const deltaY = point.y - previewSwipeRef.current.y;
      previewSwipeRef.current = { active: false, x: 0, y: 0, moved: false };
      if (Math.abs(deltaX) < 42 || Math.abs(deltaX) < Math.abs(deltaY) * 1.18) return;
      event.preventDefault();
      movePreview(deltaX < 0 ? 1 : -1);
    };
    const cancelPreviewSwipe = () => {
      previewSwipeRef.current = { active: false, x: 0, y: 0, moved: false };
    };
    const gridPreviewStyle = { height: "clamp(11.5rem, 52vw, 18rem)" };

    return (
      <div className="relative mt-2 overflow-hidden rounded-[1rem] border border-[var(--horizontal-line)] bg-[rgba(255,255,255,0.02)]">
        <button
          type="button"
          onClick={handleRemoveMedia}
          className="absolute right-3 top-3 z-10 flex h-7 w-7 items-center justify-center rounded-full bg-black/60 text-white backdrop-blur hover:bg-black/80"
          title="Remove attachment"
        >
          <IoClose />
        </button>

        {mediaType === "image" && selectedFiles.length > 0 && (
          <div className="flex flex-col gap-2">
            {mediaLayout === "grid" && selectedFiles.length > 1 ? (
              selectedFiles.length >= 4 ? (
                <div className="grid min-h-0 grid-cols-[minmax(0,1.58fr)_minmax(0,0.9fr)] gap-1 overflow-hidden rounded-[0.8rem]" style={gridPreviewStyle}>
                  <div className="relative h-full overflow-hidden bg-black/20">
                    <img src={imagePreviewUrls[0]} alt="Preview 1" className="absolute inset-0 h-full w-full object-cover" />
                  </div>
                  <div className="grid grid-rows-3 gap-1">
                    {selectedFiles.slice(1, 4).map((file, offset) => {
                      const index = offset + 1;
                      const hiddenCount = Math.max(0, selectedFiles.length - 4);
                      return (
                        <div key={`${file.name}-${index}`} className="relative min-h-0 overflow-hidden bg-black/20">
                          <img src={imagePreviewUrls[index]} alt={`Preview ${index + 1}`} className="absolute inset-0 h-full w-full object-cover" />
                          {index === 3 && hiddenCount > 0 && (
                            <span className="absolute inset-0 flex items-center justify-center bg-black/55 text-xl font-bold text-white">
                              +{hiddenCount}
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : selectedFiles.length === 3 ? (
                <div className="grid min-h-0 grid-cols-[minmax(0,1.58fr)_minmax(0,0.9fr)] gap-1 overflow-hidden rounded-[0.8rem]" style={gridPreviewStyle}>
                  <div className="relative h-full overflow-hidden bg-black/20">
                    <img src={imagePreviewUrls[0]} alt="Preview 1" className="absolute inset-0 h-full w-full object-cover" />
                  </div>
                  <div className="grid grid-rows-2 gap-1">
                    {selectedFiles.slice(1, 3).map((file, offset) => {
                      const index = offset + 1;
                      return (
                        <div key={`${file.name}-${index}`} className="relative min-h-0 overflow-hidden bg-black/20">
                          <img src={imagePreviewUrls[index]} alt={`Preview ${index + 1}`} className="absolute inset-0 h-full w-full object-cover" />
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <div className="grid min-h-0 grid-cols-2 gap-1 overflow-hidden rounded-[0.8rem]" style={gridPreviewStyle}>
                  {selectedFiles.slice(0, 2).map((file, index) => (
                    <div key={`${file.name}-${index}`} className="relative min-h-0 overflow-hidden bg-black/20">
                      <img src={imagePreviewUrls[index]} alt={`Preview ${index + 1}`} className="absolute inset-0 h-full w-full object-cover" />
                    </div>
                  ))}
                </div>
              )
            ) : (
              <div
                className="relative overflow-hidden rounded-[0.8rem] bg-black/20"
                style={{ touchAction: "pan-y" }}
                onPointerDown={startPreviewSwipe}
                onPointerMove={trackPreviewSwipe}
                onPointerUp={finishPreviewSwipe}
                onPointerCancel={cancelPreviewSwipe}
                onTouchStart={startPreviewSwipe}
                onTouchMove={trackPreviewSwipe}
                onTouchEnd={finishPreviewSwipe}
                onTouchCancel={cancelPreviewSwipe}
              >
                <img
                  src={imagePreviewUrls[safePreviewIndex]}
                  alt={`Preview ${safePreviewIndex + 1}`}
                  className="h-64 w-full object-cover"
                />
                {selectedFiles.length > 1 && (
                  <>
                    <button
                      type="button"
                      onClick={() => movePreview(-1)}
                      className="absolute left-2 top-1/2 z-10 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full bg-black/45 text-white backdrop-blur"
                      aria-label="Previous preview image"
                    >
                      <IoChevronBack />
                    </button>
                    <button
                      type="button"
                      onClick={() => movePreview(1)}
                      className="absolute right-2 top-1/2 z-10 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full bg-black/45 text-white backdrop-blur"
                      aria-label="Next preview image"
                    >
                      <IoChevronForward />
                    </button>
                    <span className="absolute right-2 top-2 z-10 rounded-full bg-black/45 px-2 py-0.5 text-[0.68rem] font-semibold text-white">
                      {safePreviewIndex + 1}/{selectedFiles.length}
                    </span>
                  </>
                )}
              </div>
            )}

            {selectedFiles.length > 1 && (
              <div className="flex items-center justify-between gap-2 rounded-[0.85rem] bg-black/15 p-1">
                {[
                  { value: "carousel", label: "Carousel", icon: IoAlbumsOutline },
                  { value: "grid", label: "Grid", icon: IoGridOutline },
                ].map((option) => {
                  const Icon = option.icon;
                  const active = mediaLayout === option.value;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setMediaLayout(option.value)}
                      className={`flex flex-1 items-center justify-center gap-1.5 rounded-[0.7rem] px-2 py-2 text-[0.76rem] font-semibold transition-colors ${
                        active
                          ? "bg-[var(--pink)] text-white shadow-[var(--shadow-pink)]"
                          : "text-[var(--text-gray-light)]"
                      }`}
                    >
                      <Icon className="text-[0.95rem]" />
                      {option.label}
                    </button>
                  );
                })}
              </div>
            )}

            {mediaLayout === "carousel" && selectedFiles.length > 1 && (
              <div className="flex justify-center gap-1.5">
                {selectedFiles.map((file, index) => (
                  <img
                    key={`${file.name}-${index}`}
                    src={imagePreviewUrls[index]}
                    alt=""
                    onClick={() => setPreviewIndex(index)}
                    className={`h-8 w-8 rounded-md object-cover ${
                      index === safePreviewIndex ? "ring-2 ring-[var(--pink)]" : "opacity-55"
                    }`}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {mediaType === "video" && selectedFile && (
          <video
            src={selectedFilePreviewUrl}
            controls
            className="max-h-64 w-full rounded-[0.8rem] object-contain"
          />
        )}

        {mediaType === "link" && isYouTube(mediaValue) && (
          <div className="aspect-video w-full rounded-[0.8rem] overflow-hidden">
            <iframe
              width="100%"
              height="100%"
              src={`https://www.youtube.com/embed/${getYouTubeId(mediaValue)}`}
              title="YouTube video player"
              frameBorder="0"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
          </div>
        )}

        {mediaType === "link" && !isYouTube(mediaValue) && (
          <div className="flex items-center gap-3 rounded-[0.8rem] bg-[rgba(255,255,255,0.05)] p-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--blue)] text-white shadow-lg">
              <FaFileAlt className="text-[1.2rem]" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[0.85rem] font-medium text-[var(--text-black)]">
                Link Attached
              </p>
              <a
                href={mediaValue}
                target="_blank"
                rel="noreferrer"
                className="truncate text-[0.75rem] text-[var(--blue)] hover:underline"
              >
                {mediaValue}
              </a>
            </div>
          </div>
        )}

        {mediaType === "file" && selectedFileIsPdf && (
          <PdfPager src={selectedFilePreviewUrl} title={mediaValue || "PDF preview"} compact />
        )}

        {mediaType === "file" && !selectedFileIsPdf && (
          <div className="flex items-center gap-3 rounded-[0.8rem] bg-[rgba(255,255,255,0.05)] p-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--pink)] text-white shadow-lg">
              <FaFileAlt className="text-[1.2rem]" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[0.85rem] font-medium text-[var(--text-black)]">
                {mediaValue}
              </p>
              <p className="text-[0.7rem] text-[var(--text-gray-light)]">Document attached</p>
            </div>
          </div>
        )}
      </div>
    );
  };

  const composerAiContext = {
    current_text: text,
    media_type: mediaType,
    media_label:
      mediaType === "image"
        ? `${selectedFiles.length} selected image${selectedFiles.length === 1 ? "" : "s"}`
        : selectedFile?.name || mediaValue || "",
    image_count: mediaType === "image" ? selectedFiles.length : 0,
    governance_kind: isDecisionMode ? "decision" : "post",
    decision_level: isDecisionMode ? decisionLevel : "",
    voting_days: isDecisionMode ? votingDays : undefined,
  };

  const renderContent = () => (
    <div className="flex flex-col gap-3 text-[var(--text-black)]">
      <div className="relative">
        <textarea
          ref={textAreaRef}
          placeholder="Share your idea, update, or question"
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            mentionAutocomplete.trackCaret(event.currentTarget);
          }}
          onClick={(event) => mentionAutocomplete.trackCaret(event.currentTarget)}
          onKeyDown={mentionAutocomplete.handleKeyDown}
          onKeyUp={(event) => mentionAutocomplete.trackCaret(event.currentTarget)}
          rows={1}
          className="composer-textarea min-h-[7.4rem] max-h-[min(72dvh,58rem)] w-full resize-none rounded-[1.1rem] border border-[var(--horizontal-line)] bg-[rgba(255,255,255,0.06)] px-4 py-3 text-[0.92rem] outline-none placeholder:text-[var(--text-gray-light)]"
        />
        <MentionAutocomplete controller={mentionAutocomplete} />
      </div>

      {collabPromptUser && (
        <div className="composer-collab-prompt flex flex-wrap items-center justify-between gap-2 rounded-[1rem] px-3 py-2">
          <div className="flex min-w-0 items-center gap-2">
            <span
              className="flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-full text-[0.64rem] font-black uppercase text-white"
              style={{
                ...speciesAvatarStyle(collabPromptUser.species || "human"),
                backgroundColor: speciesAccentColor(collabPromptUser.species || "human"),
              }}
            >
              {collabPromptUser.avatar ? (
                <img
                  src={collabPromptUser.avatar}
                  alt=""
                  className="h-full w-full object-cover"
                  loading="lazy"
                  referrerPolicy="no-referrer"
                />
              ) : (
                collabPromptUser.initials
              )}
            </span>
            <p className="min-w-0 text-[0.78rem] font-semibold">
              Invite <span className="text-[var(--pink)]">@{collabPromptUser.username}</span> as collaborator?
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              onClick={() => addPendingCollabInvitee(collabPromptUser)}
              className="composer-collab-action rounded-full px-3 py-1.5 text-[0.72rem] font-black"
            >
              Invite
            </button>
            <button
              type="button"
              onClick={() => setCollabPromptUser(null)}
              className="composer-collab-action secondary rounded-full px-3 py-1.5 text-[0.72rem] font-black"
            >
              Not now
            </button>
          </div>
        </div>
      )}

      {(pendingCollabInvitees.length > 0 || collabNotice) && (
        <div className="composer-collab-strip flex flex-col gap-2 rounded-[1rem] px-3 py-2">
          {pendingCollabInvitees.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="flex items-center gap-1 text-[0.66rem] font-black uppercase tracking-[0.12em] text-[var(--text-gray-light)]">
                <IoPersonAddOutline className="text-[var(--pink)]" />
                Collab invites
              </span>
              {pendingCollabInvitees.map((invitee) => (
                <button
                  type="button"
                  key={invitee.key}
                  onClick={() => removePendingCollabInvitee(invitee.username)}
                  className="composer-collab-chip inline-flex max-w-full items-center gap-1.5 rounded-full px-2 py-1 text-[0.68rem] font-bold"
                  title={`Remove @${invitee.username}`}
                >
                  <span
                    className="flex h-5 w-5 shrink-0 items-center justify-center overflow-hidden rounded-full text-[0.56rem] font-black uppercase text-white"
                    style={{
                      ...speciesAvatarStyle(invitee.species || "human"),
                      backgroundColor: speciesAccentColor(invitee.species || "human"),
                    }}
                  >
                    {invitee.avatar ? (
                      <img
                        src={invitee.avatar}
                        alt=""
                        className="h-full w-full object-cover"
                        loading="lazy"
                        referrerPolicy="no-referrer"
                      />
                    ) : (
                      invitee.initials
                    )}
                  </span>
                  <span className="truncate">@{invitee.username}</span>
                  <span className="composer-collab-pending-pill hidden shrink-0 rounded-full px-1.5 py-0.5 text-[0.52rem] uppercase tracking-[0.08em] sm:inline">
                    invite pending
                  </span>
                  <span className="composer-collab-remove-dot flex h-4 w-4 shrink-0 items-center justify-center rounded-full" aria-hidden="true">
                    <IoClose className="text-[0.72rem]" />
                  </span>
                </button>
              ))}
            </div>
          )}
          {collabNotice && <p className="text-[0.72rem] font-semibold text-[var(--text-gray-light)]">{collabNotice}</p>}
        </div>
      )}

      <AiDelegateActionModal
        open={aiComposerOpen}
        mode="composer_assist"
        target={{ title: proposalMode === "decision" ? "Decision composer" : "Post composer", text }}
        composerContext={composerAiContext}
        onClose={() => setAiComposerOpen(false)}
        onApproved={() => {
          setAiComposerOpen(false);
          setNotify(["AI post published as the selected delegate."]);
          refetchPosts?.();
          queryClient.invalidateQueries({ queryKey: ["home-feed"] });
          queryClient.invalidateQueries({ queryKey: ["proposals"] });
        }}
      />

      {renderMediaPreview()}

      <div className="flex flex-nowrap items-center justify-between gap-1.5 text-[0.78rem]">
        <div className="flex min-w-0 shrink-0 items-center gap-1">
          {userAvatar ? (
            <img
              src={userAvatar}
              alt="profile"
              onError={(event) => {
                event.currentTarget.src = defaultAvatar;
              }}
              className="composer-action-avatar mr-1 h-9 w-9 shrink-0 rounded-full border object-cover"
              style={userAvatarStyle}
            />
          ) : (
            <div className="composer-action-avatar mr-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border bgGray text-[0.72rem] font-semibold" style={userAvatarStyle}>
              {(userData?.name || "SN").slice(0, 2).toUpperCase()}
            </div>
          )}
          <MediaInput
            type="image"
            icon={<IoImageOutline className="text-[1rem]" />}
            accept="image/*"
            multiple
            inputRef={imageInputRef}
            handleFileChange={(event) => handleFileChange(event, "image")}
          />
          <MediaInput
            type="video"
            icon={<IoVideocamOutline className="text-[1rem]" />}
            accept="video/*"
            inputRef={videoInputRef}
            handleFileChange={(event) => handleFileChange(event, "video")}
          />
          <MediaInput
            type="file"
            icon={<IoDocumentTextOutline className="text-[1rem]" />}
            inputRef={fileInputRef}
            handleFileChange={(event) => handleFileChange(event, "file")}
          />
          <button
            type="button"
            onClick={() => setAiComposerOpen(true)}
            className="composer-icon-button flex h-10 w-10 shrink-0 items-center justify-center rounded-full font-semibold text-[var(--pink)]"
            aria-label="AI"
            title="AI"
          >
            <IoSparklesOutline className="text-[1.05rem]" />
          </button>
        </div>

        <div className="flex min-w-0 shrink-0 items-center gap-1.5 text-[0.82rem] text-white">
          <button
            type="button"
            onClick={() => setProposalMode((mode) => (mode === "decision" ? "post" : "decision"))}
            className={`composer-governance-button flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${
              isDecisionMode ? "active" : ""
            }`}
            aria-pressed={isDecisionMode}
            aria-label={isDecisionMode ? "Decision poll enabled" : "Enable decision poll"}
            title={isDecisionMode ? "Decision poll enabled" : "Decision poll"}
          >
            <IoBarChartOutline className="text-[1.08rem]" />
          </button>
          <button
            type="button"
            onClick={() => setDiscard(true)}
            className="composer-icon-button flex h-10 w-10 shrink-0 items-center justify-center rounded-full font-semibold"
            aria-label="Close composer"
            title="Close composer"
          >
            <IoClose className="text-[1.08rem]" />
          </button>
          <button
            type="button"
            onClick={publish}
            disabled={mutation.isPending}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--pink)] font-semibold text-white shadow-[var(--shadow-pink)] transition-transform hover:scale-105 disabled:opacity-60 disabled:hover:scale-100"
            aria-label={mutation.isPending ? "Publishing" : "Post"}
            title={mutation.isPending ? "Publishing" : "Post"}
          >
            <IoSend className="text-[1.05rem]" />
          </button>
        </div>
      </div>

      {isDecisionMode && (
        <div className="composer-governance-strip composer-decision-row is-decision flex h-10 w-full min-w-0 items-center gap-1 rounded-full px-1.5">
          <label className="composer-deadline-control flex min-w-0 flex-1 items-center gap-1.5 rounded-full px-2">
            <IoTimeOutline className="shrink-0 text-[0.92rem]" />
            <span className="w-7 shrink-0 text-center text-[0.66rem] font-black tabular-nums">{votingDays}d</span>
            <input
              type="range"
              min="1"
              max="14"
              value={votingDays}
              onChange={(event) => setVotingDays(Number(event.target.value))}
              className="min-w-0 flex-1 accent-[var(--pink)]"
              aria-label="Voting days"
            />
          </label>
          <button
            type="button"
            onClick={() => setDecisionLevel((level) => (level === "important" ? "standard" : "important"))}
            className="composer-threshold-button flex h-8 w-14 shrink-0 items-center justify-center gap-1 rounded-full text-[0.66rem] font-black tabular-nums"
            aria-label={`Decision threshold ${decisionThresholdLabel}`}
            title="Toggle decision threshold"
          >
            <IoShieldCheckmarkOutline className="text-[0.82rem]" />
            {decisionThresholdLabel}
          </button>
        </div>
      )}
    </div>
  );

  return (
    <div className="w-full">
      {errorMsg.length > 0 && <ErrorMessage messages={errorMsg} />}
      {embedded ? (
        renderContent()
      ) : (
        <LiquidGlass className="rounded-[1.45rem] px-3 py-3 sm:px-4 sm:py-4">
          {renderContent()}
        </LiquidGlass>
      )}
    </div>
  );
}

export default InputFields;
