import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { Button, Input } from "../components";
import { useAuth } from "../context/AuthContext";
import { useDataMode } from "../context/DataModeContext";
import { humanizeApiError } from "../api/errors.js";
import { ApiClientError } from "../api/client.js";

export function LoginPage() {
  const { login, isAuthenticated, loading: authLoading } = useAuth();
  const { setMode } = useDataMode();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from?.pathname || "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  if (!authLoading && isAuthenticated) {
    return <Navigate to={from} replace />;
  }

  async function onSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      const human = humanizeApiError(
        err instanceof ApiClientError
          ? err
          : new ApiClientError(err?.message || "Sign-in failed", { status: 401 }),
      );
      setError(human);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-page__panel">
        <header className="login-page__brand">
          <p className="login-page__mark">Business OS</p>
          <h1 className="login-page__title">Owner sign-in</h1>
          <p className="login-page__sub">
            Access your digital team. Session credentials stay on this device.
          </p>
        </header>

        <form className="login-page__form stack" onSubmit={onSubmit} noValidate>
          {error ? (
            <div className="login-page__error" role="alert">
              <strong>{error.title}</strong>
              <p>{error.description}</p>
            </div>
          ) : null}

          <Input
            id="owner-email"
            name="email"
            type="email"
            label="Email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <Input
            id="owner-password"
            name="password"
            type="password"
            label="Password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />

          <Button type="submit" variant="primary" disabled={submitting || !email || !password}>
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <p className="login-page__foot">
          <button
            type="button"
            className="login-page__demo-link"
            onClick={() => {
              setMode("demo");
              navigate("/", { replace: true });
            }}
          >
            Browse demo data without signing in
          </button>
        </p>
      </div>
    </div>
  );
}
