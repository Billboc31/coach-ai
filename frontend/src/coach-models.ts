import { useCallback, useEffect, useRef, useState } from "react";

export type CoachModel = { id: string; name: string };
const preferenceKey = "coach-preferred-model";
export function preferredModel(choices: CoachModel[], previous = "") {
  if (choices.some((m) => m.id === previous)) return previous;
  return (
    choices.find((m) => /(^|[^a-z])sol([^a-z]|$)/i.test(m.id + " " + m.name))
      ?.id ||
    choices[0]?.id ||
    ""
  );
}
function savedPreference(key: string) {
  try {
    return localStorage.getItem(key) || "";
  } catch {
    return "";
  }
}

export function useCoachModels(active: boolean, connectionRevision: number, owner = "local") {
  const scopedKey = owner === "local" ? preferenceKey : preferenceKey + ":" + owner;
  const [models, setModels] = useState<CoachModel[]>([]),
    [model, setSelected] = useState("");
  const [loading, setLoading] = useState(false),
    [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  const selected = useRef("");
  const refresh = useCallback(async () => {
    if (!active) return;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/models", {
        signal: controller.signal,
      });
      if (!response.ok)
        throw new Error(
          response.status === 401
            ? "Reconnecte ton espace."
            : "Impossible de charger les modèles. Vérifie la connexion ChatGPT puis réessaie.",
        );
      const choices: CoachModel[] = await response.json();
      if (
        !Array.isArray(choices) ||
        choices.some(
          (m) => !m || typeof m.id !== "string" || typeof m.name !== "string",
        )
      )
        throw new Error("Catalogue de modèles indisponible.");
      if (controller.signal.aborted) return;
      setModels(choices);
      const chosen = preferredModel(
        choices,
        savedPreference(scopedKey) || selected.current,
      );
      selected.current = chosen;
      setSelected(chosen);
      if (!chosen)
        setError("Aucun modèle disponible pour cette connexion ChatGPT.");
    } catch (e) {
      if (!controller.signal.aborted) setError((e as Error).message);
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [active, connectionRevision, owner]);
  useEffect(()=>{selected.current="";setSelected("");},[owner]);
  useEffect(() => {
    if (active) void refresh();
    else {
      request.current?.abort();
      setModels([]);
      setSelected("");
      selected.current = "";
      setLoading(false);
      setError("");
    }
    return () => request.current?.abort();
  }, [active, refresh]);
  function setModel(id: string) {
    if (!models.some((m) => m.id === id)) return;
    selected.current = id;
    setSelected(id);
    try {
      localStorage.setItem(scopedKey, id);
    } catch {
      /* A blocked storage must not stop the chat. */
    }
  }
  return {
    models,
    model,
    setModel,
    loadModels: refresh,
    modelsLoading: loading,
    modelsError: error,
  };
}
