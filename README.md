# listenooga

Python-Tool zum gleichzeitigen Aufzeichnen von Mikrofon- und Systemaudio (z.B. Motorrad-Headset + PC-Output) unter Windows 11.

## Idee

- Spur 1: Mikrofon deines Bluetooth-Headsets
- Spur 2: Systemaudio (das, was du im Headset hörst – Navi, Discord, etc.)

Aufnahme erfolgt mit `sounddevice` (WASAPI-Loopback) und wird als WAV gespeichert.
