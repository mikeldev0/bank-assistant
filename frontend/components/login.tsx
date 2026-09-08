"use client";
import { useState, useTransition } from "react";
import { ArrowUpRight, ShieldCheck } from "lucide-react";
import { login } from "@/app/actions";
export function Login() {
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  return (
    <main className="login">
      <section>
        <div className="brand">
          <span className="brand-icon">b.</span> bank assistant
        </div>
        <span className="eyebrow">HUMAN IN THE LOOP</span>
        <h1>
          The final say
          <br />
          is always yours.
        </h1>
        <p>
          Review the assistant&apos;s actions, confirm the details, and stay in control at every
          step.
        </p>
        <div className="login-note">
          <ShieldCheck size={20} /> Simulation environment · No real money movement
        </div>
      </section>
      <form
        action={(form) =>
          startTransition(async () => {
            try {
              setError(await login(form));
            } catch {
              setError("Unable to sign in.");
            }
          })
        }
      >
        <span className="eyebrow">PRIVATE ACCESS</span>
        <h2>Control Center</h2>
        <p>Enter your review password.</p>
        <label htmlFor="password">Password</label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          maxLength={256}
        />
        <button disabled={pending}>
          {pending ? "Signing in…" : "Enter workspace"}
          <ArrowUpRight size={18} />
        </button>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <small>AIFindr credentials remain on the server.</small>
      </form>
    </main>
  );
}
