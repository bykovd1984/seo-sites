# Canon iR3300 error codes and what to check first

On the **Canon imageRUNNER 3300 (iR3300)**, first check where the code appears. An **E-code** on the service-call screen describes a fault detected by the copier. A **number starting with #** in the job log explains [why a particular job ended](#what-a-number-starting-with-means). A paper-jam diagram gives instructions for the paper path shown on screen. Photograph the full display, including any digits after a hyphen, before changing anything. [Canon’s iR3300/iR2800/iR2200 Reference Guide](https://files.canon-europe.com/files/soft03-48735/Manual/iR2200_2800_3300_Reference_Guide_EN.pdf)

## What E000, E001, E002 and E003 mean

These four codes concern the **fixing unit**, the part of the copier that heats the toner to bond it to the paper. The difference is what the copier measured. The same code can have several causes, so keep the full code for the service technician. These definitions apply to the original iR3300 family. A machine labelled **imageRUNNER ADVANCE C3330** belongs to a different family.

| Code in Canon’s service table | What the copier detected |
| --- | --- |
| E000 | The fixing temperature failed to rise as expected just after power-on. |
| E001 | A temperature sensor in the fixing unit registered an excessively high reading. |
| E002 | The fixing unit warmed up too slowly to reach a required temperature in time. |
| E003 | The measured fixing temperature dropped below its required level. |
| E007 | The copier detected a problem with the rotation of the fixing film. |
| E010 | The copier detected a problem with the rotation of its main motor. |

For example, **E001** identifies the temperature reading that triggered the stop. The technician still has to determine whether the unit overheated or a fault in the sensing or control circuit produced that reading. Clearing the error in a service menu would erase the warning without establishing the cause. [Canon’s iR2200/iR2800/iR3300 Service Handbook, chapter 6, archived copy](https://www.manualslib.com/manual/834914/Canon-Ir2200.html?page=234#manual)

## If the copier smokes or makes an unusual noise

If the copier is smoking, giving off an unusual smell or making an abnormal noise, switch it off at the main power switch, unplug it if safe to do so and contact service. Leave it off. [Canon’s Reference Guide, safety precautions](https://files.canon-europe.com/files/soft03-48735/Manual/iR2200_2800_3300_Reference_Guide_EN.pdf#page=19)

## What to do at the service-call screen

For an ordinary service-call message without those signs, Canon gives this sequence for the iR3300 family. Use the **main power switch** on the copier. The power key on the control panel is a separate control. If other users have reserved print jobs, let them know that switching the main power off erases those jobs.

1. Write down the full error code. Note whether it appeared at startup, when making a copy or as a sheet reached the exit.
2. Turn the main power off, wait **at least three seconds**, then switch it on again.
3. If the copier still cannot operate normally, turn the main power off, unplug it and contact the service representative. Give them the model, the full code and what the copier was doing when it stopped. [Canon’s service-call procedure, printed page 6-33, archived copy](https://www.manualslib.com/manual/1063919/Canon-Ir-3300.html?page=245)

## What a number starting with # means

On this model, open **System Monitor**, choose **Log**, then open **Details** for the affected job. Canon calls the number there an **End Code**. Its reference guide gives these examples.

| End Code | What happened | Next step |
| --- | --- | --- |
| #99 | A copy or print job was interrupted. | Try that job again. |
| #816 | The print job would exceed the print allowance for its Department ID. | Ask the person who manages the copier to check the department’s limit. |
| #852 | The main power was switched off while a job was being processed. | Once the copier is on and ready, submit the job again if needed. |

For instance, if colleagues can still print and your job shows **#816**, give the copier administrator that code and your department name. They can check the allowance while everyone else keeps using the machine. [Canon’s iR3300 job-code table, printed page 6-30, archived copy](https://www.manualslib.com/manual/1063919/Canon-Ir-3300.html?page=242)
