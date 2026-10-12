# RhemaCast Operator Guide

Welcome to the RhemaCast Operator Guide. This document provides essential information for church AV operators running the RhemaCast application.

## Audio Configuration

### Cross-Platform Backend Differences

RhemaCast handles audio slightly differently depending on your operating system. When selecting your input microphone in the UI dropdown, you may notice some differences in how devices are named:

#### Windows 11
- **Backend**: RhemaCast defaults to using the **WASAPI** audio backend on Windows.
- **Naming**: You will see clean, human-readable device names directly corresponding to your physical hardware (e.g., `"Realtek High Definition Audio"`, `"Focusrite USB Audio"`, or `"Blue Snowball"`). 
- **Recommendation**: Simply select the microphone that matches your physical receiver.

#### Linux (Debian / Pop!_OS / Ubuntu)
- **Backend**: RhemaCast defaults to the **ALSA** (Advanced Linux Sound Architecture) backend. 
- **Naming**: ALSA device names often include backend-prefixed strings like `(hw:1,0)` or `(hw:0,0)`. For example, your integrated microphone might show up as `"HDA Intel PCH: ALC285 Analog"`.
- **Virtual Devices Filtered**: Linux systems typically expose dozens of "virtual" routing devices (like `lavrate`, `pipewire`, `pulse`, `speex`). To prevent confusion, RhemaCast automatically filters these out of the UI dropdown, leaving only the actual hardware endpoints.
- **Recommendation**: Look for the name of your USB interface or sound card (e.g., `"HDA Intel PCH"`, `"Focusrite Scarlett"`).

### Persistent Selection
Because device names and indexes can shift if USB devices are unplugged and replugged, RhemaCast stores your selection using a persistent ID under the hood. However, if you plug your wireless receiver into a completely different USB port, you may need to re-select it in the UI once.
