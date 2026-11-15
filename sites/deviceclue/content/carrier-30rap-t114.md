# What T114 means on a Carrier AquaSnap 30RAP chiller

**T114 means low suction superheat on refrigerant circuit A.** Carrier’s ComfortLink control shuts down that circuit after the low reading persists. **T115** is the corresponding alert for circuit B. These identifiers apply to the AquaSnap 30RAP models covered by Carrier form **30RAP-7T, Rev. A**. [Carrier’s T114 and T115 definitions, page 93](https://www.shareddocs.com/hvac/docs/1005/Public/04/30RAP-7T.pdf#page=93)

## What the chiller measured

Superheat is the difference between the temperature of the suction gas and the refrigerant’s saturation temperature at suction pressure. A small difference triggers this alert. The reading concerns refrigerant inside circuit A. The temperature of the water leaving the chiller is a separate measurement. [Carrier’s explanation of superheat, page 55](https://www.shareddocs.com/hvac/docs/1005/Public/04/30RAP-7T.pdf#page=55)

## Why the same guide gives two alert thresholds

Two pages of the May 2021 manual give different trigger values. Its alert table lists **below 3°F (1.7°C) for five minutes**. Its narrative lists **below 5°F (2.8°C) for five continuous minutes**. Both describe a temperature difference and the same circuit shutdown. Give the service technician the unit model and the form number of its own controls guide so they can verify the threshold for that unit. [Carrier alert table, page 79](https://www.shareddocs.com/hvac/docs/1005/Public/04/30RAP-7T.pdf#page=79) · [Carrier alert description, page 93](https://www.shareddocs.com/hvac/docs/1005/Public/04/30RAP-7T.pdf#page=93)

## If T114 clears and then returns

Carrier lists an automatic restart after the first occurrence that day and a manual restart after subsequent occurrences.

## What to record for the service technician

Record the code, when it appeared, whether circuit A restarted, and any other alerts in the history. The table lists several possible causes, including a faulty expansion valve, a pressure or temperature sensor issue, and excessive refrigerant charge. The code alone cannot identify which applies. Give those observations to the qualified chiller technician before a repeat restart. [Carrier’s restart and probable-cause table](https://www.shareddocs.com/hvac/docs/1005/Public/04/30RAP-7T.pdf#page=79) · [Carrier’s alarm history display](https://www.shareddocs.com/hvac/docs/1005/Public/04/30RAP-7T.pdf#page=113)

A Trane controller reporting a [latched chiller fault](/guides/trane-chiller-latched-fault) uses its own diagnostic descriptions. For a Carrier service call, give the technician the Carrier model and T114 code.
