# FullShelf development guidance

- Keep inventory validation and calculations in `inventory_engine.py`; never ask an LLM to calculate business metrics.
- Keep Gemini access in `gemini_agent.py` and bind tool functions to the active Streamlit session's validated dataset.
- Mapping suggestions may send only column headings and at most three clipped sample rows, only after explicit consent. Never apply a model suggestion without user confirmation, and never let the model validate data or calculate metrics.
- Do not log API keys or expose tracebacks in the interface.
- Run `python -m pytest` from this folder after changing calculations, validation, or agent tools. The live Gemini test is opt-in and must only be run with `FULLSHELF_RUN_LIVE_GEMINI=1`.
- Never put Gemini credentials in tests, source files, commits, or GitHub Actions logs; configure any future hosted secret through the platform's protected secret store.
- Session state is temporary; do not describe it as persistent storage.
- Preserve the stated assumptions: zero safety stock, user-estimated average demand, and no purchase optimiser.
