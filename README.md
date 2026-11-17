# Wildtruhe

Web-App (PWA) für den Wildfleisch-Bestand in der Gefriertruhe.

- Pakete per Diktat oder von Hand erfassen, mit laufender Nummer, Einfrierdatum und automatischem Preis (€/kg bzw. €/Stück)
- Ampel nach Alter: Vorwarnung (Standard 30 Tage vorher), rot ab 6 Monaten
- Abgang: verkauft (Käufer, Preis, bezahlt/offen), verschenkt, selbst verbraucht, entsorgt → Verlauf
- Angebot als WhatsApp-Text teilen, Kalender-Erinnerungen (.ics), Sicherung/Wiederherstellung (JSON), CSV-Export
- Passwortschutz: Daten liegen als `data/wildtruhe.json` im Repo, AES-GCM-verschlüsselt (PBKDF2/SHA-256, 150.000 Runden, gleiches Format wie Hochsitze). Lesen ohne Token, Schreiben mit Fine-grained-Token (Contents: Read and write). Passwort wird einmal pro Gerät abgefragt.
- Abgleich zwischen Geräten: pro Paket gewinnt die jüngste Änderung; offline wird lokal gespeichert und später hochgeladen

Version 1.2.3 · Dateien: index.html, manifest.json, sw.js, icon-192.png, icon-512.png
