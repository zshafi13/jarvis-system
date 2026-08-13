# Launcher for the Chatterbox TTS Wyoming service on the Windows GPU box.
#
# Set-Location matters: `python -m wyoming_chatterbox` resolves the package from
# the working directory, and a scheduled task starts in C:\Windows\System32,
# where it is not importable. Without this the service starts fine by hand and
# then fails on every reboot with "No module named wyoming_chatterbox".
Set-Location C:\Wyoming\wyoming-chatterbox
& C:\Wyoming\wyoming-chatterbox\.venv\Scripts\python.exe -m wyoming_chatterbox `
  --uri tcp://0.0.0.0:10201 `
  --speaker-wav C:\Wyoming\jarvisclean2.wav `
  --device cuda `
  --debug *> C:\Wyoming\chatterbox.log
