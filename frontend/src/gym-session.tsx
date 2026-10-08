import { useState } from "react";
import { ArrowLeft, ArrowRight, Check, Plus, Save } from "lucide-react";
import { ExerciseThumbnail } from "./exercise-thumbnail";
import { conventionLabels } from "./exercise-catalogue";
import type { Exercise, SetLog } from "./gym";
import "./gym-session.css";

type Props = {
  exercise: Exercise;
  rows: SetLog[];
  index: number;
  total: number;
  title: string;
  locked: boolean;
  saving: boolean;
  finishing: boolean;
  dirty: boolean;
  error: string;
  conventionChanged: boolean;
  onField: (
    index: number,
    key: keyof SetLog,
    value: number | boolean | null,
  ) => void;
  onExit: () => void;
  onDetails: () => void;
  onPrevious: () => void;
  onNext: () => void;
  onSave: () => void;
  onFinish: () => void;
  onReference: () => void;
  onAdd: () => void;
};
export function GymSession(p: Props) {
  const { exercise: e, rows } = p;
  const [selected, setSelected] = useState(() => {
    const i = rows.findIndex((s) => !s.done);
    return i < 0 ? Math.max(rows.length - 1, 0) : i;
  });
  const [duration, setDuration] = useState(false);
  const i = Math.min(selected, rows.length - 1),
    row = rows[i];
  const completed = rows.filter((s) => s.done).length;
  const valid =
    (row.reps != null || row.seconds != null) &&
    [row.weight, row.reps, row.seconds].every(
      (v) => v == null || (Number.isFinite(v) && v >= 0),
    ) &&
    (row.weight == null || row.weight <= 2000) &&
    (row.reps == null || (Number.isInteger(row.reps) && row.reps <= 1000)) &&
    (row.seconds == null ||
      (Number.isInteger(row.seconds) && row.seconds <= 7200));
  function validate() {
    p.onField(i, "done", !row.done);
    if (!row.done) {
      const next = rows.findIndex((s, n) => n > i && !s.done);
      if (next >= 0) setSelected(next);
    }
  }
  const editable = !p.locked && !p.finishing;
  const hasReference =
    !!e.reference ||
    e.weight != null ||
    !!e.excel_history?.some((h) =>
      h.weights_kg?.some((v: number | null) => v != null),
    );
  return (
    <div className="gym-session">
      <div className="session-topbar">
        <button
          className="outline"
          disabled={p.saving || p.finishing}
          onClick={p.onExit}
        >
          <ArrowLeft size={18} />
          Quitter
        </button>
        <span className="session-save" role="status">
          {p.saving
            ? "Enregistrement…"
            : p.error
              ? "Sauvegarde à vérifier"
              : p.dirty
                ? "Brouillon"
                : "Enregistré"}
        </span>
        <button className="outline" onClick={p.onDetails}>
          Détails
        </button>
      </div>
      <p className="session-program">{p.title}</p>
      <div className="session-progress">
        <span>
          Exercice {p.index + 1} / {p.total}
        </span>
        <span>
          {completed} / {rows.length} séries validées
        </span>
      </div>
      <progress
        value={completed}
        max={rows.length}
        aria-label="Progression de cet exercice"
      />
      <div className="session-exercise">
        <ExerciseThumbnail
          name={e.canonical_name || e.movement_name || e.name}
          thumbnail={e.thumbnail}
          document={e.is_document}
        />
        <h1>{e.canonical_name || e.movement_name || e.name}</h1>
      </div>
      {e.is_document ? (
        <div className="gym-document">
          <p>{e.training_instruction}</p>
          {e.document_links?.map((url) => (
            <a
              className="outline"
              key={url}
              href={url}
              target="_blank"
              rel="noreferrer"
            >
              Ouvrir la fiche ↗
            </a>
          ))}
          {!e.document_links?.length && (
            <p>Lien à vérifier dans le programme d’origine.</p>
          )}
        </div>
      ) : (
        <>
          <div className="session-prescription">
            <span>{e.reps || "Consigne libre"}</span>
            {e.rest && <span>Repos {e.rest}</span>}
            {e.tempo && <span>Tempo {e.tempo}</span>}
          </div>
          {e.training_instruction && (
            <p className="session-instruction">{e.training_instruction}</p>
          )}
        </>
      )}
      {p.error && (
        <div className="error" role="alert">
          <p>{p.error}</p>
          <button className="outline" onClick={p.onDetails}>
            Comparer dans la vue complète
          </button>
        </div>
      )}
      {p.conventionChanged && (
        <p className="gym-warning">
          La variante ou convention a changé. Cette séance garde son repère
          d’origine ; reprise des charges désactivée.
        </p>
      )}
      <div className="session-series" aria-label="Choisir une série">
        {rows.map((s, n) => (
          <button
            key={n}
            className={(n === i ? "selected " : "") + (s.done ? "done" : "")}
            aria-pressed={n === i}
            onClick={() => setSelected(n)}
          >
            Série {n + 1}
            {s.done && <Check size={16} />}
          </button>
        ))}
      </div>
      <section
        className="session-entry card"
        aria-label={`Saisie série ${i + 1}`}
      >
        <h2>Série {i + 1}</h2>
        <div className="session-inputs">
          <label>
            Poids · kg
            <input
              type="number"
              inputMode="decimal"
              min={0}
              max={2000}
              step="0.5"
              value={row.weight ?? ""}
              aria-label={`Poids série ${i + 1}`}
              disabled={!editable}
              onChange={(ev) =>
                p.onField(
                  i,
                  "weight",
                  ev.target.value === "" ? null : Number(ev.target.value),
                )
              }
            />
          </label>
          <label>
            Répétitions
            <input
              type="number"
              inputMode="numeric"
              min={0}
              max={1000}
              step={1}
              value={row.reps ?? ""}
              aria-label={`Répétitions série ${i + 1}`}
              disabled={!editable}
              onChange={(ev) =>
                p.onField(
                  i,
                  "reps",
                  ev.target.value === "" ? null : Number(ev.target.value),
                )
              }
            />
          </label>
        </div>
        {i > 0 && rows[i - 1].weight != null && (
          <button
            className="text-button"
            disabled={!editable}
            onClick={() => p.onField(i, "weight", rows[i - 1].weight)}
          >
            Même poids que la série précédente · {rows[i - 1].weight} kg
          </button>
        )}
        <details
          open={duration || row.seconds != null}
          onToggle={(ev) => setDuration(ev.currentTarget.open)}
          className="session-duration"
        >
          <summary>Durée pour un maintien</summary>
          <label>
            Secondes
            <input
              type="number"
              inputMode="numeric"
              min={0}
              max={7200}
              step={1}
              value={row.seconds ?? ""}
              aria-label={`Secondes série ${i + 1}`}
              disabled={!editable}
              onChange={(ev) =>
                p.onField(
                  i,
                  "seconds",
                  ev.target.value === "" ? null : Number(ev.target.value),
                )
              }
            />
          </label>
        </details>
        <button
          className={
            "primary session-validate " + (row.done ? "validated" : "")
          }
          disabled={!editable || (!row.done && !valid)}
          onClick={validate}
        >
          <Check size={22} />
          {row.done ? "Annuler la validation" : "Valider cette série"}
        </button>
        <p className="session-convention">
          {
            conventionLabels[
              (e.recorded_weight_convention &&
              e.recorded_weight_convention !== "unspecified"
                ? e.recorded_weight_convention
                : e.weight_convention) || "unspecified"
            ]
          }
          {e.recorded_weight_context || e.weight_context
            ? " · " + (e.recorded_weight_context || e.weight_context)
            : ""}
        </p>
        <p className="session-caption">
          Renseigne ce que tu viens de faire. Les champs vides restent inconnus.
        </p>
      </section>
      <div className="session-tools">
        {hasReference && (
          <button
            className="outline"
            disabled={!editable || p.conventionChanged}
            onClick={p.onReference}
          >
            Reprendre mes charges
          </button>
        )}
        <button
          className="outline"
          disabled={!editable || rows.length >= 30}
          onClick={() => {
            p.onAdd();
            setSelected(rows.length);
          }}
        >
          <Plus size={18} />
          Ajouter une série
        </button>
        <button
          className="outline"
          disabled={p.saving || !editable}
          onClick={p.onSave}
        >
          <Save size={18} />
          Enregistrer
        </button>
      </div>
      {(e.notes || e.comments || e.warnings?.length > 0) && (
        <details className="session-notes">
          <summary>Consignes et commentaires</summary>
          <p>{e.notes}</p>
          {e.comments && <p>{e.comments}</p>}
          {e.warnings?.map((w) => (
            <p className="gym-warning" key={w}>
              {w}
            </p>
          ))}
        </details>
      )}
      <div className="session-footer">
        <div>
          <button
            className="outline"
            disabled={!p.index || p.finishing}
            onClick={p.onPrevious}
          >
            <ArrowLeft size={18} />
            Précédent
          </button>
          <button
            className="primary"
            disabled={p.index + 1 >= p.total || p.finishing}
            onClick={p.onNext}
          >
            Exercice suivant
            <ArrowRight size={18} />
          </button>
        </div>
        {p.locked ? (
          <p className="session-finished">Séance terminée et enregistrée.</p>
        ) : (
          <button
            className="text-button"
            disabled={p.saving || p.finishing}
            onClick={p.onFinish}
          >
            Terminer la séance
          </button>
        )}
      </div>
    </div>
  );
}
