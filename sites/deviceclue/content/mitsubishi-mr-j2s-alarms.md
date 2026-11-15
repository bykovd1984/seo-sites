# What do the alarm codes on a Mitsubishi MR-J2S-A mean?

On Mitsubishi Electric's **MELSERVO-J2-Super MR-J2S-□A** servo amplifiers, **AL.16** and **AL.20** point to encoder feedback, AL.50 and AL.51 identify [two kinds of overload](#al-50-and-al-51-describe-different-overloads), and **AL.52** reports a position error. Copy the whole code and the model from the amplifier label. The examples below come from the A-series instructions, including the **MR-J2S-70A**. If your model ends in a different letter, select the matching instructions before interpreting its display. [Mitsubishi Electric A-series alarm list, chapter 10](https://dl.mitsubishielectric.com/dl/fa/document/manual/servo/sh030006/sh030006j.pdf#page=203) · [Mitsubishi Electric J2-Super model and document guide](https://dl.mitsubishielectric.com/dl/fa/document/manual/servo/ib0300061/ib0300061g.pdf)

## Is the display showing the current alarm or an older one?

The amplifier's alarm display can show the current fault or an entry from its history. Mitsubishi illustrates a flashing **AL.33** for an active overvoltage alarm and a separate history entry containing **50** for an earlier overload. If the two differ, give maintenance both entries and say which one was active. Include the axis and what it was doing, such as powering up, lifting a load or slowing at the end of a move. [Mitsubishi Electric alarm-display examples, section 6.4](https://dl.mitsubishielectric.com/dl/fa/document/manual/servo/sh030006/sh030006j.pdf#page=164)

## AL.16 and AL.20 both mention the encoder

The encoder reports motor motion to the amplifier. **AL.16** means communication between them failed. **AL.20** can also cover an error the encoder detected internally. Mitsubishi lists a disconnected encoder connector, a faulty cable and an encoder fault among the possibilities. Record whether the alarm appeared at startup or while the axis was moving. That detail helps the technician decide where to investigate before ordering parts. [Mitsubishi Electric encoder alarm table, printed page 10-8](https://dl.mitsubishielectric.com/dl/fa/document/manual/servo/sh030006/sh030006j.pdf#page=205)

## AL.50 and AL.51 describe different overloads

| Code | What triggered the protection | What to include in the report |
| --- | --- | --- |
| **AL.50** | The load and its duration exceeded the amplifier's overload protection curve. | What load the axis carried and how long it had been cycling. |
| **AL.51** | The drive supplied maximum current continuously for several seconds. Mitsubishi lists a collision as one possible cause. | Where travel stopped and whether anyone observed an obstruction or impact. |

These details can be recorded from the original event. Leave the axis stopped while qualified maintenance investigates. Mitsubishi calls for resolving the cause and allowing about 30 minutes for cooling before returning the drive to operation after either overload. [Mitsubishi Electric overload definitions, section 12.1](https://dl.mitsubishielectric.com/dl/fa/document/manual/servo/sh030006/sh030006j.pdf#page=222) · [Mitsubishi Electric instructions following an alarm, section 10.2.2](https://dl.mitsubishielectric.com/dl/fa/document/manual/servo/sh030006/sh030006j.pdf#page=204)

## AL.52 means the motor fell outside the permitted position difference

The amplifier compares its expected motor position with the actual motor position. **AL.52** means the gap exceeded its allowed value. Mitsubishi documents different limits for different amplifier software revisions, so include the revision if it is already available in the machine records. A disappearing code is insufficient evidence that the fault has been corrected. Mitsubishi warns that clearing an alarm while the run command is still active can make the axis start unexpectedly. Follow the machine's stop and isolation procedure and leave the restart to the person responsible for the equipment. [Mitsubishi Electric AL.52 definition and revision note](https://dl.mitsubishielectric.com/dl/fa/document/manual/servo/sh030006/sh030006j.pdf#page=209) · [Mitsubishi Electric instructions for safe use](https://dl.mitsubishielectric.com/dl/fa/document/manual/servo/ib0300061/ib0300061g.pdf#page=1)
