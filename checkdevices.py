import soundcard as sc

# Zeigt alle Loopback-fähigen Geräte
for m in sc.all_microphones(include_loopback=True):
    print(m.id, m.name)