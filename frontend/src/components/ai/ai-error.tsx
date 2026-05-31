"use client";

import { Button } from "@/components/ui/button";

interface Props {
  error: string;
  onRetry?: () => void;
}

/** Friendly error display — recognises the 503 "AI temporarily unavailable" path. */
export function AIError({ error, onRetry }: Props) {
  const isQuota =
    /503/.test(error) ||
    /unavailable/i.test(error) ||
    /rate.?limit/i.test(error);
  const isMissingKey = /GEMINI_API_KEY/.test(error);

  let body: string;
  if (isMissingKey) {
    body = "Gemini isn’t configured on this server. Set GEMINI_API_KEY in backend/.env and restart the backend.";
  } else if (isQuota) {
    body = "AI temporarily unavailable (free-tier limit or transient error). Try again in a few seconds.";
  } else {
    body = error;
  }

  return (
    <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-200">
      <p>{body}</p>
      {onRetry && !isMissingKey && (
        <Button variant="ghost" onClick={onRetry} className="mt-2 text-xs">
          Try again
        </Button>
      )}
    </div>
  );
}
