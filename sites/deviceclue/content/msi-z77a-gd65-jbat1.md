# What does JBAT1 do on the MSI Z77A-GD65?

**JBAT1** is the clear-CMOS jumper on the **MSI Z77A-GD65, MS-7751 v2.x**. The battery-backed CMOS memory holds the board's saved configuration. Bridging the JBAT1 pins with the computer off clears that configuration. [MSI Z77A-GD65 manual, page 1-34, readable copy](https://www.manualsdir.com/manuals/467073/msi-z77a-gd65.html?page=44)

## Is a cap missing from JBAT1?

For everyday use the pins stay **open**, which MSI labels **Keep Data**. An empty pair of pins at JBAT1 is normal. A cap bridging the two pins puts this board in its **Clear Data** position. [MSI jumper diagram, page 1-34](https://www.manualsdir.com/manuals/467073/msi-z77a-gd65.html?page=44)

## When would you clear CMOS?

If the board stopped starting immediately after a BIOS setting change, clearing CMOS lets you start again with the board's defaults. A normal restart keeps your saved settings. JBAT1 affects motherboard setup. It does not install a different BIOS version or erase files from your drives. If you can still enter setup, note settings your system needs, especially the boot drive and SATA controller mode, before clearing anything. [MSI Z77A-GD65 manual, chapters 1 and 2 (ZIP)](https://download-2.msi.com/archive/mnu_exe/E7751v2.2.zip)

## Follow the jumper diagram for this board

1. Confirm the board marking and match **JBAT1** to the diagram in the Z77A-GD65 manual. The connector reference lists it on page **1-34**. Other MSI boards have their own jumper and power instructions.
2. Shut the computer down, switch off the power supply and unplug its power cord before working inside. With the system off, briefly connect the two **JBAT1** pins as shown under **Clear Data**. MSI warns that clearing CMOS with this board running can damage it.
3. Remove the jumper cap so both pins are open again. Close the case, reconnect power and start the PC. [MSI jumper diagram, page 1-34](https://www.manualsdir.com/manuals/467073/msi-z77a-gd65.html?page=44) · [MSI assembly precautions, page 1-3 (ZIP)](https://download-2.msi.com/archive/mnu_exe/E7751v2.2.zip)

## What to check on the first boot

Press **Delete** at the startup prompt to enter **Click BIOS II**. Check the date and time in **Settings → System Status** and the intended drive under **Settings → Boot → Boot Option Priorities**. MSI calls out one storage setting in particular. If the operating system was installed with **SATA Mode** set to **AHCI**, restore **AHCI** after the reset. [MSI Z77A-GD65 BIOS setup, chapter 2, readable copy](https://manuals.plus/m/aa7c8921577854a05fbc6d401ed43683e44d7ec321ec5bc80ac5ee4f6adc2b3f)
