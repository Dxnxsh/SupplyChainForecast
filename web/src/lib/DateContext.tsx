import { createContext, useContext, useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

interface DateCtx {
  asOf: string | null;
  setAsOf: (d: string | null) => void;
  /** Latest date the live data actually covers (YYYY-MM-DD), null until resolved. */
  maxDate: string | null;
}

const Ctx = createContext<DateCtx>({ asOf: null, setAsOf: () => {}, maxDate: null });

export function DateProvider({ children }: { children: React.ReactNode }) {
  const [asOf, setAsOf] = useState<string | null>(null);
  const [maxDate, setMaxDate] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch(`${API_BASE}/api/health`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { if (alive && d.db_max) setMaxDate(d.db_max); })
      .catch(() => {
        fetch(`${import.meta.env.BASE_URL}data/ui_snapshot.json`)
          .then((r) => (r.ok ? r.json() : Promise.reject()))
          .then((d) => { if (alive && d.as_of) setMaxDate(d.as_of); })
          .catch(() => {});
      });
    return () => { alive = false; };
  }, []);

  return <Ctx.Provider value={{ asOf, setAsOf, maxDate }}>{children}</Ctx.Provider>;
}

export function useDate() {
  return useContext(Ctx);
}
