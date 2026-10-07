import argparse
import logging
import secrets

from coach.config import data_dir
from coach.secrets import read_secret, write_secret


def main():
    parser = argparse.ArgumentParser(description="Coach AI : configuration et connexions locales")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("garmin-transfer")
    garmin = sub.add_parser("garmin-login")
    garmin.add_argument("--reauth", action="store_true")
    sync = sub.add_parser("garmin-sync")
    sync.add_argument("--days", type=int, choices=range(1, 31), default=7)
    chatgpt = sub.add_parser("chatgpt-login")
    chatgpt.add_argument("--port", type=int, default=1455)
    sub.add_parser("chatgpt-logout")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        if args.command == "init":
            path = data_dir() / "app.json"
            saved = read_secret(path)
            if not saved:
                saved = {"access_key": secrets.token_urlsafe(32)}
                write_secret(path, saved)
            print("Clé d’accès locale (à saisir dans l’interface, ne pas partager) :")
            print(saved["access_key"])
        elif args.command == "garmin-transfer":
            from coach.transfer import transfer

            transfer()
        elif args.command == "garmin-login":
            from coach.garmin import authenticate

            reused = authenticate(args.reauth)
            print("Connexion Garmin validée. Session " + ("réutilisée." if reused else "créée."))
        elif args.command == "garmin-sync":
            from coach.garmin import sync

            report = sync(args.days)
            print(f"Synchronisé : {report['activities']} activités, {report['days']} jours.")
            print(f"Sources indisponibles : {len(report['errors'])}.")
        elif args.command == "chatgpt-login":
            from coach.chatgpt import sign_in

            sign_in(args.port)
        elif args.command == "chatgpt-logout":
            (data_dir() / "chatgpt.json").unlink(missing_ok=True)
            print("Jetons locaux supprimés. Révoque aussi la connexion dans les réglages ChatGPT.")
    except (KeyboardInterrupt, EOFError):
        print("Interrompu.")
        raise SystemExit(130) from None
    except Exception as exc:
        if args.command in {"garmin-login", "garmin-sync"}:
            from garminconnect import (
                GarminConnectAuthenticationError,
                GarminConnectConnectionError,
                GarminConnectTooManyRequestsError,
            )

            from coach.garmin import safe_failure

            if isinstance(
                exc,
                (
                    GarminConnectAuthenticationError,
                    GarminConnectConnectionError,
                    GarminConnectTooManyRequestsError,
                ),
            ):
                detail = safe_failure(exc)
            else:
                detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        else:
            detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print("Échec : " + detail)
        print("Aucun identifiant ni détail de réponse externe affiché.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
