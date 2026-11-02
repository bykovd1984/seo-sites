# Trane chiller latched fault: what the message means

A **latched fault** on a Trane chiller generally describes a diagnostic that remains active until an appropriate manual reset. It does **not** identify the failed component or say what caused the shutdown. The full diagnostic description, affected circuit and controller model are needed before deciding what action is appropriate.

For example, Trane's RTAA documentation shows a `LATCHED FAULT - MANUAL RESET REQUIRED` message alongside a separate diagnostic description and the operating mode at the time of the fault. Other Trane controllers and chiller families can show different information and use different reset levels.

## Latching is not the cause

Think of the display as answering separate questions:

| Display information | What it tells the service technician |
|---|---|
| Diagnostic description | Which reported condition needs investigation. |
| Latching or non-latching | How that diagnostic persists or clears on the documented controller. |
| Target or circuit | Which part of the system the diagnostic applies to. |
| Severity and operating state | The reported effect and context, such as a shutdown or warning. |
| Active versus history | Whether the controller currently reports the diagnostic or retains it in the history. |

Trane's CGAM documentation illustrates a CH530 diagnostic view with separate description, target, severity and persistence fields. A diagnostic labelled latching should not be treated as a generic code for a particular pressure switch, sensor or refrigerant problem.

## What should an operator record?

Without opening electrical panels or changing the controls, record the exact wording of all active diagnostics, the machine and controller models, the time of the event and any circuit or compressor designation shown. Note the operating state and any events immediately before the alarm if they are available. A clear photograph of the screen can preserve details for the service contractor.

Follow your site's operating and escalation procedures. If there is an immediate equipment or site safety concern, follow the facility emergency process and contact the responsible personnel.

## Should you reset a latched fault?

A reset clears or acknowledges a diagnostic; it does not repair the condition that triggered it. Trane's CGAM documentation warns that resetting active diagnostics **may cause the chiller to resume operation**. For that reason, a qualified and authorized technician should assess the fault, the operating environment and the applicable model-specific procedure before any reset.

Avoid repeated resets to keep the chiller running. They can remove useful context and may allow equipment to restart before the underlying cause has been assessed. This guide deliberately does not give a universal button sequence: RTAA, CH530 and other controllers are not interchangeable.

## What if the fault returns?

Record the new diagnostic and timing, preserve any history available under your site procedures, and contact the responsible service team. An active repeat after a reset can help the technician narrow the investigation, but it still does not prove a particular failed part. Diagnostic history, operating data and model-specific service information must be interpreted together.

The sources below document specific Trane control examples. They do not replace the equipment's own instructions or an on-site assessment.
