# Short judge journey

Follow [the README](../README.md#step-by-step-setup-guide) first. A fresh clone
contains reference data and public field profiles, but no saved farmer cases or
advisories. All demo passwords are `123`. Ordinary tabs share a session: sign out
between roles. Use English for the exact controls below.

## 1. Ramesh: a question and an officer request

1. Sign in as `ramesh`; select Nalgonda Rice.
2. Review provenance labels: weather is a town observation or model estimate;
   NASA climate is historical; soil is modelled. None is a plot measurement.
3. In Explore a crop cycle enter `Rice`, then select Kharif/Rabi/Zaid. Maize is
   another historical entry, not an optimized rotation recommendation.
4. Enter `How can I keep a simple weekly record of irrigation and rainfall for my rice field?`
   and click Get careful guidance once.
5. Show the actual basis, citations, at most two actions, uncertainty and optional
   clarifying question. If no AI answer was generated, show that honestly. History
   reopens saved responses; do not present a replay as a new call.
6. Open Want professional help? Contact an officer. Enter `Demo Ramesh`,
   telephone `9999999999` (synthetic; never call), optional area `Demo Village`, and
   query `Please review my weekly irrigation and rainfall record plan.`
   Leave the separate officer photo empty. Tick consent and send the request.
7. Verify Waiting for officer. Sign out.

## 2. Rajesh: human guidance and separate publication

1. Sign in as `rajesh`, Refresh officer queue, and find the new Nalgonda Rice case.
2. Card 02 shows the farmer's question, consented contact and saved response.
   Accept AI response records acceptance/approval; Reject AI response opens a
   required replacement. With no AI answer, use Write officer response.
3. For a human response, enter `Keep a notebook of dates, irrigation events, measured rainfall and observations. Mark anything unmeasured as unknown. Bring the record for local review.`
   and Send officer response. This approves follow-up but does not publish.
   Generic Review note is saved with a workflow decision and is farmer-visible.
4. Go to Card 03: Publish a scoped advisory. Insert a cautious draft only fills
   fields; it makes no AI call. Replace its title with `Rice: keep a weekly water record`.
5. Message: `Keep a weekly notebook of irrigation dates, measured rainfall and visible observations for rice fields. Mark unmeasured details as unknown. Discuss field-specific decisions with your local extension officer. This is not evidence of an outbreak.`
6. Select 14 days and Publish to matching farmers. No names, phones or photos
   belong in public text. Show published and shared public cards. Sign out.

## 3. Lakshmi: matching and exclusion

1. Sign in as `lakshmi`, select Krishna Rice, and Refresh advisories.
2. Show the exact new Rice title and its source/expiry.
3. Select Krishna Maize and refresh again: that Rice message must be absent.
4. Optional: Priya sees AP shared public advisories and her AP private queue, not
   Telangana's private farmer cases.

## Honest limits

This is one backend's local exchange simulation. AI is inference with supplied
context, not training or an expert diagnosis. Browser speech is optional. Missing
provider data stays missing; archive data does not replace today's measurements.
The [evaluation](evaluation.md) checks structure and scope, not field accuracy.

Optional **offline** queue rehearsal, after installing requirements, from the root:

```powershell
.\.venv\Scripts\python.exe -m scripts.seed_judge_demo --database backend/data/runtime/agrisathi.sqlite3
```

This adds a labelled synthetic request with **no generated AI answer** through
normal consent/version checks. It does not recreate the team's recorded video.
