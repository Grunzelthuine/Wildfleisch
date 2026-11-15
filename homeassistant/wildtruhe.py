#!/usr/bin/env python3
"""Wildtruhe -> Home Assistant
Liest die verschlüsselte data/wildtruhe.json aus dem Repo Grunzelthuine/Wildfleisch,
entschlüsselt sie lokal (Passwort aus /config/secrets.yaml: wildtruhe_passwort)
und gibt eine Zusammenfassung als JSON für einen command_line-Sensor aus.
Namen von Käufern werden NICHT ausgegeben.

Aufruf:
  wildtruhe.py                 -> Zusammenfassung (Sensor)
  wildtruhe.py austragen NR    -> Paket NR als „Selbst verbraucht“ austragen
                                  (braucht wildtruhe_github_token in secrets.yaml)
"""
import base64, calendar, datetime as dt, json, os, re, sys, urllib.error, urllib.request

REPO = "Grunzelthuine/Wildfleisch"
BRANCH = "main"
PFAD = "data/wildtruhe.json"
SECRETS = os.environ.get("WILDTRUHE_SECRETS", "/config/secrets.yaml")


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    sys.exit(0)


def fehler(msg):
    out({"bestand": None, "fehler": msg, "stand": dt.datetime.now().isoformat(timespec="seconds")})


def secret(name, pflicht=True):
    try:
        with open(SECRETS, encoding="utf-8") as f:
            for line in f:
                m = re.match(r'^\s*' + name + r'\s*:\s*(.+?)\s*$', line)
                if m:
                    v = m.group(1)
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                        v = v[1:-1]
                    return v
    except OSError as e:
        fehler(f"secrets.yaml nicht lesbar: {e}")
    if pflicht:
        fehler(f"{name} fehlt in secrets.yaml")
    return None


def passwort():
    return secret("wildtruhe_passwort")


API = f"https://api.github.com/repos/{REPO}/contents/{PFAD}"


def api_holen(token):
    """-> (umschlag, sha) frisch über die GitHub-API (ohne CDN-Cache)"""
    h = {"User-Agent": "wildtruhe-ha", "Accept": "application/vnd.github+json"}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(f"{API}?ref={BRANCH}&t={int(dt.datetime.now().timestamp())}", headers=h)
    with urllib.request.urlopen(req, timeout=20) as r:
        j = json.loads(r.read().decode("utf-8"))
    return json.loads(base64.b64decode(j["content"]).decode("utf-8")), j["sha"]


def holen():
    token = secret("wildtruhe_github_token", pflicht=False)
    if token:
        try:
            return api_holen(token)[0]
        except Exception:
            pass
    urls = [
        f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{PFAD}?t={int(dt.datetime.now().timestamp())}",
        f"https://api.github.com/repos/{REPO}/contents/{PFAD}?ref={BRANCH}",
    ]
    letzter = None
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "wildtruhe-ha", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read().decode("utf-8"))
            if "content" in d and "enc" not in d:  # GitHub-API-Antwort
                d = json.loads(base64.b64decode(d["content"]).decode("utf-8"))
            return d
        except Exception as e:  # nächste Quelle probieren
            letzter = e
    fehler(f"Daten nicht erreichbar: {letzter}")


def entschluesseln(env, pw):
    if not env.get("enc"):
        return env
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        fehler("Python-Paket cryptography fehlt")
    salt = base64.b64decode(env["salt"])
    iv = base64.b64decode(env["iv"])
    data = base64.b64decode(env["data"])
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=int(env.get("iter", 150000))).derive(pw.encode("utf-8"))
    try:
        return json.loads(AESGCM(key).decrypt(iv, data, None).decode("utf-8"))
    except Exception:
        fehler("Passwort falsch (wildtruhe_passwort in secrets.yaml prüfen)")


def verschluesseln(obj, pw):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, iv, it = os.urandom(16), os.urandom(12), 150000
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=it).derive(pw.encode("utf-8"))
    ct = AESGCM(key).encrypt(iv, json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), None)
    b = lambda x: base64.b64encode(x).decode("ascii")
    return {"enc": "aes-gcm-v1", "hinweis": "Verschlüsselte Daten", "iter": it, "salt": b(salt), "iv": b(iv), "data": b(ct)}


def austragen(nr_text):
    try:
        nr = int(str(nr_text).strip().lstrip("#"))
    except ValueError:
        out({"ok": False, "meldung": f"Ungültige Paketnummer: {nr_text}"})
    pw = passwort()
    token = secret("wildtruhe_github_token", pflicht=False)
    if not token:
        out({"ok": False, "meldung": "wildtruhe_github_token fehlt in secrets.yaml"})
    for _ in range(3):
        try:
            env, sha = api_holen(token)
        except Exception as e:
            out({"ok": False, "meldung": f"GitHub nicht erreichbar: {e}"})
        S = entschluesseln(env, pw)
        it = next((i for i in S.get("items", []) if int(i.get("nr") or 0) == nr and i.get("status") == "truhe"), None)
        if not it:
            out({"ok": False, "meldung": f"Paket #{nr:03d} ist nicht (mehr) in der Truhe"})
        it["status"] = "selbst"
        it["abgang"] = {"kaeufer": "", "preis": 0, "datum": dt.date.today().isoformat(), "bezahlt": False, "quelle": "Home Assistant"}
        it["geaendert"] = int(dt.datetime.now().timestamp() * 1000)
        body = json.dumps(verschluesseln(S, pw), ensure_ascii=False, indent=1) + "\n"
        daten = json.dumps({"message": f"Wildtruhe: #{nr:03d} selbst verbraucht (Home Assistant)",
                            "content": base64.b64encode(body.encode("utf-8")).decode("ascii"),
                            "branch": BRANCH, "sha": sha}).encode("utf-8")
        req = urllib.request.Request(API, data=daten, method="PUT", headers={
            "User-Agent": "wildtruhe-ha", "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30):
                pass
            out({"ok": True, "meldung": f"#{nr:03d} {it.get('art')} {it.get('teil')} als selbst verbraucht ausgetragen"})
        except urllib.error.HTTPError as e:
            if e.code in (409, 422):
                continue  # inzwischen geändert -> neu holen
            out({"ok": False, "meldung": "Token ohne Schreibrecht" if e.code in (401, 403) else f"GitHub-Fehler {e.code}"})
        except Exception as e:
            out({"ok": False, "meldung": f"Speichern fehlgeschlagen: {e}"})
    out({"ok": False, "meldung": "Konflikt beim Speichern – bitte nochmal versuchen"})


def plus_monate(d, n):
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def de(d):
    return d.strftime("%d.%m.%Y")


def menge(it, einheit):
    g = int(it.get("gramm") or 0)
    gt = (f"{g/1000:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " kg") if g >= 1000 else (f"{g} g" if g else "")
    if einheit == "stk":
        return f"{int(it.get('anzahl') or 1)} Stk" + (f" · {gt}" if gt else "")
    return gt or "?"


def euro(x):
    return f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    pw = passwort()
    S = entschluesseln(holen(), pw)
    cfg = S.get("cfg") or {}
    monate = int(cfg.get("monate") or 6)
    vorwarn = int(cfg.get("vorwarnTage") if cfg.get("vorwarnTage") is not None else 30)
    preise = S.get("preise") or {}
    heute = dt.date.today()
    items = S.get("items") or []

    truhe, faellig, bald, pakete = [], [], [], []
    for it in items:
        if it.get("status") != "truhe":
            continue
        try:
            d = dt.date.fromisoformat(it["datum"])
        except Exception:
            continue
        frist = plus_monate(d, monate)
        rest = (frist - heute).days
        einheit = ((preise.get(it.get("art")) or {}).get(it.get("teil")) or {}).get("e", "kg")
        nr = int(it.get("nr") or 0)
        txt = f"#{nr:03d} {it.get('art')} {it.get('teil')}, {menge(it, einheit)}"
        e = {"nr": nr, "text": txt, "eingefroren": de(d), "faellig_am": de(frist), "tage": rest,
             "art": it.get("art"), "teil": it.get("teil"), "menge": menge(it, einheit),
             "preis": round(float(it.get("preis") or 0), 2)}
        truhe.append((it, e, frist))
        pakete.append(e)
        if rest <= 0:
            faellig.append(e)
        elif rest <= vorwarn:
            bald.append(e)

    pakete.sort(key=lambda e: (e["tage"], e["nr"]))
    faellig.sort(key=lambda e: (e["tage"], e["nr"]))
    bald.sort(key=lambda e: (e["tage"], e["nr"]))

    kg = sum(int(it.get("gramm") or 0) for it, _, _ in truhe) / 1000
    wert = sum(float(it.get("preis") or 0) for it, _, _ in truhe)

    nach_teil = {}
    for it, e, _ in truhe:
        k = f"{it.get('art')} · {it.get('teil')}"
        n = nach_teil.setdefault(k, {"pakete": 0, "gramm": 0})
        n["pakete"] += 1
        n["gramm"] += int(it.get("gramm") or 0)
    nach_teil_liste = [f"{k}: {v['pakete']} Paket(e)" + (f" · {v['gramm']/1000:.1f} kg".replace(".", ",") if v['gramm'] else "") for k, v in sorted(nach_teil.items())]

    nachste = pakete[0] if pakete else None
    jahr = str(heute.year)
    verkauft = [it for it in items if it.get("status") == "verkauft"]
    offen = sum(float((it.get("abgang") or {}).get("preis") or 0) for it in verkauft if not (it.get("abgang") or {}).get("bezahlt"))
    jahr_summe = sum(float((it.get("abgang") or {}).get("preis") or 0) for it in verkauft if str((it.get("abgang") or {}).get("datum", "")).startswith(jahr))

    out({
        "bestand": len(truhe),
        "kg": round(kg, 2),
        "wert": round(wert, 2),
        "wert_text": euro(wert),
        "faellig": len(faellig),
        "bald": len(bald),
        "faellig_nr": ",".join(str(e["nr"]) for e in sorted(faellig, key=lambda e: e["nr"])),
        "faellig_liste": faellig,
        "bald_liste": bald,
        "naechste": (f"{nachste['text']} – fällig {nachste['faellig_am']}" if nachste else None),
        "naechste_datum": (dt.datetime.strptime(nachste["faellig_am"], "%d.%m.%Y").date().isoformat() if nachste else None),
        "nach_teil": nach_teil_liste,
        "pakete": pakete,
        "offen_betrag": round(offen, 2),
        "verkauft_jahr": round(jahr_summe, 2),
        "monate": monate,
        "vorwarn_tage": vorwarn,
        "stand": dt.datetime.now().isoformat(timespec="seconds"),
        "fehler": None,
    })


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "austragen":
        austragen(sys.argv[2])
    main()
