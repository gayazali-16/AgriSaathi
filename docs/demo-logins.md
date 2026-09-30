# AgriSaathi demo login accounts

Open http://localhost:5174. Each new page launch shows the login page. Enter a username and password, then choose **Sign in**. The account determines its role and district/state scope.

| Name | Username | Password | Workspace and scope |
|---|---|---|---|
| Ramesh | `ramesh` | `123` | Farmer — Nalgonda, Telangana, Rice |
| Suresh | `suresh` | `123` | Farmer — second Nalgonda Rice profile |
| Anil | `anil` | `123` | Farmer — Khammam, Telangana, Maize |
| Lakshmi | `lakshmi` | `123` | Farmer — Krishna, Andhra Pradesh, Rice and Maize fields |
| Rajesh | `rajesh` | `123` | Officer — Telangana |
| Priya | `priya` | `123` | Officer — Andhra Pradesh |

These are public demonstration accounts, mapped to the existing seeded identities. They are enabled only with `DEMO_MODE=true` and do not provide production authentication. Usernames ignore case and surrounding spaces; passwords must match exactly. Sessions use signed HttpOnly cookies. **Sign out** returns to login.

The API login request is `POST /api/v1/session` with JSON `{"username":"ramesh","password":"123"}`. Role and identity are selected by the server.

## Crop cycle inputs

The current historical records contain **Rice** and **Maize** for Nalgonda, Khammam and Krishna, in **Kharif, Rabi and Zaid**. Type `Rice` or `Maize` as the previous crop and select a season shown by the records. Rice shows Maize as the other historically recorded crop, and Maize shows Rice. Other crops correctly return no supported records.

The outputs are historical crop/season candidates. The dataset does not contain validated rotation sequences, suitability rankings or yield predictions; discuss choices with an officer.

## Officer AI review

Below the farmer question, **AI response** shows the saved AI answer, possible causes, actions and uncertainty. **Accept AI response** saves the acceptance and approves follow-up. **Reject AI response** opens a required **Officer response** (10–1,200 characters); **Send officer response** records the rejection and sends the replacement response to that farmer. No public advisory is published by these actions.

If AI did not generate an answer, the panel says so and offers **Write officer response**. The farmer sees officer decisions and responses in **Officer response**; the original AI answer remains in the case history. Closed cases remain read only. Card 03 is still used separately to publish a scoped public advisory, with the existing privacy checks.

Telangana publication automatically shares the public advisory with matching Krishna farmers in Andhra Pradesh. Select Rice or Maize to see the corresponding crop feed. Andhra Pradesh officers can see shared public advisories while private case access remains state scoped. Keep personal details out of public text; pattern checks do not recognize every possible identifier. Follow [the judge journey](demo-script.md). A fresh clone starts with empty case/advisory history.
