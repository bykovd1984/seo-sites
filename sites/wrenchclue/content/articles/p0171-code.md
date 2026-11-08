# P0171 Code: What System Too Lean on Bank 1 Means

P0171 means **System Too Lean (Bank 1)**. The engine computer has been adding fuel because its feedback indicates too much air for the amount of fuel on that bank. The correction met the vehicle's criteria for a lean fault. The question is why: air may be getting in without being accounted for, too little fuel may be reaching the engine, or the information used to calculate the mixture may be inaccurate. The code alone doesn't establish that the sensor reporting the condition has failed.

## Start with the bank and the symptoms

Bank 1 is the cylinder bank containing cylinder No. 1. On an inline engine, there's just one bank. On an engine with two banks, use the cylinder layout for the specific engine to locate No. 1. A label that says **Bank 1** identifies where the computer detected the fuel-control problem. It doesn't mean a part next to cylinder No. 1 is defective.

Check whether **P0174** also appears. That's the lean code for Bank 2, as shown in [Ford's gasoline OBD system summary](https://www.fordservicecontent.com/Ford_Content/catalog/motorcraft/OBD_Operation_Summary_to_Gasoline_MY_2024_2025.pdf). When both banks report lean, something they share deserves attention. When only P0171 appears, comparing the banks' actual fuel corrections is more useful than assuming the second bank is perfectly normal. Two banks can show a similar trend even if only one has set a code.

Some drivers notice a rough idle, hesitation, or a stumble; others first learn of the problem from a steady check engine light. Record when the symptom is strongest. An uneven idle only on the first cold start is a different complaint from a loss of power whenever the car accelerates. If the engine shakes severely and the light starts flashing, pull over safely, shut it off, and arrange assistance. Tell the shop about the [flashing light](flashing-check-engine-light.md) as well as the lean code.

## Read fuel trim as a response to a problem

Fuel trim is the computer's adjustment to the fuel it originally calculated the engine would need. Positive trim means it's commanding more fuel. Short-term trim describes the immediate correction; long-term trim reflects an adjustment learned over time. Neither tells you by itself where extra air entered or whether a fuel supply problem exists.

Consider a split intake hose downstream of the airflow measurement. Air that comes in through the split didn't enter by the expected route. The computer may respond to the resulting lean exhaust indication by adding fuel. In that situation, a sensor reporting lean is providing a useful warning. Replacing it leaves the extra air path open.

Before clearing codes or resetting learned values, save the code list and any freeze frame showing conditions such as temperature, speed, and load. If fuel trims are available, record which bank and operating condition each belongs to. A picture of a trim value with no indication of whether the engine was cold, warm, idling, or under load leaves out much of what makes the number useful.

## How the pattern guides the next test

| Observed pattern | Productive next question |
|---|---|
| Fuel correction is pronounced at idle and decreases as engine speed rises | Is unmetered air entering through an intake hose, seal, or connection? A leak can represent a larger share of total airflow at idle. |
| Correction persists beyond idle, especially when the engine needs more fuel | Does measured fuel delivery meet the requirements for this engine, and does the reported airflow make sense? |
| Bank 1 differs substantially from Bank 2 under the same conditions | What intake path, fuel delivery component, or feedback signal is specific to Bank 1? |
| Rough idle and the lean indication appear at a particular temperature | Can the shop inspect and test at that temperature rather than only after the car has warmed up? |

These comparisons help select a test. They aren't universal pass/fail rules. In a [2004 lean-diagnosis bulletin](https://www.fordservicecontent.com/Ford_Content/pubs/content/~WT/~MUS~LEN/3602/tsb04-17-04.htm), Ford used freeze-frame conditions and compared idle corrections with those at higher engine speed on **listed 2000–2004 Ford, Lincoln, and Mercury vehicles**. The useful lesson is to compare like conditions and preserve the data. The bulletin's procedure and limits don't automatically apply to a newer Ford, much less a Chevrolet, Honda, Nissan, or Toyota.

## What a returning code can reveal

[DENSO describes a Toyota with rough idle and returning lean codes](https://www.densoautoparts.com/reference-dtc-p0171-returns-after-af-sensor-replacement/). Replacing the air/fuel sensor hadn't resolved P0171 and P0174. A cracked hose between the purge valve and intake manifold was letting air in. That's a concrete reason to inspect the air path before condemning a feedback sensor. It isn't a reason to order that particular hose for every Toyota with P0171.

For your own car, ask what finding supports the proposed repair. A leak diagnosis should identify a place where air enters. A fuel delivery diagnosis should include a measurement evaluated against the vehicle's requirements. If the recommendation is an airflow or air/fuel sensor, ask how the technician distinguished an inaccurate signal from an accurate report of a real mixture problem. A name on a scan-tool screen isn't enough to make that distinction.

After the repair, the useful comparison is how Bank 1 responds under the conditions that exposed the problem. For a cold-idle complaint, ask whether the shop checked cold behavior before returning the car. If the lean code returns, bring both reports and note whether the roughness returned with it. That helps distinguish a repair that improved the symptom from one that also restored fuel control.

## Frequently asked questions

**Does lean mean I'm running low on gas?** It describes the relationship between air and fuel during engine operation, not the level on the fuel gauge. A full tank doesn't rule out inadequate fuel delivery, and P0171 doesn't establish a bad fuel pump.

**Can P0171 and P0300 be related?** Yes. A mixture problem may contribute to uneven combustion. Save both codes; the [P0300 misfire pattern](p0300-code.md) and Bank 1 fuel corrections can help the shop decide whether one fault explains both.

**Should I clear P0171 to see if it returns?** Save the diagnostic information first. Clearing memory can remove the conditions and learned corrections that would help a technician find an intermittent leak. A light that stays off just after a reset doesn't verify a repair.
