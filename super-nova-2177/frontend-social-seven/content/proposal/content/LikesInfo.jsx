"use client";

import { useEffect, useMemo, useState } from "react";
import { BsFillCpuFill } from "react-icons/bs";
import { FaBriefcase, FaUser } from "react-icons/fa";
import LiquidGlass from "@/content/liquid glass/LiquidGlass";
import { useUser } from "@/content/profile/UserContext";
import { API_BASE_URL } from "@/utils/apiBase";
import { speciesAccentGradient } from "@/utils/species";
import { buildWeightedVoteSummary } from "@/utils/voteWeights";

const SLIDER_BLUE = "#5e8dfa";

/* Old weighted-slider blue start: hsl(230,80%,75%). */
function getSliderColor(ratio) {
  const pinkShare = Math.round(Math.min(Math.max(ratio, 0), 100));
  return `color-mix(in srgb, ${SLIDER_BLUE} ${100 - pinkShare}%, var(--pink) ${pinkShare}%)`;
}

function SpeciesVoteRow({ icon: Icon, label, likes, dislikes, internalPercent, accent }) {
  const ratio = Math.round(internalPercent || 0);
  const hasVotes = likes + dislikes > 0;

  return (
    <div className="vote-info-row grid w-full grid-cols-[2.5rem_minmax(0,1fr)] gap-x-3 gap-y-1.5 rounded-[1rem] px-3 py-2.5">
      <span className="vote-info-icon flex h-10 w-10 shrink-0 items-center justify-center rounded-full">
        <Icon />
      </span>
      <div className="min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[0.78rem] font-semibold text-[var(--text-black)]">{label}</span>
          <span className="text-right text-[0.72rem] text-[var(--text-gray-light)]">
            {hasVotes ? `${ratio}% - ${likes} yes - ${dislikes} no` : "No votes yet"}
          </span>
        </div>
      </div>
      <div className="vote-info-track col-start-2 h-1.5 rounded-full">
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{
            width: `${internalPercent || 0}%`,
            background: accent,
          }}
        />
      </div>
    </div>
  );
}

function LikesInfo({ proposalId, likesData, dislikesData, className = "" }) {
  const [likes, setLikes] = useState([]);
  const [dislikes, setDislikes] = useState([]);
  const [error, setError] = useState("");
  const { userData } = useUser();
  const backendUrl = userData?.activeBackend || API_BASE_URL;

  useEffect(() => {
    if (likesData || dislikesData) {
      setLikes(likesData || []);
      setDislikes(dislikesData || []);
      setError("");
      return;
    }

    async function fetchVotes() {
      if (!backendUrl) {
        setError("API base URL is not configured.");
        return;
      }

      try {
        setError("");
        const response = await fetch(`${backendUrl}/proposals/${proposalId}`);
        if (!response.ok) {
          setError(`Failed to load proposal: ${response.status} ${response.statusText}`);
          return;
        }

        const data = await response.json();
        setLikes(data.likes || []);
        setDislikes(data.dislikes || []);
      } catch (err) {
        setError(`Failed to fetch vote details: ${err.message}`);
      }
    }

    fetchVotes();
  }, [backendUrl, proposalId, likesData, dislikesData]);

  const counts = useMemo(() => buildWeightedVoteSummary(likes, dislikes), [likes, dislikes]);

  const totalVotes = likes.length + dislikes.length;
  const overallApproval = Math.round(counts.supportPercent || 0);

  return (
    <LiquidGlass className={`vote-info-glass w-full rounded-[1.2rem] p-3 ${className}`.trim()}>
      <div className="vote-info-content flex w-full flex-col gap-2.5">
        {error ? (
          <p className="text-[0.76rem] text-red-400">{error}</p>
        ) : (
          <>
            {/* Overall weighted approval header */}
            <div className="vote-info-header flex items-center justify-between rounded-[0.8rem] px-3 py-2">
              <span className="text-[0.76rem] font-semibold text-[var(--text-black)]">
                Weighted Approval
              </span>
              <span className="text-[0.82rem] font-bold" style={{ color: getSliderColor(overallApproval) }}>
                {overallApproval}%
              </span>
            </div>
            <div className="vote-info-track mx-3 mb-1 h-1 rounded-full">
              <div
                className="h-full rounded-full transition-all duration-300"
                style={{
                  width: `${Math.min(counts.supportPercent, 100)}%`,
                  background: `linear-gradient(90deg, ${SLIDER_BLUE} 0%, ${getSliderColor(counts.supportPercent)} 100%)`,
                }}
              />
            </div>
            <p className="mb-1 text-center text-[0.66rem] text-[var(--text-gray-light)]">
              {totalVotes} total vote{totalVotes !== 1 ? "s" : ""} - Each species carries 33% weight
            </p>

            <SpeciesVoteRow
              icon={FaUser}
              label="Humans"
              likes={counts.bySpecies.human.yes}
              dislikes={counts.bySpecies.human.no}
              internalPercent={counts.bySpecies.human.internalPercent}
              accent={speciesAccentGradient("human")}
            />
            <SpeciesVoteRow
              icon={FaBriefcase}
              label="ORG"
              likes={counts.bySpecies.company.yes}
              dislikes={counts.bySpecies.company.no}
              internalPercent={counts.bySpecies.company.internalPercent}
              accent={speciesAccentGradient("company")}
            />
            <SpeciesVoteRow
              icon={BsFillCpuFill}
              label="AI"
              likes={counts.bySpecies.ai.yes}
              dislikes={counts.bySpecies.ai.no}
              internalPercent={counts.bySpecies.ai.internalPercent}
              accent={speciesAccentGradient("ai")}
            />
          </>
        )}
      </div>
    </LiquidGlass>
  );
}

export default LikesInfo;
