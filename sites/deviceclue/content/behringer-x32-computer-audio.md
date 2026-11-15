# How to play computer audio through a Behringer X32 and record over USB

On a full-size X32 fitted with an **X-USB** expansion card, connect the computer to the USB socket **on the card**. Select X-USB in your recording software. The card carries up to 32 channels in each direction. On the console, **Card Out** selects what the computer can record. The console's **input routing** selects where playback from the computer appears on the mixer. You can test each direction separately with [one microphone](#record-one-microphone-before-assigning-all-the-tracks) and [a short stereo file](#bring-stereo-playback-onto-two-mixer-channels). [Behringer X-USB specifications and drivers](https://www.behringer.com/en/products/0606-ABV) · [Behringer X32 instructions, chapter 6](https://cdn-media.empowertribe.com/e452c7959c0d4002908c23044a9558a7/8849399545886.pdf#page=37)

## Which USB socket connects to the computer?

Look for **X-USB** on the expansion-card faceplate at the back of the console. The X32 also has a rear USB port marked for remote control and a top-panel socket for a USB drive. The top socket can record a stereo board mix directly to a drive. If a used console has a different expansion card, read the card label before choosing a driver. Behringer offers X-USB ASIO drivers for Windows and lists Core Audio support on Mac. [Behringer X32 connections](https://www.behringer.com/en/products/0603-ACE) · [Behringer X-USB downloads](https://www.behringer.com/en/products/0606-ABV)

## Bring stereo playback onto two mixer channels

Send a stereo file to **X-USB outputs 1 and 2** in the recording software. For a rehearsal with console channels **25–32** free, assign that input bank to **Card 1–8** in the input-routing screen. The file's left side now arrives on channel **25** and the right side on **26**. Start with the channel faders down and check the input meters. To hear it in Main LR, assign the two strips there, pan them left and right, then bring up the level. The bank assignment also changes channels 27–32, so confirm all eight are available before applying it. [Behringer X32 input-routing instructions](https://cdn-media.empowertribe.com/e452c7959c0d4002908c23044a9558a7/8849399545886.pdf#page=51)

## Record one microphone before assigning all the tracks

1. For a microphone connected to rear **XLR input 3**, open the console's **Routing** screen. On **Card Out**, set the source of card outputs **1–8** to **Local 1–8**. In an existing show, note the current assignment first because this setting changes all eight card feeds.
2. In your digital audio workstation, select X-USB as the audio input. Choose **input 3** on a mono track and arm it. Speak into the microphone and check the track meter.
3. Record a few seconds. This particular route takes signal from the local preamp. Moving the channel fader changes the live mix independently of the recorded track. If the microphone is actually plugged into a digital stagebox, use its matching AES50 input bank for the card send.

If input 3 is missing from the software's list, check the channel count in **Setup → Card**. A two-channel configuration exposes only the first pair. [Behringer X32 recording example](https://cdn-media.empowertribe.com/e452c7959c0d4002908c23044a9558a7/8849399545886.pdf#page=38) · [Behringer card-output routing](https://cdn-media.empowertribe.com/e452c7959c0d4002908c23044a9558a7/8849399545886.pdf#page=54)

## Where to look when only one direction works

If playback reaches channels 25 and 26 but the recorded track is silent, follow the microphone from its socket through **Card Out** to the track's selected input. If the recording worked but playback is silent, follow the stereo file from its software output pair to the console input bank. Once the console's channel meters move, the return has arrived. Check the channel mute, level and mix assignment from there. [Behringer X32 signal routing](https://cdn-media.empowertribe.com/e452c7959c0d4002908c23044a9558a7/8849399545886.pdf#page=51)
