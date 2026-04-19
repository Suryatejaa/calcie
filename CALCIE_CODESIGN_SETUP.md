# CALCIE Stable Code Signing Setup

This guide fixes the macOS behavior where `CALCIE.app` loses microphone, accessibility, or screen-recording permissions after reinstall.

## Why this happens

Right now CALCIE falls back to **ad-hoc signing** when no stable macOS code-signing identity is available.

With ad-hoc signing:
- the app still runs
- the menu bar shell still works
- but macOS can treat each reinstall like a new app identity for privacy permissions

That is why permissions can disappear after reinstall even when the bundle name looks the same.

## Goal

We want CALCIE to be signed with a stable identity such as:

- `Apple Development: Your Name (TEAMID)`

Once that is in place, reinstalls are much more likely to keep the same macOS privacy trust identity.

## Step 1: Check whether a signing identity already exists

From the Jarvis repo root:

```bash
./scripts/check_calcie_codesign.sh
```

If you already have an `Apple Development` or `Developer ID Application` identity, the script will print it and show the next command to use.

## Step 2: If no identity exists, create one in Xcode

1. Open `Xcode`
2. Go to `Xcode > Settings > Accounts`
3. Sign in with your Apple ID if needed
4. Select your team/account
5. Click `Manage Certificates...`
6. Add an `Apple Development` certificate

After that, re-run:

```bash
./scripts/check_calcie_codesign.sh
```

## Step 3: Tell CALCIE which identity to use

Example:

```bash
export CALCIE_CODESIGN_IDENTITY="Apple Development: Your Name (TEAMID)"
```

You can put that in your shell profile if you want it to persist.

## Step 4: Reinstall CALCIE with stable signing

```bash
./scripts/install_calcie_macos_app.sh
```

If signing worked, the build output should say something like:

```text
Code signing: stable identity (Apple Development: ...)
```

If it still says `Code signing: ad-hoc`, CALCIE is still not using a stable certificate yet.

## Step 5: Re-grant permissions one last time

After the first successful stable-signed install:

1. Open `CALCIE.app`
2. Grant microphone, accessibility, screen recording, and notifications if prompted

That should be the last painful permission reset cycle for normal reinstalls.

## Quick verification

You can confirm available identities with:

```bash
security find-identity -v -p codesigning
```

And you can confirm the build helper sees them with:

```bash
./scripts/check_calcie_codesign.sh
```

## Honest note

This improves permission persistence, but it does not magically make CALCIE fully distributable yet.

CALCIE is still:
- repo-backed
- locally packaged
- not yet a notarized/distributed macOS app

But stable signing is the right next milestone and solves the most annoying current reinstall problem.
