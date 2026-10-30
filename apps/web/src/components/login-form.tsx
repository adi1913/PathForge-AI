"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { consumeExpiredFlag, setSession } from "@/lib/auth";
import { errorText } from "@/lib/use-load";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";

export function LoginForm() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);

  useEffect(() => setExpired(consumeExpiredFlag()), []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result =
        mode === "login"
          ? await api.login(email.trim(), password)
          : await api.register({ email: email.trim(), password, display_name: displayName.trim() || null });
      setSession({ token: result.access_token, user: result.user });
      setPassword("");
      router.replace("/");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const registering = mode === "register";
  return (
    <Card>
      <CardHeader>
        <CardTitle>{registering ? "Create your account" : "Sign in to PathForge AI"}</CardTitle>
        <CardDescription>
          {registering ? "Passwords need at least 10 characters." : "Your data is private to your account."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {expired && (
          <p role="status" className="mb-3 rounded-md border border-border bg-muted p-2 text-sm">
            Your session expired. Please sign in again.
          </p>
        )}
        <form onSubmit={submit} className="space-y-3">
          {registering && (
            <div>
              <Label htmlFor="display-name">Display name (optional)</Label>
              <Input id="display-name" value={displayName} maxLength={100} onChange={(e) => setDisplayName(e.target.value)} />
            </div>
          )}
          <div>
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete={registering ? "new-password" : "current-password"}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Please wait..." : registering ? "Create account" : "Sign in"}
          </Button>
        </form>
        <button
          type="button"
          className="mt-3 text-sm underline"
          onClick={() => {
            setMode(registering ? "login" : "register");
            setError(null);
          }}
        >
          {registering ? "Already have an account? Sign in" : "New here? Create an account"}
        </button>
      </CardContent>
    </Card>
  );
}
