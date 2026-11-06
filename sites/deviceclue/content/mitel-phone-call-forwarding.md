# Mitel phone call forwarding: set a destination and turn it off

Call forwarding sends **future incoming calls** to another destination. On the Mitel 5320e and 5330e with MiVoice Office 250, the documented Fwd All control lets you enter that destination. The 5340e uses Forward and menu options. Confirm the platform before applying these steps to a phone with a similar model name.

If someone is already on the line and you want to pass that conversation to a colleague, follow the [Mitel call-transfer procedure](/guides/mitel-phone-transfer-call). Forwarding and transfer solve different tasks.

## Choose when calls should be forwarded

| Intended result | Forwarding condition |
| --- | --- |
| Every incoming call goes elsewhere | All calls |
| Calls move only when you do not answer | No answer |
| Calls move while your extension is busy | Busy |
| Either of those situations redirects calls | Busy or no answer |

Office 250 documents these as separate choices. Decide the condition before entering a destination; an all-calls rule may stop the desk phone ringing when you expected it to ring first. Have the administrator confirm any delay or behavior you rely on.

## Set forwarding on Office 250

For the 5320e/5330e example, press Fwd All and enter the extension when prompted for the forwarding destination. The 5340e uses Forward followed by the appropriate menu choice. Check the displayed destination after entry.

The [Office 250 5320e/5330e/5340e instructions](https://www.mitel.com/sites/default/files/s3_imports/Devices%20and%20Accessories/IP%20Phones/5300%20Series/5300%20IP%20Phones%20Platform%20Specific%20Documents/MiVoice%20250/6.3/en/5320e5330e5340e_UG_6.3.pdf) describe outside-line selection when forwarding to an external number. Use your site's configured dialing method, rather than assuming that a mobile number can be entered exactly as it appears in your contacts.

The older [Office 250 5330 quick reference](https://www.mitel.com/sites/default/files/s3_imports/Devices%20and%20Accessories/IP%20Phones/5300%20Series/5300%20IP%20Phones%20Platform%20Specific%20Documents/MiVoice%20250/6.1/en/Mitel%205330%20IP%20Phone%20QRG_6.1.pdf) calls its control Fwd. Follow the reference matching the actual phone and system.

## Turn manual forwarding off

On the documented 5320e/5330e Office 250 setup, press Fwd All and then lift the handset to cancel manual forwarding. On the 5340e, use Forward followed by FWD OFF. Check the screen and make a test call afterward.

This cancellation concerns manual forwarding. A system-level route, group rule or another service may still affect where calls arrive. If they continue going elsewhere, tell the administrator what you canceled and where the test call ended up.

## Test the destination before leaving

Make a call to your extension from another phone and verify the result at both ends. For conditional forwarding, test the relevant situation: an unanswered desk phone is different from one already busy.

If forwarding to a mobile, check that it is the intended number, that the recipient answers and that your organization allows that destination. Avoid creating a loop where the destination forwards back to your desk.

## When manual settings do not explain the result

Mitel also documents System Forwarding, whose destination is administered centrally; its [Office 250 system-forwarding explanation](https://www.mitel.com/sites/default/files/s3_imports/Devices%20and%20Accessories/Digital%20Phones/8500%20Series/MiVoice%20Office%20250/6.3/en/Mitel%208560%20and%208660%20Phone%20User%20Guide.pdf) distinguishes it from a user-entered destination. That reference is for a different handset family and should not supply button sequences for your 5330e.

Give support the platform, model, forwarding condition, destination and a timed example of a misrouted call. Do not factory-reset the phone to change call routing.
