"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { IoAdd, IoChevronDown, IoCheckmark } from "react-icons/io5";
import { avatarDisplayUrl } from "@/utils/avatar";

function delegateInitials(delegate = {}) {
  const label = delegate.display_name || delegate.username || "AI";
  return String(label).slice(0, 2).toUpperCase();
}

function delegateProviderLabel(delegate = {}) {
  const provider = delegate.provider_connection?.text || {};
  return provider.model_label || provider.provider_label || delegate.model_identity || "server/fallback";
}

function DelegateAvatar({ delegate, defaultAvatar }) {
  return (
    <span className="ai-delegate-picker-avatar">
      {delegate.avatar_url ? (
        <img src={avatarDisplayUrl(delegate.avatar_url, defaultAvatar)} alt="" className="h-full w-full object-cover" />
      ) : (
        delegateInitials(delegate)
      )}
    </span>
  );
}

function DelegateSummary({ delegate, defaultAvatar, compact = false }) {
  const traits = Array.isArray(delegate?.persona_traits) ? delegate.persona_traits.slice(0, compact ? 2 : 3) : [];
  return (
    <span className="flex min-w-0 flex-1 items-center gap-3 text-left">
      <DelegateAvatar delegate={delegate} defaultAvatar={defaultAvatar} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[0.82rem] font-black text-[var(--text-black)]">
          {delegate.display_name || delegate.username}
        </span>
        <span className="mt-0.5 block truncate text-[0.68rem] font-semibold text-[var(--text-gray-light)]">
          {delegate.custody_label || "Custodied AI delegate"}
        </span>
        <span className="mt-1 flex flex-wrap gap-1">
          {traits.map((trait) => (
            <span key={trait} className="ai-delegate-picker-chip">
              {trait}
            </span>
          ))}
          <span className="ai-delegate-picker-chip">{delegateProviderLabel(delegate)}</span>
        </span>
      </span>
    </span>
  );
}

export default function AiDelegatePicker({
  delegates = [],
  value = "",
  onChange,
  onCreateDelegate,
  defaultAvatar = "",
  disabledCount = 0,
}) {
  const [open, setOpen] = useState(false);
  const pickerRef = useRef(null);
  const selectedDelegate = useMemo(() => {
    if (!delegates.length) return null;
    return delegates.find((delegate) => String(delegate.id || "") === String(value || "")) || delegates[0];
  }, [delegates, value]);

  useEffect(() => {
    if (!open) return undefined;
    const closeOnOutsidePointer = (event) => {
      if (!pickerRef.current || pickerRef.current.contains(event.target)) return;
      setOpen(false);
    };
    document.addEventListener("pointerdown", closeOnOutsidePointer, true);
    return () => document.removeEventListener("pointerdown", closeOnOutsidePointer, true);
  }, [open]);

  if (!selectedDelegate) return null;
  const canOpenMenu = delegates.length > 1 || Boolean(onCreateDelegate);

  return (
    <div ref={pickerRef} className="ai-delegate-picker" data-ai-delegate-picker>
      <p className="mb-2 text-[0.62rem] font-black uppercase tracking-[0.14em] text-[var(--text-gray-light)]">
        AI delegate
      </p>
      <button
        type="button"
        className={`ai-delegate-picker-button ${open ? "is-open" : ""}`}
        onClick={() => {
          if (canOpenMenu) setOpen((current) => !current);
        }}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <DelegateSummary delegate={selectedDelegate} defaultAvatar={defaultAvatar} />
        {canOpenMenu && <IoChevronDown className={`shrink-0 text-[1rem] transition-transform ${open ? "rotate-180" : ""}`} />}
      </button>
      {open && canOpenMenu && (
        <div className="ai-delegate-picker-menu" role="listbox">
          {delegates.map((delegate) => {
            const isSelected = String(delegate.id || "") === String(selectedDelegate.id || "");
            return (
              <button
                key={delegate.id || delegate.username}
                type="button"
                className={`ai-delegate-picker-option ${isSelected ? "is-selected" : ""}`}
                role="option"
                aria-selected={isSelected}
                onClick={() => {
                  onChange?.(String(delegate.id || ""));
                  setOpen(false);
                }}
              >
                <DelegateSummary delegate={delegate} defaultAvatar={defaultAvatar} compact />
                {isSelected && <IoCheckmark className="shrink-0 text-[var(--pink)]" />}
              </button>
            );
          })}
          {onCreateDelegate && (
            <button
              type="button"
              className="ai-delegate-picker-option ai-delegate-picker-create"
              onClick={() => {
                setOpen(false);
                onCreateDelegate();
              }}
            >
              <span className="ai-delegate-picker-avatar ai-delegate-picker-create-icon">
                <IoAdd />
              </span>
              <span className="min-w-0 flex-1 text-left">
                <span className="block text-[0.82rem] font-black text-[var(--text-black)]">+ Create AI delegate</span>
                <span className="mt-0.5 block text-[0.68rem] font-semibold text-[var(--text-gray-light)]">
                  Create one in this popup, or open the full Genesis page.
                </span>
              </span>
            </button>
          )}
        </div>
      )}
      {disabledCount > 0 && (
        <p className="mt-2 text-[0.65rem] font-semibold text-[var(--text-gray-light)]">
          {disabledCount} disabled delegate{disabledCount === 1 ? "" : "s"} hidden from drafting.
        </p>
      )}
    </div>
  );
}
