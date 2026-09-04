import { useState } from "react";
import { Button } from "./Button";
import { humanizeApiError } from "../api/errors.js";

export function LiveError({ error, onRetry, resourceLabel = "this data" }) {
  const [showTech, setShowTech] = useState(false);
  const human = humanizeApiError(error);

  return (
    <div className="state-block error-state" role="alert">
      <h3 className="state-block__title">{human.title}</h3>
      <p className="state-block__desc">
        {human.description || `We couldn't load ${resourceLabel}. Your data has not been changed.`}
      </p>
      <div className="state-block__actions">
        {onRetry ? (
          <Button variant="secondary" onClick={onRetry}>
            Try again
          </Button>
        ) : null}
        <Button variant="ghost" size="sm" onClick={() => setShowTech((v) => !v)}>
          {showTech ? "Hide technical details" : "Technical details"}
        </Button>
      </div>
      {showTech ? (
        <pre className="tech-details" tabIndex={0}>
          {[
            human.status ? `status=${human.status}` : null,
            human.code ? `code=${human.code}` : null,
            error?.requestId ? `request_id=${error.requestId}` : null,
            error?.message ? `message=${error.message}` : null,
          ]
            .filter(Boolean)
            .join("\n")}
        </pre>
      ) : null}
    </div>
  );
}
