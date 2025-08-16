from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import List, Optional, Callable, TypeVar
from functools import wraps

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

try:
    # Python 3.9+: zona oraria IANA senza dipendenze esterne
    from zoneinfo import ZoneInfo
except ImportError:
    # Per Python <3.9 servirebbe 'pip install backports.zoneinfo'
    from backports.zoneinfo import ZoneInfo  # type: ignore

# === CONFIG ===============================================================


OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",  # creare/modificare eventi
    "https://www.googleapis.com/auth/gmail.send",       # inviare email
]
CREDENTIALS_FILE = os.environ.get("GOOGLE_CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE = os.environ.get("GOOGLE_TOKEN_FILE", "token.json")

CALENDAR_SUMMARY = "Scadenze_TiL"
DEFAULT_TZ = ZoneInfo("Europe/Rome")

DEFAULT_RECIPIENTS = [
    "destinatario1@example.com",
    "destinatario2@example.com",
]

# ========================================================================

T = TypeVar("T")

def _retry_api(max_tries: int = 3, base_delay: float = 0.6) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Retry esponenziale su alcune HttpError (429/5xx)."""
    def deco(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            tries = 0
            while True:
                try:
                    return fn(*args, **kwargs)
                except HttpError as e:
                    status = getattr(e, "status_code", None) or getattr(e, "resp", None) and getattr(e.resp, "status", None)
                    if status in (429, 500, 502, 503, 504) and tries < max_tries - 1:
                        time.sleep(base_delay * (2 ** tries))
                        tries += 1
                        continue
                    raise
        return wrapper
    return deco


def _get_credentials() -> Credentials:
    """
    OAuth2 flow come nei quickstart ufficiali.
    Crea/usa token.json per memorizzare access/refresh token.
    """
    creds: Optional[Credentials] = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, OAUTH_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"File credenziali Google non trovato: {CREDENTIALS_FILE}. "
                    f"Scaricalo dalla Cloud Console e/o imposta GOOGLE_CREDENTIALS_FILE."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, OAUTH_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return creds


def _build_calendar_service(creds: Credentials):
    return build("calendar", "v3", credentials=creds)


def _build_gmail_service(creds: Credentials):
    return build("gmail", "v1", credentials=creds)


def _get_calendar_id_by_summary(service, summary: str) -> Optional[str]:
    """
    Cerca tra i calendarList dell’utente un calendario con quel 'summary'
    e restituisce il suo 'id'. Se non trovato, None.
    """
    page_token = None
    while True:
        resp = service.calendarList().list(pageToken=page_token, maxResults=250).execute()
        for cal in resp.get("items", []):
            if cal.get("summary") == summary:
                return cal.get("id")
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return None


def _ensure_calendar(service, summary: str, time_zone: str = "Europe/Rome") -> str:
    """
    Ritorna l'ID del calendario con quel summary; se non esiste lo crea.
    """
    cal_id = _get_calendar_id_by_summary(service, summary)
    if cal_id:
        return cal_id
    body = {"summary": summary, "timeZone": time_zone}
    created = service.calendars().insert(body=body).execute()
    # assicura che compaia nella lista dell’utente
    service.calendarList().insert(calendarId=created["id"]).execute()
    return created["id"]


@dataclass
class Reminder:
    method: str  # "email" oppure "popup"
    minutes: int  # 0..40320 (4 settimane)


@_retry_api()
def add_deadline(
    title: str,
    due_at: datetime,
    duration_minutes: int = 30,
    reminders: Optional[List[Reminder]] = None,
    description: Optional[str] = None,
) -> str:
    """
    Inserisce una scadenza nel calendario 'Scadenze_TiL' con reminder personalizzati.

    Args:
        title: Titolo dell’evento.
        due_at: datetime con timezone (Europe/Rome di default se naive).
        duration_minutes: durata dell’evento (default 30').
        reminders: lista di Reminder (max 5). Se None, usa i default del calendario.
        description: testo descrittivo opzionale.

    Returns:
        eventId creato su Google Calendar.
    """
    creds = _get_credentials()
    cal = _build_calendar_service(creds)

    cal_id = _ensure_calendar(cal, CALENDAR_SUMMARY, "Europe/Rome")

    # Garanzia timezone
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=DEFAULT_TZ)
    start_dt = due_at.astimezone(DEFAULT_TZ)
    end_dt = (due_at + timedelta(minutes=duration_minutes)).astimezone(DEFAULT_TZ)

    body = {
        "summary": title,
        "description": description or "",
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Europe/Rome"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "Europe/Rome"},
    }

    if reminders is not None:
        body["reminders"] = {
            "useDefault": False,
            "overrides": [{"method": r.method, "minutes": int(r.minutes)} for r in reminders][:5],
        }

    try:
        event = cal.events().insert(calendarId=cal_id, body=body).execute()
        return event["id"]
    except HttpError as e:
        raise RuntimeError(f"Errore Calendar API (add_deadline): {e}") from e


@_retry_api()
def update_deadline(
    event_id: str,
    new_title: Optional[str] = None,
    new_due_at: Optional[datetime] = None,
    new_duration_minutes: Optional[int] = None,
    new_description: Optional[str] = None,
    reminders: Optional[List[Reminder]] = None,
) -> str:
    """
    Aggiorna un evento esistente (se esiste). Ritorna l'event_id.
    """
    creds = _get_credentials()
    cal = _build_calendar_service(creds)
    cal_id = _ensure_calendar(cal, CALENDAR_SUMMARY, "Europe/Rome")

    ev = cal.events().get(calendarId=cal_id, eventId=event_id).execute()

    if new_title is not None:
        ev["summary"] = new_title
    if new_description is not None:
        ev["description"] = new_description

    if new_due_at is not None or new_duration_minutes is not None:
        if new_due_at is None:
            # usa la vecchia start
            old_start = ev["start"]["dateTime"]
            dt = datetime.fromisoformat(old_start.replace("Z", "+00:00"))
        else:
            dt = new_due_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=DEFAULT_TZ)
        start_dt = dt.astimezone(DEFAULT_TZ)

        duration = new_duration_minutes if new_duration_minutes is not None else 30
        end_dt = (start_dt + timedelta(minutes=duration))

        ev["start"] = {"dateTime": start_dt.isoformat(), "timeZone": "Europe/Rome"}
        ev["end"] = {"dateTime": end_dt.isoformat(), "timeZone": "Europe/Rome"}

    if reminders is not None:
        ev["reminders"] = {
            "useDefault": False,
            "overrides": [{"method": r.method, "minutes": int(r.minutes)} for r in reminders][:5],
        }

    cal.events().update(calendarId=cal_id, eventId=event_id, body=ev).execute()
    return event_id


@_retry_api()
def send_message(
    subject: str,
    body_text: str,
    recipients: Optional[List[str]] = None,
    from_address: Optional[str] = None,
) -> str:
    """
    Spedisce un’email in testo semplice ai destinatari indicati (default i due fissi).

    Args:
        subject: Oggetto del messaggio.
        body_text: Corpo del messaggio (plain text).
        recipients: Lista destinatari; default usa quelli preconfigurati.
        from_address: opzionale; se omesso Gmail userà l’account autenticato ("me").

    Returns:
        messageId Gmail.
    """
    creds = _get_credentials()
    gmail = _build_gmail_service(creds)

    tos = recipients or DEFAULT_RECIPIENTS
    if not tos:
        raise ValueError("Nessun destinatario specificato e DEFAULT_RECIPIENTS vuoto")

    msg = EmailMessage()
    msg.set_content(body_text)
    msg["To"] = ", ".join(tos)
    if from_address:
        msg["From"] = from_address
    msg["Subject"] = subject

    # Base64 URL-safe come da guida "Sending Email"
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    body = {"raw": raw}

    try:
        sent = gmail.users().messages().send(userId="me", body=body).execute()
        return sent["id"]
    except HttpError as e:
        raise RuntimeError(f"Errore Gmail API (send_message): {e}") from e


@_retry_api()
def elimina_evento(eventId: str, calendar_id: Optional[str] = None) -> None:
    """
    Cancella un evento. Se calendar_id è None, usa/crea il calendario 'Scadenze_TiL'.
    Firma retro-compatibile con il tuo codice (che talvolta passa 1 solo argomento).
    """
    creds = _get_credentials()
    service = build("calendar", "v3", credentials=creds)
    cal_id = calendar_id or _ensure_calendar(service, CALENDAR_SUMMARY, "Europe/Rome")
    service.events().delete(calendarId=cal_id, eventId=eventId).execute()
    print(f"Evento {eventId} eliminato con successo.")

# === Utility di ricerca/lista/cleanup =====================================

def _iso_with_tz(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=DEFAULT_TZ)
    return dt.astimezone(DEFAULT_TZ).isoformat()


@_retry_api()
def list_deadlines(
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
    q: Optional[str] = None,
    page_size: int = 250,
) -> List[dict]:
    """
    Restituisce una lista di eventi dal calendario 'Scadenze_TiL'.

    Args:
        from_dt: filtro iniziale (inclusivo). Se naive, assume Europe/Rome.
        to_dt: filtro finale (esclusivo). Se naive, assume Europe/Rome.
        q: testo di ricerca full-text lato Google (facoltativo).
        page_size: eventi per pagina (Google accetta fino a ~250).

    Returns:
        Lista di dict normalizzati: {id, summary, start, end, htmlLink, raw}
        Dove start/end sono stringhe ISO (dateTime o date).
    """
    creds = _get_credentials()
    cal = _build_calendar_service(creds)
    cal_id = _ensure_calendar(cal, CALENDAR_SUMMARY, "Europe/Rome")

    params = {
        "calendarId": cal_id,
        "singleEvents": True,             # espande ricorrenze
        "orderBy": "startTime",
        "maxResults": int(page_size),
    }
    tmin = _iso_with_tz(from_dt)
    tmax = _iso_with_tz(to_dt)
    if tmin: params["timeMin"] = tmin
    if tmax: params["timeMax"] = tmax
    if q:    params["q"] = q

    items: List[dict] = []
    page_token = None
    while True:
        if page_token:
            params["pageToken"] = page_token
        resp = cal.events().list(**params).execute()
        for ev in resp.get("items", []):
            start = ev.get("start", {})
            end   = ev.get("end", {})
            items.append({
                "id": ev.get("id"),
                "summary": ev.get("summary", ""),
                "start": start.get("dateTime") or start.get("date"),
                "end": end.get("dateTime") or end.get("date"),
                "htmlLink": ev.get("htmlLink"),
                "raw": ev,  # oggetto completo in caso serva
            })
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return items


@_retry_api()
def find_deadlines_by_summary(
    prefix: str,
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
    case_insensitive: bool = True,
    limit: Optional[int] = None,
) -> List[dict]:
    """
    Trova eventi il cui SUMMARY inizia con 'prefix'.

    Nota: usa 'q=prefix' per restringere lato Google, poi filtra lato client
    con startswith (eventuali match interni non desiderati vengono esclusi).

    Args:
        prefix: prefisso del titolo (es. '123/2025 - ').
        from_dt, to_dt: finestra temporale (facoltativa).
        case_insensitive: confronto case-insensitive.
        limit: massimo numero di risultati (None = tutti).

    Returns:
        Lista di eventi (stesso formato di list_deadlines).
    """
    raw = list_deadlines(from_dt=from_dt, to_dt=to_dt, q=prefix)
    if case_insensitive:
        p = prefix.lower()
        out = [e for e in raw if (e.get("summary") or "").lower().startswith(p)]
    else:
        out = [e for e in raw if (e.get("summary") or "").startswith(prefix)]
    if limit is not None:
        out = out[: int(limit)]
    return out


@_retry_api()
def delete_deadlines_by_prefix(
    prefix: str,
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
    dry_run: bool = True,
) -> List[str]:
    """
    Cancella tutti gli eventi il cui summary inizia con 'prefix'.
    Per sicurezza default = dry_run (non cancella, ma restituisce gli IDs).

    Args:
        prefix: prefisso del titolo da cancellare.
        from_dt, to_dt: finestra temporale (facoltativa).
        dry_run: se True non cancella, ritorna solo la lista degli ID.

    Returns:
        Lista degli eventId coinvolti.
    """
    creds = _get_credentials()
    cal = _build_calendar_service(creds)
    cal_id = _ensure_calendar(cal, CALENDAR_SUMMARY, "Europe/Rome")

    matches = find_deadlines_by_summary(prefix, from_dt=from_dt, to_dt=to_dt)
    ids = [m["id"] for m in matches if m.get("id")]
    if dry_run:
        return ids

    for eid in ids:
        try:
            cal.events().delete(calendarId=cal_id, eventId=eid).execute()
        except HttpError as e:
            # Continuiamo comunque; al chiamante rimane la lista tentata
            print(f"Errore in delete {eid}: {e}")
    return ids


