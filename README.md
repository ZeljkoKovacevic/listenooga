# listenooga

Python-Tool zum gleichzeitigen Aufzeichnen von Mikrofon- und Systemaudio (z.B. Motorrad-Headset + PC-Output) unter Windows 11.

## Idee

- Spur 1: Mikrofon deines Bluetooth-Headsets
- Spur 2: Systemaudio (das, was du im Headset hörst – Navi, Discord, etc.)

Aufnahme erfolgt mit `sounddevice` (WASAPI-Loopback) und wird als WAV gespeichert.


###
.\whisper-server.exe `
>>   --host 0.0.0.0 `
>>   --port 9080 `
>>   --model "D:\Zeljko\whisper-data\models\ggml-large-v3-turbo-q5_0.bin" `
>>   --language de `
>>   --threads 8 `
>>   --flash-attn `


whisper-server.exe  --host 0.0.0.0  --port 9080  --model "/mnt/d/Zeljko/whisper-data/models/ggml-large-v3-turbo-q5_0.bin"   --language de   --threads 8  --flash-attn 