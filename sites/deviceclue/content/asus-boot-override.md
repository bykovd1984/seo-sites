# How ASUS Boot Override works and when to use it

**Boot Override** starts the computer from the device you choose **for this startup**. On an **ASUS ROG Strix Z490-G Gaming** motherboard, it is the convenient choice for starting a Windows installer from a USB drive once. **Boot Option Priorities** controls which device the motherboard tries first on later starts. Selecting a USB drive under Boot Override starts it immediately. [ASUS ROG Strix Z490-G Gaming BIOS manual, page 59](https://dlcdnets.asus.com/pub/ASUS/mb/LGA1200/ROG_STRIX_Z490-G_GAMING/E16801_ROG_STRIX_Z490-G_GAMING_Series_BIOS_manual_EM_WEB.pdf#page=59)

## Boot from USB once on the ROG Strix Z490-G Gaming

1. Connect the prepared bootable USB drive and start or restart the computer.
2. Press **Delete** or **F2** during the initial startup check to enter the motherboard’s BIOS setup. If it opens in **EZ Mode**, press **F7** for **Advanced Mode**.
3. Open **Boot**, find **Boot Override**, and select the USB drive from the list. If you only need the device list, the same board also offers a shortcut. Press **F8** when the ASUS logo appears at startup. [ASUS motherboard BIOS manual, setup keys and Boot menu](https://dlcdnets.asus.com/pub/ASUS/mb/LGA1200/ROG_STRIX_Z490-G_GAMING/E16801_ROG_STRIX_Z490-G_GAMING_Series_BIOS_manual_EM_WEB.pdf)

## Where is Boot Override on an ASUS notebook?

Match the menu to the firmware screen you see. In the notebook UEFI example, ASUS shows **Boot Menu (F8)**. Open it, select the USB drive and press **Enter**. In the legacy BIOS example, the drive appears under **Save & Exit → Boot Override**. Select its entry and press **Enter** to start from it. [ASUS guide to USB boot menus](https://www.asus.com/us/support/faq/1013017/)

## What if the USB drive is missing?

First check how you prepared the drive. For a Windows installation, ASUS uses Microsoft’s **Media Creation Tool** to make a bootable USB installer. If you simply copied the ISO file to a spare stick, use the tool and select **USB flash drive** as the destination. Creating the installer erases the selected drive, so choose one whose contents you can replace. [ASUS Windows installation media guide](https://rog.asus.com/support/faq/1039507/)

## What if Windows only starts through Boot Override?

If the installed Windows drive starts when you select it manually, look at the saved order. In **Advanced Mode → Boot**, open **Boot Option #1**, choose the entry for the drive that successfully started Windows, then press **F10** and confirm. On the next restart, check whether it starts on its own. This procedure requires the system drive to appear in the list. If the list has no entry for it, ASUS directs owners to drive-detection troubleshooting. [ASUS boot priority instructions](https://www.asus.com/us/support/faq/1053205/) · [ASUS troubleshooting for a PC that opens BIOS at startup](https://rog.asus.com/support/faq/1042868/)
