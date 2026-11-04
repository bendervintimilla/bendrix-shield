# wAIrrior — Privacy Policy

Last updated: 2026-11-02

wAIrrior is an open-source hackathon project by Juan Vintimilla. This policy covers the
"wAIrrior owner approvals" WhatsApp integration and the wAIrrior demo panel.

## What data is processed

- **The owner's WhatsApp messages to the wAIrrior number** (text and voice notes), only
  while a live demo run is active. Messages from any other number are ignored and their
  media is never downloaded.
- **Voice notes** are downloaded from Meta's media servers, converted to audio on the
  owner's own computer, and transcribed by a Meta model through the wAIrrior gateway. The
  transcript and the understood intent ("rotate the key" / "do not rotate") are shown in
  the owner's local panel.
- **Gateway call metadata** (model name, time, cost, status) is kept in a local database
  on the owner's computer so the cost of each run can be reported.

## What is not done

- No data is sold, shared with advertisers, or used to train models.
- Voice notes are not stored after transcription; the run state lives in memory and is
  cleared with "New run" or when the panel stops.
- Access tokens and app secrets stay in the operating system's keychain and are never
  written to logs or exports.

## Who can use it

The integration only answers the single owner phone number configured on that computer.
There are no user accounts.

## Deleting your data

Message the owner or open an issue at
https://github.com/bendervintimilla/bendrix-shield/issues and any local records tied to
your number will be deleted. You can also remove the WhatsApp conversation from your
own phone at any time.

## Contact

https://github.com/bendervintimilla/bendrix-shield/issues
