# How to turn off Do Not Disturb on an Avaya phone

On an Avaya phone connected to **IP Office with the default short codes enabled, dial *09 to switch Do Not Disturb off**. This is not a universal Avaya code: your administrator can change or remove short codes, and phones connected to other Avaya platforms can behave differently.

Check that Do Not Disturb is actually active before changing settings. A silent ringer, call forwarding and a phone disconnected from its system can all make it seem that incoming calls are missing.

## Confirm the system and the symptom

The model name alone is not enough. Ask your telephone administrator whether the phone uses IP Office and whether the standard DND codes are enabled for your extension.

In the [IP Office description of DND](https://documentation.avaya.com/en-us/home/bundle/ip-office/ipofficemanager-12-2/dnd%2C-follow-me-and-forwarding/do-not-disturb-%28dnd%29.html), ordinary calls are sent to voicemail when available, or receive busy treatment. You can still make outgoing calls, and permitted exceptions can behave differently. Being able to call out therefore does not prove DND is off.

## Disable DND with the correct code

When the phone is idle and your system uses the documented defaults:

1. Dial *09 from your extension.
2. Check whether the DND indication clears.
3. Make a test call to the extension from another phone.

[Avaya's IP Office short-code table](https://documentation.avaya.com/bundle/IPOfficeJ100User/page/Short_Codes_DND.html) lists *08 for enabling DND and *09 for disabling it. If *09 is rejected or does nothing, confirm the configured code instead of trying unrelated feature codes.

Avoid using *00 just to solve DND. In that same table, *00 cancels multiple forms of forwarding as well as DND, potentially changing routing you intended to keep.

## A quiet ringer is different

Avaya's [J100 status-icon guide](https://documentation.avaya.com/en-us/home/bundle/ip-office/ipofficej100user/phone-keys-and-display/icons.html) distinguishes DND, unconditional forwarding, a silenced ringer and zero call volume.

| What you observe | What to inspect |
| --- | --- |
| Incoming call appears but is silent | Ringer volume |
| DND indicator remains on | DND setting and administrator policy |
| Forwarding indicator appears | Intended forwarding destination |
| Connection error is displayed | Telephone-system connectivity |

Use the displayed state to choose the next check. Increasing speaker volume during a call is not a test of incoming-call routing.

## Verify direct and group calls separately

Ask a colleague to call your extension directly, then test the number customers normally use if it goes through a group or reception desk. Note whether the phone rings, goes straight to voicemail or receives no call at all.

For a useful support report, record the time, calling number or extension, called destination and displayed status. Different results for direct and group calls help the administrator locate the routing issue without resetting the phone.

## If the setting keeps returning

Do not factory-reset the device to remove DND. Avaya allows administrators to control user settings, and a local reset is not a substitute for checking those rules. Ask the administrator to inspect your extension's DND, forwarding and group configuration. Keep any deliberate forwarding in place until its purpose is understood.
