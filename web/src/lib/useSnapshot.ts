import { useEffect, useState } from "react";
import type { Snapshot } from "./types";

interface State {
  data: Snapshot | null;
  error: string | null;
  loading: boolean;
}

/** Loads the model-generated snapshot (scripts/build_ui_snapshot.py -> public/data). */
export function useSnapshot(): State {
  const [state, setState] = useState<State>({ data: null, error: null, loading: true });

  useEffect(() => {
    let alive = true;
    fetch(`${import.meta.env.BASE_URL}data/ui_snapshot.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`snapshot ${r.status}`);
        return r.json();
      })
      .then((data: Snapshot) => alive && setState({ data, error: null, loading: false }))
      .catch((e: Error) => alive && setState({ data: null, error: e.message, loading: false }));
    return () => {
      alive = false;
    };
  }, []);

  return state;
}
