# Omron HEM-907XL error codes Er1 through Er9

If a professional Omron **HEM-907XL** stops a measurement and shows **Er** followed by a digit, record that digit before you clear the screen. For example, Er1 points to inflation, Er2 to deflation and Er9 to a fault in the main unit. The error itself supplies no blood pressure reading.

## Er1 through Er4: what happened to cuff pressure?

| Display | What happened | First operator check |
| --- | --- | --- |
| Er1 | The cuff failed to build the required pressure in time. | Check that the air tube is seated at the monitor and cuff and that air can pass through it. |
| Er2 | Pressure fell too fast or too slowly, or the cycle took too long. | Check the cuff wrap. Inspect the cuff bladder for a leak according to the equipment instructions. |
| Er3 | Cuff pressure went over the monitor’s limit. | Check the external tubing for a restriction. The code refers to pressure in the cuff. |
| Er4 | Inflation was insufficient for the unit to complete the reading. | If using automatic inflation, verify the P-SET dial is fully in AUTO and the patient can keep still during inflation. |

A useful distinction when logging a fault is *when* it appeared. A cuff that never inflated and one that inflated but failed during release point to different rows of the table. Leave manual inflation settings to the trained operator following the model instructions.

## Er5 through Er8: why no reading appeared

| Display | What the HEM-907XL detected | What to check |
| --- | --- | --- |
| Er5 | The cuff reached its target pressure, but the monitor could not derive the reading. | Check the cuff fit and placement. |
| Er6 | The pulse signal picked up by the cuff was too weak. | Check the cuff wrap as described in the cuff-fitting section. |
| Er7 | The monitor rejected the relationship between its systolic and diastolic measurements. | Check for movement during the measurement. |
| Er8 | The detected pulse rate was outside the range this monitor accepts. | Have the trained operator assess the patient according to the clinical setting’s protocol. |

With Er8, the display alone cannot establish a pulse rate or diagnose a rhythm problem. If a usable reading is needed, follow the facility’s procedure for obtaining one. Omron explains each code in its [HEM-907XL instructions, printed page 27](https://medaval.ie/docs/manuals/Omron-HEM-907XL-Manual.pdf#page=27).

## Er9: when the monitor needs service

Omron identifies Er9 as a main-unit malfunction. Take the unit out of measurement use and refer it to the facility’s equipment service team or Omron support. Record the model, the full code and the stage of measurement. Changing the cuff fit addresses other codes and is unnecessary as a test for Er9.

## If your display says A1, E5 or something else

Read the model number from the unit itself. **HEM-907XL** is the professional monitor covered here. Its table labels the errors **Er1** through **Er9**. If your unit shows **A1** or **E5**, copying the row for Er1 or Er5 can send you to the wrong check. Look up the exact model and display together. [Omron’s model identification page](https://omronhealthcare.com/products/intellisense-professional-digital-blood-pressure-monitor-hem-907xl)

If the nameplate says **HBP-1300** and the display reads **E2**, use the [HBP-1300 cuff and measurement checks](/guides/omron-hbp-1300-e1-e2-errors). That model uses a different code table.
