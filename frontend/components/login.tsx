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
          La última palabra
          <br />
          siempre es tuya.
        </h1>
        <p>
          Revisa las acciones del asistente, confirma los detalles y mantén el control en cada paso.
        </p>
        <div className="login-note">
          <ShieldCheck size={20} /> Entorno de simulación · Sin movimientos de dinero real
        </div>
      </section>
      <form
        action={(form) =>
          startTransition(async () => {
            try {
              setError(await login(form));
            } catch {
              setError("No se ha podido iniciar sesión.");
            }
          })
        }
      >
        <span className="eyebrow">ACCESO PRIVADO</span>
        <h2>Centro de control</h2>
        <p>Introduce tu contraseña de revisión.</p>
        <label htmlFor="password">Contraseña</label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          maxLength={256}
        />
        <button disabled={pending}>
          {pending ? "Accediendo…" : "Entrar al espacio"}
          <ArrowUpRight size={18} />
        </button>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <small>Las credenciales de AIFindr permanecen en el servidor.</small>
      </form>
    </main>
  );
}
