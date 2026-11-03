Word error rate needs 3 HAND-TYPED transcripts of what was actually said in your recordings.

1. Pick 3 calls: one English, one Hindi, one Hindi-English mixed (for example call_05, call_01, call_08).
2. Listen to the recording and type exactly what was said into call_XX.txt in this folder.
   Do not copy the script: people skip and change words when they talk, and that is what WER measures.
3. For Hindi speech, type it in the same script the transcription API returns (Whisper normally gives
   Devanagari). Open the call in the app, look at the transcript, and use the same script.
4. Run:  python evaluate.py
