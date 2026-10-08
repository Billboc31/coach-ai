import { useEffect, useRef, useState } from "react";
import {
  Activity,
  MessageCircle,
  Bike,
  CalendarDays,
  Dumbbell,
  Target,
  Brain,
  Settings,
  MoreHorizontal,
  X,
} from "lucide-react";

const destinations = [
  { id: "overview", label: "Vue d’ensemble", short: "Accueil", icon: Activity },
  { id: "coach", label: "Mon coach", short: "Coach", icon: MessageCircle },
  { id: "activities", label: "Mes activités", short: "Activités", icon: Bike },
  { id: "gym", label: "Musculation", short: "Muscu", icon: Dumbbell },
  {
    id: "planning",
    label: "Mon planning",
    short: "Planning",
    icon: CalendarDays,
  },
  { id: "profile", label: "Objectifs & profil", short: "Profil", icon: Target },
  { id: "memory", label: "Mémoire", short: "Mémoire", icon: Brain },
  { id: "settings", label: "Connexions", short: "Connexions", icon: Settings },
];
const primary = destinations.slice(0, 4);
const secondary = destinations.slice(4);

export function AppNavigation({
  tab,
  onSelect,
}: {
  tab: string;
  onSelect: (tab: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const sheet = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = sheet.current;
    if (open && !dialog?.open) dialog?.showModal();
    if (!open && dialog?.open) dialog.close();
  }, [open]);
  useEffect(() => {
    setOpen(false);
  }, [tab]);
  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);
  function choose(id: string) {
    setOpen(false);
    onSelect(id);
    window.scrollTo({ top: 0, behavior: "auto" });
  }
  const extra = secondary.find((item) => item.id === tab);
  return (
    <>
      <nav className="desktop-nav" aria-label="Navigation principale">
        {destinations.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            aria-current={tab === id ? "page" : undefined}
            className={tab === id ? "active" : ""}
            onClick={() => choose(id)}
          >
            <Icon size={19} />
            <span>{label}</span>
            {tab === id && <span className="nav-dot" />}
          </button>
        ))}
      </nav>
      <nav className="mobile-nav" aria-label="Navigation mobile">
        {primary.map(({ id, label, short, icon: Icon }) => (
          <button
            key={id}
            aria-label={label}
            aria-current={tab === id ? "page" : undefined}
            className={tab === id ? "active" : ""}
            onClick={() => choose(id)}
          >
            <Icon size={21} />
            <span>{short}</span>
          </button>
        ))}
        <button
          className={extra ? "active" : ""}
          aria-label="Plus de pages"
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-controls="mobile-menu"
          onClick={() => setOpen(true)}
        >
          <MoreHorizontal size={21} />
          <span>{extra?.short || "Plus"}</span>
        </button>
      </nav>
      <dialog
        ref={sheet}
        id="mobile-menu"
        className="mobile-menu"
        aria-labelledby="mobile-menu-title"
        onCancel={() => setOpen(false)}
        onClose={() => setOpen(false)}
        onClick={(e) => {
          if (e.target === e.currentTarget) {
            const box = e.currentTarget.getBoundingClientRect();
            if (
              e.clientX < box.left ||
              e.clientX > box.right ||
              e.clientY < box.top ||
              e.clientY > box.bottom
            )
              setOpen(false);
          }
        }}
      >
        <div className="mobile-menu-heading">
          <h2 id="mobile-menu-title">Mon espace</h2>
          <button
            className="outline"
            aria-label="Fermer le menu"
            onClick={() => setOpen(false)}
          >
            <X size={20} />
          </button>
        </div>
        <div className="mobile-menu-links">
          {secondary.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              aria-current={tab === id ? "page" : undefined}
              className={tab === id ? "active" : ""}
              onClick={() => choose(id)}
            >
              <Icon size={22} />
              <span>{label}</span>
            </button>
          ))}
        </div>
      </dialog>
    </>
  );
}
