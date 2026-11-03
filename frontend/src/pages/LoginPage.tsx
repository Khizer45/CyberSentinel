import { useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router";
import { useMutation } from "@tanstack/react-query";
import { Button } from "../components/Button";
import { TextField } from "../components/FormFields";
import { Callout, ErrorCallout, FullPageLoader } from "../components/States";
import { useAuth } from "../features/auth/AuthContext";
import { usePageTitle } from "../hooks/usePageTitle";
import { AuthLayout } from "../layouts/AuthLayout";

/** Only same-origin relative paths are accepted as post-login destinations (no open redirects). */
export function safeRedirect(value: unknown): string {
  return typeof value === "string" && value.startsWith("/") && !value.startsWith("//") && !value.startsWith("/\\") ? value : "/";
}

export function LoginPage() {
  usePageTitle("Sign in");
  const { status, login, notice } = useAuth();
  const location = useLocation();
  const from = safeRedirect((location.state as { from?: unknown } | null)?.from);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const mutation = useMutation({
    mutationFn: () => login(email.trim(), password),
    onError: () => setPassword(""),
  });

  if (status === "loading") return <FullPageLoader label="Checking your session…" />;
  if (status === "authenticated") return <Navigate to={from} replace />;

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!mutation.isPending) mutation.mutate();
  };

  return (
    <AuthLayout>
      <div className="auth-card card" style={{ padding: 28 }}>
        <div className="stack-sm">
          <h1>Sign in</h1>
          <p className="muted">Use the account issued by your CyberSentinel administrator.</p>
        </div>
        {notice && !mutation.isError ? <Callout tone="info">{notice}</Callout> : null}
        <ErrorCallout error={mutation.error} />
        <form className="stack" onSubmit={onSubmit} noValidate>
          <TextField
            label="Email"
            type="email"
            name="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <TextField
            label="Password"
            type="password"
            name="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <Button type="submit" variant="primary" loading={mutation.isPending} disabled={!email.trim() || !password}>
            Sign in
          </Button>
        </form>
        <p className="small subtle">
          Repeated failed attempts temporarily lock the account. Forgotten passwords are reset by an administrator.
        </p>
      </div>
    </AuthLayout>
  );
}
