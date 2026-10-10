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

export async function modelResponseError(response: Response): Promise<string> {
  if (response.status === 401) return "Reconnecte ton espace.";
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body &&
        typeof body.detail === "string" && body.detail.trim() && body.detail.length <= 1000)
      return body.detail;
  } catch { /* A proxy can return HTML instead of JSON. */ }
  return "Catalogue ChatGPT indisponible. Réessaie ou vérifie la session dans Connexions.";
}

function validateModels(value: unknown): CoachModel[] {
  if (!Array.isArray(value) || value.some(
    (m) => !m || typeof m.id !== "string" || !m.id || typeof m.name !== "string",
  )) throw new Error("Catalogue de modèles indisponible.");
  return value;
}

export function useCoachModels(active: boolean, connectionRevision: number, owner = "local") {
  const scopedKey = owner === "local" ? preferenceKey : preferenceKey + ":" + owner;
  const [models, setModels] = useState<CoachModel[]>([]),
    [model, setSelected] = useState("");
  const [loading, setLoading] = useState(false),
    [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  const selected = useRef("");
  const applyModels = useCallback((value: unknown) => {
    const choices = validateModels(value);
    request.current?.abort();
    setLoading(false);
    setModels(choices);
    const chosen = preferredModel(choices, savedPreference(scopedKey) || selected.current);
    selected.current = chosen;
    setSelected(chosen);
    setError(chosen ? "" : "Aucun modèle disponible pour cette connexion ChatGPT.");
  }, [scopedKey]);
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
        cache: "no-store",
      });
      if (!response.ok) throw new Error(await modelResponseError(response));
      const choices = validateModels(await response.json());
      if (controller.signal.aborted) return;
      applyModels(choices);
    } catch (e) {
      if (!controller.signal.aborted) {
        setModels([]);
        setSelected("");
        selected.current = "";
        setError((e as Error).message);
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [active, connectionRevision, owner, applyModels]);
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
    applyModels,
    modelsLoading: loading,
    modelsError: error,
  };
}
