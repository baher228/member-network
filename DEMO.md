# Member Network — 3-minute demo script

Before going on stage: open `/members` → **Reset demo** (restores the seeded starting state; real/non-seed rows are kept). Use a fresh name for the new member each run (e.g. "Sam Demo 2").

| Time | Screen | Do | Say |
| --- | --- | --- | --- |
| 0:00–0:10 | `/members` | Point at the graph and the **Isolated** count | "Community leads know members as phone numbers. Here are 80 (synthetic, labelled *Demo data*) members — a few nobody has connected with." |
| 0:10–0:40 | `/join` | Name "Sam Demo", builds "voice agents for call centres", wants "help with payments and billing infrastructure", speaker topic "voice AI", tick both consents → **Join** | "Opt-in, with explicit consent for intros and for being suggested as a speaker. Stored in Supabase Postgres with row-level security." |
| 0:40–1:05 | `/for-you` (now viewing as Sam) | Show the top cards: content score, CF bar at 0, reason "X builds … you want help with …" | "New member, no likes yet, so it's all content similarity — sentence embeddings of what you want versus what others build." |
| 1:05–1:30 | `/for-you` | **Like** two people, **Pass** one. Point at the interaction count, the CF weight rising, and a reason like "You liked A and B; N people who liked them also connected with C" | "Now collaborative filtering kicks in: people who liked who you liked also liked C. The blend shifts toward CF as you interact — every suggestion says why." |
| 1:30–2:05 | `/intros` | **Run weekly intros now**. Show the run log (drafted / failed / skipped), open one intro's reasons, **Accept** one | "Once a week — also on a scheduler — one intro per consenting member. The LLM only writes the message from these structured reasons. If the LLM fails, you see *failed* with the error, never made-up text. Accepting feeds back into the model." |
| 2:05–2:35 | `/speakers` | Click **voice agents** (public builders on). Scroll to a *PUBLIC LONDON BUILDER* card and click a GitHub/Devpost/HN link | "Need a speaker? Consenting members first, then public builders with evidence links — each marked live or cached." |
| 2:35–3:00 | `/eval` | Point at the two tables | "Honest numbers: 20% held-out likes, 5 splits. Hybrid wins, but CF alone is no better than popularity on this data, and the hybrid's lead over content is about one standard deviation. Synthetic data, so it's a sanity check, not a claim." |

Fallbacks: if the LLM badge says unavailable or intros show *failed*, say so — it's the designed behaviour. If an external speaker source shows *failed*, the others still render. Threads (`/threads` → Load sample → Analyse) is a spare 20s if time allows.
