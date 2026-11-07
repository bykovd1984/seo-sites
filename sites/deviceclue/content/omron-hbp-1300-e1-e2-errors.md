# Omron HBP-1300 E1 and E2 errors: cuff leak or interrupted reading?

If the **HBP-1300** shows **E1**, start where the cuff tube connects to the monitor. If it shows **E2**, check what happened during the measurement. Both can appear when no usable reading was obtained, but the next check is different. Write down the characters before acknowledging the alarm.

## E1: check whether the cuff can hold air

Look for a loose tube connection at the monitor. Seat the connector securely and inspect the cuff for an air leak. Omron specifies a compatible, leak-free **GS CUFF** if the cuff needs replacement. A repeated E1 with a properly connected, known-good cuff is a reason to refer the equipment for assessment.

## E2: check the arm, cuff and timing

| What happened during the attempt | What the operator should check |
| --- | --- |
| The patient talked or moved while the cuff inflated or the unit was measuring | Explain the need for a still, supported arm and a quiet measurement. |
| The cuff shifted or a rolled sleeve was tight above it | Remove the constriction and reapply a correctly sized cuff following the fitting instructions. |
| Inflation kept repeating before E2 appeared | Check for an air leak. Omron also associates E2 with a measurement exceeding its 165-second limit. |

The 165 seconds is the monitor’s fault threshold. If the cuff is causing discomfort, stop the measurement. If a reading is clinically needed and attempts continue to fail, use the facility’s procedure for obtaining a reliable reading. [Omron’s HBP-1300 instructions, error tables on printed pages 28–29](https://device.report/m/71e639df8818fa3e38723fa36a416a1c9cab0ee983b78099df1c144e000ab516_optim.pdf)

## When the display actually says E9 or E40

**E9** is an internal hardware alarm. Omron directs the operator to service. **E40** means the battery is depleted. Follow the HBP-1300 charging or battery-replacement instructions. If several alarms arise, the battery warning can take display priority. Dismissing a message with a button clears the indication; check the underlying condition before the next measurement.

## If the display starts with Er

Look at the nameplate again. On a different professional Omron model, the HEM-907XL, **Er2** points to a deflation problem. Applying that meaning to **E2** on the HBP-1300 would lead you to the wrong check. See the [HEM-907XL error-code table](/guides/omron-hem-907xl-error-codes) if that is the model on the unit.
