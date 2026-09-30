# Manual verification

Start from the [README setup](README.md#step-by-step-setup-guide). Select English
so these control names match. Use only public demo accounts and synthetic data.

1. **Fresh clone:** install the declared dependencies, create `.env`, start backend
   and frontend, and check health. The login page and empty case history should
   load without any original developer folder or database.
2. **Farmer:** sign in as `ramesh / 123`, select Nalgonda Rice, and inspect current
   weather if available, historical NASA climate, modelled soil and source limits.
   The satellite card should be absent. Type Rice in crop-cycle lookup; season
   controls show historical Maize entries. Unsupported crops should abstain.
3. **Guidance:** submit the weekly-record question in the [judge journey](docs/demo-script.md).
   If Gemini succeeds, inspect the actual basis, sources, up to two actions,
   uncertainty and any optional clarification. Reopening history is a saved replay.
   Without a key or on provider failure, verify honest unavailability instead.
4. **Consent:** open Contact an officer. Use `Demo Ramesh`, synthetic telephone
   `9999999999` (never call it), and the sample query. Tick consent and submit.
   Verify Waiting for officer. A question photo alone must not grant officer access.
5. **Officer:** sign out and sign in as `rajesh / 123`; refresh the queue and locate
   the new question. Review note text is saved with a decision and is visible to
   the farmer, not a private memo. Ask for more information; the farmer should
   receive the note and a reply box after refreshing. Submitting the reply returns
   it to review. Verify stale versions are rejected, not silently overwritten.
6. **Response:** accept a genuine saved AI response, or reject it with a required
   officer replacement. With no AI answer, use Write officer response. Check the
   saved history and farmer-visible note. None of these actions publishes.
7. **Sharing:** approve and separately publish the synthetic Rice message in Card
   03. Sign in as Lakshmi; Krishna Rice receives it, Maize excludes that specific
   Rice message. Priya can see AP public receipts and AP private cases, not the
   private Telangana request. Detected contact details must block public posting;
   manually inspect public text for names that pattern checks cannot detect.
8. **Closed cases:** resolve a disposable request and enable Include closed cases
   (read only). History should remain visible and editing disabled.
9. **Accessibility and languages:** test keyboard focus, mobile layout, English/
   Telugu/Hindi strings, and browser voice Type instead fallback. Browser support
   and fluent-language review are separate from automated script checks.
10. **Deployment:** follow [the deployment guide](DEPLOYMENT_GUIDE.md), verify its
    HTTPS health and repeat the journey there. Local tests do not prove a hosted
    provider call, permanent storage or agronomic correctness.

Record actual outcomes. Never treat a configured key, a mocked test, a saved
response, or successful schema validation as a newly verified live AI answer.
